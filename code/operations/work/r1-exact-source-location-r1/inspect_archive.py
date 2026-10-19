"""Read the exact historical ZIP and its direct cohort references; never extract."""
from __future__ import annotations

import hashlib
import json
import re
import stat
import zipfile
from pathlib import Path, PurePosixPath, PureWindowsPath

DEST = Path(__file__).resolve().parent
BASE = Path(r"C:\Users\nicol\Documents\Codex\2026-10-15\cr\outputs\HPC-Forest-Etude-2020-2024-r1")
EXPECTED = "cd769d474b6cb14c2fba11ab687f8825d35cb0b57a397d09aefab0ae743ffc18"


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def ref(path):
    path = Path(path)
    raw = path.read_bytes()
    return {"path": str(path), "sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)}


def main():
    cohort = BASE / "runs/coverage-gpt-6-luna-max"
    auth = read(cohort / "autorisation.json")
    source = Path(auth["source_zip"]["path"])
    assert source.is_file() and source.is_absolute() and not any(p.is_symlink() or p.is_junction() for p in (source, *source.parents))
    actual = ref(source)
    assert actual["sha256"] == auth["source_zip"]["sha256"] == EXPECTED
    plan = Path(auth["plan"]["path"])
    assert ref(plan)["sha256"] == auth["plan"]["sha256"]
    derived = read(BASE.parent / "HPC-Forest-Harnais-Comparaison-r1/manifest-source-derivee.json")
    assert derived["base_source_sha256"] == EXPECTED
    issues, files, directories, kinds = [], {}, [], {}
    with zipfile.ZipFile(source) as archive:
        infos = archive.infolist()
        total = sum(item.file_size for item in infos)
        assert 0 < len(infos) <= 5000 and total <= 100 * 1024**2
        seen, folded = set(), set()
        for item in infos:
            name = item.filename
            normalized = name.replace("\\", "/")
            parts = PurePosixPath(normalized).parts
            reasons = []
            if not name or "\x00" in name or "\\" in name or name.startswith(("/", "\\")) or PureWindowsPath(name).drive:
                reasons.append("absolute, drive, empty or noncanonical separator")
            if any(part in {".", ".."} or ":" in part or part.endswith((" ", ".")) or re.fullmatch(r"(?i:con|prn|aux|nul|com[1-9]|lpt[1-9])(?:\..*)?", part) for part in parts):
                reasons.append("unsafe path component")
            if name in seen or normalized.casefold() in folded:
                reasons.append("duplicate or case-colliding name")
            seen.add(name)
            folded.add(normalized.casefold())
            mode = item.external_attr >> 16
            kind = stat.S_IFMT(mode)
            kinds[str(kind)] = kinds.get(str(kind), 0) + 1
            if stat.S_ISLNK(mode) or kind not in {0, stat.S_IFREG, stat.S_IFDIR}:
                reasons.append("link or special member")
            if item.flag_bits & 1:
                reasons.append("encrypted member")
            if reasons:
                issues.append({"name": name, "reasons": reasons})
            if item.is_dir():
                directories.append(name)
            else:
                raw = archive.read(item)
                assert len(raw) == item.file_size
                files[name] = {"sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw), "compressed_bytes": item.compress_size}
        crc_failure = archive.testzip()
    paths = list(files)
    top = sorted({PurePosixPath(path).parts[0] for path in paths})
    suffix_match = {}
    for name, entry in files.items():
        candidates = [key for key in derived["files"] if name == key or name.endswith("/" + key)]
        if len(candidates) == 1:
            suffix_match[name] = {"derived_path": candidates[0], "equal_to_9a68_file": derived["files"][candidates[0]] == entry["sha256"]}
    result = {"schema": "hpc-forest-exact-r1-source-location-readonly-v1", "source_available_local": True,
              "source": actual, "expected_sha256": EXPECTED, "sha256_verified": True,
              "zip_members": len(infos), "regular_files": len(files), "directories": len(directories), "total_uncompressed_bytes": total,
              "archive_safety": {"safe_names_and_types": not issues, "issues": issues, "crc_failure": crc_failure, "all_files_read_without_execution": True,
                                 "extraction_performed": False, "member_type_counts": kinds},
              "top_level_components": top, "files": files,
              "cohort": {"run_directory": str(cohort), "authorization": ref(cohort / "autorisation.json"),
                         "authorization_identity": {key: auth[key] for key in ("schema", "scope_id", "model", "effort", "session_id")},
                         "submission": ref(cohort / "submission.json"), "submission_job_id": read(cohort / "submission.json")["job_id"],
                         "plan": ref(plan), "actual_historical_job_id": "748259"},
              "comparison_derivative": {"sha256": derived["new_source_zip_sha256"], "declared_base_sha256": derived["base_source_sha256"],
                                        "declared_base_files_byte_identical": derived["base_files_byte_identical"], "matched_files": len(suffix_match),
                                        "matching_file_hashes": sum(item["equal_to_9a68_file"] for item in suffix_match.values()),
                                        "mismatches": [name for name, item in suffix_match.items() if not item["equal_to_9a68_file"]]},
              "source_code_executed": False, "source_extracted": False, "network_calls": 0, "model_calls": 0, "jobs_submitted": 0}
    assert result["cohort"]["submission_job_id"] == "748259"
    output = DEST / "VERIFICATION-ARCHIVE-R1-CD769.json"
    with output.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    print(json.dumps({"report": ref(output), "source": actual, "regular_files": len(files), "members": len(infos),
                      "safe": not issues, "crc_failure": crc_failure, "cohort_job": "748259", "model": auth["model"], "effort": auth["effort"],
                      "derived_file_hashes_matching": result["comparison_derivative"]["matching_file_hashes"], "executed_archive_code": False}))


if __name__ == "__main__":
    main()
