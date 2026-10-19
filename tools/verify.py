"""Verify file integrity and recalculate the published evidence; read-only."""
from __future__ import annotations

import hashlib
import re
from pathlib import Path, PurePosixPath
from urllib.parse import unquote, urlsplit

from .article_r5 import verify as verify_article_r5
from .manifest import public_files
from .native_first import verify as verify_native_first
from .qualification import verify as verify_qualification
from .received_r4 import HTMLReferences, verify as verify_received_r4
from .received import verify as verify_received
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
    for path in root.rglob("*.md"):
        if any(part.startswith(".") for part in path.relative_to(root).parts):
            continue
        for link in re.findall(r"!?\[[^\]]*\]\(([^\s)]+)\)", path.read_text(encoding="utf-8")):
            if re.match(r"[a-z][a-z0-9+.-]*:", link, re.IGNORECASE) or link.startswith("#"):
                continue
            target = (path.parent / link.split("#", 1)[0]).resolve()
            if not target.is_relative_to(root.resolve()) or not target.exists():
                raise EvidenceError(f"Broken relative link in {path.name}: {link}")
            checked += 1
    return checked


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


def main():
    count = verify_manifest(ROOT)
    compare(compute(), load_json((ROOT / "evidence/results.json").read_text(encoding="utf-8")))
    received = verify_received(ROOT)
    qualification = verify_qualification(ROOT)
    revision4 = verify_received_r4(ROOT)
    native = verify_native_first(ROOT)
    article = verify_article_r5(ROOT)
    article_files = verify_article_bundle(ROOT)
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
    print("This checks integrity and arithmetic; it does not execute or certify the evaluated programs.")


if __name__ == "__main__":
    main()
