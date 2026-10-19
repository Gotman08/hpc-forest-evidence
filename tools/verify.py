"""Verify file integrity and recalculate the published evidence; read-only."""
from __future__ import annotations

import hashlib
import re
import stat
from datetime import datetime
from itertools import pairwise
from pathlib import Path, PurePosixPath
from urllib.parse import unquote, urlsplit

from .article_r5 import verify as verify_article_r5
from .full_snapshot import (
    SnapshotError,
    _digest_file,
    _linked,
    _relative,
    _unlinked_ancestors,
)
from .full_snapshot import verify as verify_full_snapshot
from .manifest import public_files
from .native_first import verify as verify_native_first
from .qualification import verify as verify_qualification
from .received import verify as verify_received
from .received_r4 import HTMLReferences
from .received_r4 import verify as verify_received_r4
from .recompute import ROOT, EvidenceError, compare, compute, load_json


def verify_manifest(root: Path):
    manifest = load_json((root / "MANIFEST.json").read_text(encoding="utf-8"))
    if manifest.get("schema") != 1 or not isinstance(manifest.get("files"), list):
        raise EvidenceError("Invalid manifest schema")
    seen = set()
    for item in manifest["files"]:
        name = item.get("path")
        if (not isinstance(name, str) or "\\" in name or ":" in name
                or PurePosixPath(name).is_absolute() or ".." in PurePosixPath(name).parts
                or name in seen or name == "MANIFEST.json"):
            raise EvidenceError("Unsafe or duplicate manifest path")
        seen.add(name)
        target = root / name
        if (not target.is_file() or any(p.is_symlink() for p in [target, *target.parents] if p != root.parent)
                or not target.resolve().is_relative_to(root.resolve())):
            raise EvidenceError(f"Missing or linked public artifact: {name}")
        raw = target.read_bytes()
        if type(item.get("bytes")) is not int or len(raw) != item["bytes"] or hashlib.sha256(raw).hexdigest() != item.get("sha256"):
            raise EvidenceError(f"Artifact changed: {name}")
    actual = {path.relative_to(root).as_posix() for path in public_files(root)}
    if actual != seen:
        raise EvidenceError("Public file inventory differs from the manifest")
    return len(seen)


def verify_links(root: Path):
    checked = 0
    # Historical source documents retain their original, machine-specific links.
    # Their bytes are checked by the manifest; current documentation remains linked.
    archived = (("code", "r1-historical"), ("code", "r1-comparison"),
                ("code", "r2-native"), ("code", "operations"),
                ("reproducibility", "reexecution-r1-r2-r2"))
    for path in root.rglob("*.md"):
        relative = path.relative_to(root).parts
        if (any(part.startswith(".") for part in relative)
                or any(relative[:len(prefix)] == prefix for prefix in archived)):
            continue
        for link in re.findall(r"!?\[[^\]]*\]\(([^\s)]+)\)", path.read_text(encoding="utf-8")):
            if re.match(r"[a-z][a-z0-9+.-]*:", link, re.IGNORECASE) or link.startswith("#"):
                continue
            target = (path.parent / link.split("#", 1)[0]).resolve()
            if not target.is_relative_to(root.resolve()) or not target.exists():
                raise EvidenceError(f"Broken relative link in {path.name}: {link}")
            checked += 1
    return checked


