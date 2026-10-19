"""Restore one pinned private source into a new local folder; execute no project code."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import zipfile
from pathlib import Path, PurePosixPath

PINS = {
    "r1-harnais-9a68": "9a68a83fde4acb6bd247d79e00490e7d36f0c4c59c6c881152101e4c499387eb",
    "r2-matrice15-b79": "b79e6fdc3e1e0dae5d9d240353510c504ffc1298265a6d425f248a8f2b5489d4",
}
IGNORED_CACHES = {"__pycache__", ".pytest_cache", ".ruff_cache"}
DEVICE = re.compile(r"^(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\.|$)", re.I)


def need(condition, message):
    if not condition:
        raise ValueError(message)


def checksum(raw):
    return hashlib.sha256(raw).hexdigest()


def unique_object(pairs):
    value = {}
    for key, item in pairs:
        need(key not in value, "Champ JSON duplique")
        value[key] = item
    return value


def read_json(path):
    def nonfinite(value):
        raise ValueError("Nombre JSON non fini : " + value)
    return json.loads(path.read_text(encoding="utf8"), object_pairs_hook=unique_object,
                      parse_constant=nonfinite)


def ordinary(path, *, file=False):
    path = Path(path)
    need(path.is_absolute() and ".." not in path.parts, "Chemin absolu sans traversal requis")
    need(not any(item.is_symlink() or getattr(item, "is_junction", lambda: False)()
                 or (item.exists() and getattr(item.lstat(), "st_file_attributes", 0) & 0x400)
                 for item in (path, *path.parents)), "Lien, junction ou reparse point refuse")
    if file:
        need(path.is_file(), "Fichier prive absent")
    return path


def artifact(root, ref):
    need(isinstance(ref, dict) and set(ref) == {"path", "sha256"}, "Reference path/SHA exacte requise")
    relative = PurePosixPath(ref["path"])
    need(relative.parts and not relative.is_absolute() and ".." not in relative.parts
         and relative.as_posix() == ref["path"] and "\\" not in ref["path"], "Chemin de catalogue non confine")
    path = ordinary(root.joinpath(*relative.parts), file=True)
    need(path.resolve().is_relative_to(root.resolve()), "Fichier du catalogue hors paquet")
    need(checksum(path.read_bytes()) == ref["sha256"], "SHA du fichier prive different")
    return path


def member_name(name):
    pure = PurePosixPath(name)
    need(pure.parts and pure.parts[0] == "HPC-Forest" and len(pure.parts) > 1
         and not pure.is_absolute() and ".." not in pure.parts and pure.as_posix() == name
         and "\\" not in name and not any(char in name for char in (":", "\0", "\r", "\n")),
         "Membre ZIP hors racine ou nom dangereux")
    relative = pure.relative_to("HPC-Forest")
    need(not any(part.endswith((".", " ")) or DEVICE.match(part) or part == ".git" for part in relative.parts),
         "Nom Windows ambigu, reserve ou depot imbrique refuse")
    return relative.as_posix()


def validate(root, edition):
    root = ordinary(root)
    catalogue = read_json(ordinary(root / "CATALOGUE.json", file=True))
    need(catalogue.get("schema") == "hpc-forest-private-r1-r2-reexecution-catalogue-v1", "Mauvais catalogue")
    need(edition in PINS and edition in catalogue["editions"], "Edition inconnue")
    entry = catalogue["editions"][edition]
    need(entry["source_zip"]["sha256"] == PINS[edition], "Edition scientifique non pinnee")
    archive_path = artifact(root, entry["source_zip"])
    manifest_path = artifact(root, entry["runtime_manifest"])
    declared = read_json(manifest_path)
    need(isinstance(declared, dict) and declared and all(isinstance(key, str) and re.fullmatch(r"[a-f0-9]{64}", sha)
         for key, sha in declared.items()), "Inventaire source complet requis")
    files, folded, total = {}, set(), 0
    with zipfile.ZipFile(archive_path) as archive:
        for item in archive.infolist():
            need(not item.is_dir() and (item.external_attr >> 16) & 0o170000 in {0, stat.S_IFREG}
                 and not item.flag_bits & 1, "Membre non regulier ou chiffre refuse")
            relative = member_name(item.filename)
            total += item.file_size
            need(relative.casefold() not in folded and len(files) < 2000 and item.file_size <= 8 * 1024 * 1024
                 and total <= 64 * 1024 * 1024, "ZIP duplique ou hors bornes")
            folded.add(relative.casefold())
            with archive.open(item) as source:
                raw = source.read(8 * 1024 * 1024 + 1)
            need(len(raw) == item.file_size and relative in declared and checksum(raw) == declared[relative],
                 "Octets ZIP absents ou differents du manifeste")
            files[relative] = raw
    need(set(files) == set(declared) and len(files) == entry["source_file_count"], "Inventaire ZIP/manifeste incomplet")
    return entry, files, declared


def prepare(root, edition, destination):
    entry, files, declared = validate(root, edition)
    destination = ordinary(destination)
    need(not destination.exists() and destination.parent.is_dir(), "Destination neuve et parent existant requis")
    destination.mkdir(exist_ok=False)
    project = destination / "project"
    project.mkdir(exist_ok=False)
    for relative, raw in files.items():
        target = project.joinpath(*PurePosixPath(relative).parts)
        target.parent.mkdir(parents=True, exist_ok=True)
        ordinary(target.parent)
        need(target.parent.resolve().is_relative_to(project.resolve()), "Ecriture hors nouvelle copie refusee")
        descriptor = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(raw)
    actual = {path.relative_to(project).as_posix(): checksum(path.read_bytes()) for path in project.rglob("*") if path.is_file()}
    need(actual == declared, "Relecture de la nouvelle copie differente")
    receipt = {"schema": "hpc-forest-private-fresh-source-restore-v1", "edition": edition,
        "source_zip_sha256": entry["source_zip"]["sha256"], "source_file_count": len(files),
        "project": str(project), "restored_source_verified": actual == declared,
        "historical_version_mutated": False, "scientific_run_started": False, "native_model_calls": 0,
        "jobs_submitted": 0, "network_used": False, "existing_session_or_budget_reused": False}
    with (destination / "RESTAURATION.json").open("x", encoding="utf8") as stream:
        json.dump(receipt, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    return receipt


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--edition", choices=sorted(PINS), required=True)
    parser.add_argument("--destination", type=Path)
    parser.add_argument("--verify-only", action="store_true")
    args = parser.parse_args(argv)
    root = Path(__file__).resolve().parent
    try:
        if args.verify_only:
            need(args.destination is None, "Ne pas combiner verify-only et destination")
            entry, files, _ = validate(root, args.edition)
            value = {"edition": args.edition, "source_zip_sha256": entry["source_zip"]["sha256"],
                     "source_file_count": len(files), "archive_verified": True, "source_executed": False}
        else:
            need(args.destination is not None, "Une destination neuve explicite est requise")
            value = prepare(root, args.edition, args.destination)
        print(json.dumps(value, ensure_ascii=False))
    except (ValueError, OSError, KeyError, zipfile.BadZipFile) as error:
        print(json.dumps({"restored_source_verified": False, "error": str(error)}, ensure_ascii=False))
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