def verify_source_trees(root: Path):
    """Hash the inert historical copies and require complete source coverage."""
    root = root.resolve()
    guide = "reproducibility/reexecution-r1-r2-r2"
    edition_paths = {"code/r1-historical", "code/r1-comparison", "code/r2-native"}
    code_prefixes = edition_paths | {"code/operations"}
    excluded = {"code/README.md", "code/SOURCES.json"}

    def require(condition, message):
        if not condition:
            raise EvidenceError("Published source trees: " + message)

    def path_name(value):
        try:
            return _relative(value)
        except SnapshotError as exc:
            raise EvidenceError("Published source trees: unsafe path") from exc

    def files_under(folder):
        result, pending = set(), [root / folder]
        while pending:
            current = pending.pop()
            _unlinked_ancestors(current)
            require(current.is_dir(), "missing source directory")
            for target in current.iterdir():
                info = target.lstat()
                require(not _linked(info), "linked source entry")
                if stat.S_ISDIR(info.st_mode):
                    pending.append(target)
                else:
                    require(stat.S_ISREG(info.st_mode), "non-regular source entry")
                    result.add(target.relative_to(root).as_posix())
        return result

    _unlinked_ancestors(root / "code/SOURCES.json")
    data = load_json((root / "code/SOURCES.json").read_text(encoding="utf-8"))
    require(isinstance(data, dict) and set(data) == {"schema", "experiments_paused", "historical_editions",
                                                   "operation_files", "files", "scope"}, "invalid inventory fields")
    require(data["schema"] == "hpc-forest-published-source-trees-v1" and data["experiments_paused"] is True,
            "invalid schema or paused state")
    require(isinstance(data["scope"], str) and data["scope"], "missing scope")
    require(isinstance(data["files"], list) and data["files"], "missing file inventory")
    seen, references, prefixes = set(), {}, {}
    for item in data["files"]:
        require(isinstance(item, dict) and set(item) == {"path", "bytes", "sha256"}, "invalid file fields")
        name = path_name(item["path"])
        require(name not in excluded and (any(name.startswith(p + "/") for p in code_prefixes)
                                         or name.startswith(guide + "/")), "out-of-scope source path")
        folded = name.casefold()
        require(folded not in seen, "duplicate source path")
        seen.add(folded)
        for length in range(1, len(name.split("/")) + 1):
            prefix = "/".join(name.split("/")[:length])
            key = prefix.casefold()
            require(key not in prefixes or prefixes[key] == prefix, "case-colliding source path")
            prefixes[key] = prefix
        require(type(item["bytes"]) is int and item["bytes"] >= 0 and isinstance(item["sha256"], str)
                and re.fullmatch(r"[0-9a-f]{64}", item["sha256"]), "invalid file fingerprint")
        target = root / name
        _unlinked_ancestors(target)
        digest, size, _ = _digest_file(target)
        require(size == item["bytes"] and digest == item["sha256"], "source bytes differ")
        references[name] = item
    actual_code = files_under("code") - excluded
    actual_guide = files_under(guide)
    require(set(references) == actual_code | actual_guide, "source coverage differs")
    editions = data["historical_editions"]
    require(isinstance(editions, list) and len(editions) == len(edition_paths), "invalid historical edition inventory")
    edition_seen, historical_count = set(), 0
    for edition in editions:
        require(isinstance(edition, dict) and set(edition) == {"path", "archive", "archive_sha256", "files"},
                "invalid historical edition fields")
        folder = path_name(edition["path"])
        archive = path_name(edition["archive"])
        require(folder in edition_paths and folder not in edition_seen and "/" not in archive and archive.endswith(".zip"),
                "unknown or duplicate historical edition")
        edition_seen.add(folder)
        archive_reference = references.get(guide + "/archives/" + archive)
        require(archive_reference is not None and archive_reference["sha256"] == edition["archive_sha256"],
                "historical archive fingerprint differs")
        count = sum(name.startswith(folder + "/") for name in actual_code)
        require(type(edition["files"]) is int and edition["files"] > 0 and count == edition["files"],
                "historical source count differs")
        historical_count += count
    operations = sum(name.startswith("code/operations/") for name in actual_code)
    require(type(data["operation_files"]) is int and data["operation_files"] >= 0
            and operations == data["operation_files"] and len(actual_code) == historical_count + operations,
            "operational source count differs")
    return {"files": len(references), "code_files": len(actual_code), "restoration_files": len(actual_guide),
            "historical_editions": len(editions), "operation_files": operations}


def verify_article_bundle(root: Path):
    folder = root / "docs/article"
    provenance = load_json((folder / "provenance.json").read_text(encoding="utf-8"))
    if (provenance.get("schema") != "hpc-forest-public-article-v3"
            or provenance.get("edition") != "2026-10-19-r5"
            or provenance.get("source_cutoff_utc") != "2026-10-19T11:40:35.931000+00:00"
            or provenance.get("new_scientific_gain_admitted") is not False
            or type(provenance.get("scientifically_admitted_pairs")) is not int
            or provenance.get("scientifically_admitted_pairs") != 0):
        raise EvidenceError("Current article scope differs")
    previous = load_json((folder / "history/r4/provenance.json").read_text(encoding="utf-8"))
    docs = {name + "." + extension for name in ("ARTICLE", "ANNEXES-TECHNIQUES")
            for extension in ("pdf", "html", "md")}
    original_figures = {item["path"] for item in previous["files"] if item["path"].endswith(".png")}
    figures = {f"edition-professionnelle/figures/comparaison-r1-r2/{name}.{extension}"
               for name in ("couverture-r1-r2", "quicksort-repetitions-r1-r2", "cout-et-couverture-r1-r2")
               for extension in ("png", "svg", "pdf")}
    data = {"donnees-r1-r2/" + name for name in ("comparison.json", "matrix15-comparison.csv",
            "timing-samples.csv", "FILES.sha256.json", "provenance.json", "rebuild-figures.py", "REPRODUCTION.md")}
    expected = docs | original_figures | figures | data
    files = provenance.get("files", [])
    if not isinstance(files, list):
        raise EvidenceError("Missing current article artifact inventory")
    seen = set()
    for item in files:
        if not isinstance(item, dict) or set(item) != {"path", "bytes", "sha256"}:
            raise EvidenceError("Invalid current article artifact entry")
        name = item["path"]
        if not isinstance(name, str) or name not in expected or name in seen:
            raise EvidenceError("Unreviewed or duplicate current article artifact")
        target = folder / name
        if not target.is_file() or target.is_symlink() or not target.resolve().is_relative_to(folder.resolve()):
            raise EvidenceError("Missing current article artifact")
        raw = target.read_bytes()
        if type(item["bytes"]) is not int or len(raw) != item["bytes"] or hashlib.sha256(raw).hexdigest() != item["sha256"]:
            raise EvidenceError("Current article bytes differ from provenance")
        seen.add(name)
    if seen != expected:
        raise EvidenceError("Incomplete current article artifact inventory")
    for item in previous["files"]:
        if item["path"] in original_figures:
            raw = (folder / item["path"]).read_bytes()
            if len(raw) != item["bytes"] or hashlib.sha256(raw).hexdigest() != item["sha256"]:
                raise EvidenceError("Original article figure changed")
    for name in ("ARTICLE.html", "ANNEXES-TECHNIQUES.html"):
        parser = HTMLReferences()
        parser.feed((folder / name).read_text(encoding="utf-8"))
        for tag, attr, raw in parser.references:
            parts = urlsplit(raw)
            if parts.scheme in {"http", "https", "mailto"}:
                if tag != "a" or attr != "href":
                    raise EvidenceError("External article rendering dependency")
                continue
            if parts.scheme == "data":
                continue
            if parts.scheme or parts.netloc:
                raise EvidenceError("Unexpected current article HTML reference")
            if parts.path:
                target = (folder / unquote(parts.path)).resolve()
                if not target.is_relative_to(folder.resolve()) or not target.is_file():
                    raise EvidenceError("Broken current article HTML artifact reference")
    return len(files)


def verify_native_incidents(root: Path):
    raw = (root / "evidence/native-incidents-2026-10-19/incidents.json").read_text(encoding="utf-8")
    data = load_json(raw)
    shapes = {
        "": "schema article_source_cutoff_utc observed_at_utc coverage sol_count astra_count limits sources",
        "coverage": "registered_cells source_final_timing_cells technical_incident_cells not_launched_cells cells_without_included_scientific_measurement scientifically_admitted_pairs new_scientific_gains_admitted",
        "sol_count": "job_id subject_id declared_model declared_effort scheduler_state scheduler_elapsed_seconds bootstrap_failed_at_utc original_admission_deadline_utc admission_accepted native_child_launch_attempted model_calls exact_tokens deadline_expired_at_observation failure_caused_by_deadline_expiry budget_or_chronology_reset replay_performed",
        "astra_count": "job_id subject_id declared_model declared_effort scheduler_state scheduler_exit_code scheduler_ended_at_utc allocation_admission_accepted pipeline_complete source_first_start_verified source_invocation_unknown source_delivered_calls_announced source_exact_tokens_announced_per_call source_exact_tokens_announced scientific_timing_samples_published original_archive later_reception",
        "astra_count.original_archive": "members regular_file_members links preceding_metadata_artifacts_expected preceding_metadata_artifacts_present preceding_metadata_regular_and_bounded second_delivery_receipt_present",
        "astra_count.later_reception": "scp_transfers_requested scp_transfers_received all_scp_transfers_verified second_delivery_receipt_received",
        "limits": "model_and_effort_are_declared_source_metadata tokens_are_source_cache_and_response_announcements independent_private_cli_audit_performed independent_performance_audit_verified final_performance_admission_claimed article_r5_and_numeric_dataset_modified scientific_jobs_launched_for_publication model_calls_issued_for_publication",
    }
    def require(condition, message):
        if not condition:
            raise EvidenceError("Native technical incidents: " + message)
    def object_at(path):
        item = data
        for key in path.split(".") if path else []:
            item = item[key]
        return item
    for path, fields in shapes.items():
        item = object_at(path)
        require(type(item) is dict and set(item) == set(fields.split()), "closed fields required at " + path)
    def exact(path, wanted):
        actual = object_at(path)
        require(type(actual) is type(wanted) and actual == wanted, "unsupported status or count at " + path)
    exact("schema", "hpc-forest-native-r2-technical-incidents-v1")
    exact("article_source_cutoff_utc", "2026-10-19T11:40:35.931000+00:00")
    exact("observed_at_utc", "2026-10-19T12:34:58.457867+00:00")
    expected = {
        "coverage": [60, 1, 2, 57, 59, 0, 0],
        "sol_count": {"job_id":"755766", "subject_id":"2023-count", "declared_model":"gpt-6.1-sol", "declared_effort":"max", "scheduler_state":"FAILED", "scheduler_elapsed_seconds":3, "admission_accepted":False, "native_child_launch_attempted":False, "model_calls":0, "exact_tokens":0, "deadline_expired_at_observation":True, "failure_caused_by_deadline_expiry":False, "budget_or_chronology_reset":False, "replay_performed":False},
        "astra_count": {"job_id":"755862", "subject_id":"2023-count", "declared_model":"gpt-6-astra", "declared_effort":"max", "scheduler_state":"FAILED", "scheduler_exit_code":"1:0", "allocation_admission_accepted":True, "pipeline_complete":False, "source_first_start_verified":False, "source_invocation_unknown":True, "source_delivered_calls_announced":2, "source_exact_tokens_announced":30919, "scientific_timing_samples_published":0},
        "astra_count.original_archive": [295, 190, 0, 12, 11, True, False],
        "astra_count.later_reception": [6, 6, True, True],
        "limits": [True, True, False, False, False, False, 0, 0],
    }
    for path, wanted in expected.items():
        if isinstance(wanted, list):
            wanted = dict(zip(shapes[path].split(), wanted, strict=True))
        for key, value in wanted.items():
            exact(path + "." + key, value)
    coverage = data["coverage"]
    require(coverage["registered_cells"] == coverage["source_final_timing_cells"] + coverage["technical_incident_cells"] + coverage["not_launched_cells"], "cell coverage does not sum to 60")
    require(coverage["cells_without_included_scientific_measurement"] == coverage["technical_incident_cells"] + coverage["not_launched_cells"], "missing scientific measurements promoted")
    tokens = data["astra_count"]["source_exact_tokens_announced_per_call"]
    require(type(tokens) is list and all(type(n) is int for n in tokens) and tokens == [14753, 16166], "source-announced per-call tokens differ")
    require(sum(tokens) == data["astra_count"]["source_exact_tokens_announced"], "source-announced token sum differs")
    chronology = [data["sol_count"]["bootstrap_failed_at_utc"], data["article_source_cutoff_utc"], data["sol_count"]["original_admission_deadline_utc"], data["astra_count"]["scheduler_ended_at_utc"], data["observed_at_utc"]]
    moments = [datetime.fromisoformat(value) for value in chronology]
    require(all(moment.utcoffset() is not None and moment.utcoffset().total_seconds() == 0 for moment in moments) and all(a < b for a, b in pairwise(moments)), "failure, deadline and receipt chronology differs")
    sources = data["sources"]
    names = {"sol-bootstrap-result":"bootstrap-failed-755766.json", "astra-readonly-summary":"SYNTHESE-CAUSE-r1.json", "astra-original-archive":"results-755862.tar.gz", "astra-later-delivery-receipt":None, "sol-bootstrap-scp-receipt":"BOOTSTRAP-FAILED-SCP-REEL-r1.json", "sol-scheduler-summary":"JOB-EFFICIENCY-FAILED-REEL-r1.json", "astra-cache-worker-summary":"LOCAL-CACHE-AND-WORKER-SUMMARY-r1.json", "astra-scheduler-status":"JOB-STATUS-r1.json"}
    require(type(sources) is list and len(sources) == len(names), "source fingerprint inventory differs")
    seen = set()
    for item in sources:
        require(type(item) is dict and set(item) == {"id", "basename", "bytes", "sha256"}, "closed source metadata required")
        name = item["id"]
        require(type(name) is str and name in names and name not in seen and item["basename"] == names[name], "private or duplicate source name")
        require(type(item["bytes"]) is int and item["bytes"] > 0 and type(item["sha256"]) is str and re.fullmatch(r"[0-9a-f]{64}", item["sha256"]), "invalid source fingerprint")
        seen.add(name)
    require(not re.search(r"(?<![A-Za-z0-9])[A-Za-z]:[\\/]|/scratch/|/home/|Bearer\s|sk-[A-Za-z0-9]{16}", raw, re.IGNORECASE), "private path or credential pattern")
    return coverage


def main():
    count = verify_manifest(ROOT)
    compare(compute(), load_json((ROOT / "evidence/results.json").read_text(encoding="utf-8")))
    received = verify_received(ROOT)
    qualification = verify_qualification(ROOT)
    revision4 = verify_received_r4(ROOT)
    native = verify_native_first(ROOT)
    article = verify_article_r5(ROOT)
    article_files = verify_article_bundle(ROOT)
    incidents = verify_native_incidents(ROOT)
    source_trees = verify_source_trees(ROOT)
    full_snapshot = verify_full_snapshot(ROOT / "archive/full-2026-10-19")
    links = verify_links(ROOT)
    print(f"Verified {count} file hashes and {links} relative links.")
    print("Recomputed 144 controller series (2,400 measured cycles) and 200 CPU samples (40 configurations).")
    print(f"Received update: {received['cpu_samples']} CPU samples, {received['confirmations']} confirmations, "
          f"{received['registers']} search registers and {received['cost_exports']} separate cost views.")
    print(f"Separate zero-model qualification: {qualification['subjects']} baselines and {qualification['samples']} timings.")
    print(f"Revision r4: {revision4['matrix_cells']} matrix cells, {revision4['r2_NA']} R2 missing values and no complete comparison.")
    print(f"Native first batch: {native['candidate_samples']} initial and {native['reference_samples']} reference timings, "
          f"{native['delivered_calls']} delivered calls and {native['exact_tokens_used']} exact tokens; "
          "audited release accepted on ARM, with no final confirmation or admitted scientific gain.")
    print(f"Article r5: {article_files} artifacts, {article['matrix_cells']} cells and {article['timing_samples']} timings; "
          f"{article['r2_missing_cells']} R2 cells without measurements and zero scientifically admitted pairs.")
    print(f"Later technical supplement: {incidents['technical_incident_cells']} incidents, "
          f"{incidents['not_launched_cells']} unlaunched cells and {incidents['cells_without_included_scientific_measurement']} cells without included comparison measurements; no new performance result.")
    print(f"Published source copies: {source_trees['code_files']} code files and "
          f"{source_trees['restoration_files']} restoration files; historical programs were not executed.")
    print(f"Full inert snapshot: {full_snapshot['roots']} roots, {full_snapshot['files']} files and "
          f"{full_snapshot['unique_objects']} unique content objects.")
    print("This checks integrity and arithmetic; it does not execute or certify the evaluated programs.")


if __name__ == "__main__":
    main()
