"""Capture, verify and restore inert local files using only the standard library.

Capture never follows links or executes source. Failed operations leave their
partial output in place. Absolute source locations stay out of the inventory;
their normalized hashes prevent restoration into an original source tree.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath

MAX_CHUNK_BYTES = 40 * 1024 * 1024
MAX_LINK_DESCRIPTOR_BYTES = 1024 * 1024
MAX_CATALOG_BYTES = 20 * 1024 * 1024
DEFAULT_CATALOG_ENTRIES = 10000
TABLES = ("roots", "directories", "files", "links", "exclusions", "objects")
WINDOWS_DEVICES = frozenset({"CON", "PRN", "AUX", "NUL", "CLOCK$", "CONIN$", "CONOUT$"}
                            | {f"{prefix}{number}" for prefix in ("COM", "LPT") for number in "123456789¹²³"})
SCHEMA = "hpc-forest-full-snapshot-v1"
PLAN_SCHEMA = "hpc-forest-full-snapshot-build-plan-v1"
DEFAULT_SNAPSHOT = Path(__file__).resolve().parents[1] / "archive/full-2026-10-19"


class SnapshotError(ValueError):
    """Invalid, changed, unsafe or incomplete snapshot data."""


def _require(condition, message):
    if not condition:
        raise SnapshotError(message)


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        _require(key not in result, "Duplicate JSON key")
        result[key] = value
    return result


def _json(path):
    try:
        return json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_pairs)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise SnapshotError(f"Cannot read JSON: {path.name}") from exc


def _dump(value):
    return (json.dumps(value, ensure_ascii=True, sort_keys=True, indent=2) + "\n").encode("utf-8")


def _keys(value, keys):
    _require(isinstance(value, dict) and set(value) == set(keys), "Invalid object fields")


def _integer(value, minimum=0):
    return type(value) is int and value >= minimum


def _sha(value):
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def _component(value):
    """Require names that preserve their identity under ordinary Win32 paths."""
    _require(value and value not in {".", ".."} and value[-1] not in " ."
             and not any(c in '<>"|?*\\:\x00' or ord(c) < 32 for c in value),
             "Unsafe Windows path component")
    stem = value.split(".", 1)[0].rstrip(" ").upper()
    _require(stem not in WINDOWS_DEVICES, "Reserved Windows device name")


def _relative(value):
    _require(isinstance(value, str) and value and not any(c in value for c in "\\:\x00"),
             "Unsafe relative path")
    parts = value.split("/")
    _require(not PurePosixPath(value).is_absolute() and all(p not in {"", ".", ".."} for p in parts),
             "Unsafe relative path")
    for part in parts:
        _component(part)
    return value


def _root_id(value):
    _require(isinstance(value, str) and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}", value)
             and value not in {".", ".."} and value.casefold() != "links.json", "Invalid root ID")
    _component(value)
    return value


def _linked(info):
    return stat.S_ISLNK(info.st_mode) or bool(getattr(info, "st_file_attributes", 0) & 0x400)


def _unlinked_ancestors(path):
    for item in [path, *path.parents]:
        try:
            _require(not _linked(item.lstat()), "Linked path or ancestor")
        except FileNotFoundError:
            continue


def _location_hash(path):
    name = path.resolve().as_posix().casefold().rstrip("/") or "/"
    return hashlib.sha256(name.encode("utf-8", errors="surrogatepass")).hexdigest()


def _identity(info):
    # Windows may flush NTFS change-time metadata when a read handle opens;
    # content stability uses file identity, size and last-write time instead.
    # lstat also synthesizes execute bits from extensions such as .exe while
    # fstat does not. Ignore only those synthetic bits on Windows, retaining
    # file type and read-only/write permissions. POSIX modes stay unchanged.
    mode = info.st_mode & ~0o111 if os.name == "nt" else info.st_mode
    return (info.st_dev, info.st_ino, mode, info.st_size, info.st_mtime_ns)


def _bounded_bytes(path, maximum):
    before = path.lstat()
    _require(stat.S_ISREG(before.st_mode) and not _linked(before) and before.st_size <= maximum,
             "Missing, linked or oversized JSON artifact")
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    with os.fdopen(os.open(path, flags), "rb") as stream:
        _require(_identity(os.fstat(stream.fileno())) == _identity(before), "JSON artifact changed before read")
        raw = stream.read(maximum + 1)
        _require(len(raw) <= maximum and len(raw) == before.st_size
                 and _identity(os.fstat(stream.fileno())) == _identity(before)
                 and _identity(path.lstat()) == _identity(before), "JSON artifact changed or exceeded size limit")
    return raw


def _bounded_json(path, maximum):
    raw = _bounded_bytes(path, maximum)
    try:
        return json.loads(raw.decode("utf-8"), object_pairs_hook=_pairs)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise SnapshotError("Invalid bounded JSON artifact") from exc


def _digest_file(path):
    before = path.lstat()
    _require(stat.S_ISREG(before.st_mode) and not _linked(before), "Source is not an ordinary file")
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    digest = hashlib.sha256()
    size = 0
    with os.fdopen(os.open(path, flags), "rb") as stream:
        _require(_identity(os.fstat(stream.fileno())) == _identity(before), "Source changed before read")
        while block := stream.read(1024 * 1024):
            digest.update(block)
            size += len(block)
        _require(_identity(os.fstat(stream.fileno())) == _identity(before), "Source mutated during read")
    _require(_identity(path.lstat()) == _identity(before) and size == before.st_size,
             "Source mutated during read")
    return digest.hexdigest(), size, before


def _part_path(whole_sha, index):
    return f"objects/{whole_sha[:2]}/{whole_sha}.{index:06d}.bin"


def _write_parts(output, whole_sha, size, read, chunk_bytes):
    parts = []
    total = 0
    digest = hashlib.sha256()
    for index in range(max(1, (size + chunk_bytes - 1) // chunk_bytes)):
        wanted = min(chunk_bytes, size - total)
        block = read(wanted)
        _require(len(block) == wanted, "Source shortened during capture")
        name = _part_path(whole_sha, index)
        target = output / name
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("xb") as stream:
            stream.write(block)
        digest.update(block)
        total += len(block)
        parts.append({"path": name, "bytes": len(block), "sha256": hashlib.sha256(block).hexdigest()})
    _require(not read(1) and total == size and digest.hexdigest() == whole_sha,
             "Source content changed during capture")
    return {"sha256": whole_sha, "bytes": size, "parts": parts}


def _created(value):
    _require(isinstance(value, str), "Invalid creation timestamp")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise SnapshotError("Invalid creation timestamp") from exc
    _require(parsed.tzinfo is not None and parsed.utcoffset().total_seconds() == 0,
             "Creation timestamp must use UTC")
    return value


def _counts(manifest):
    objects = manifest["objects"]
    return {"roots": len(manifest["roots"]), "directories": len(manifest["directories"]),
            "files": len(manifest["files"]), "file_bytes": sum(f["bytes"] for f in manifest["files"]),
            "links": len(manifest["links"]), "exclusions": len(manifest["exclusions"]),
            "unique_objects": len(objects), "object_bytes": sum(o["bytes"] for o in objects),
            "stored_parts": sum(len(o["parts"]) for o in objects),
            "stored_bytes": sum(p["bytes"] for o in objects for p in o["parts"])}


def _catalog_path(table, index):
    return f"catalogs/{table}.{index:06d}.json"


def _write_inventory(output, manifest):
    index = dict(manifest)
    (output / "catalogs").mkdir(exist_ok=True)
    for table in TABLES:
        references, pending = [], []
        header = ('{"schema":"hpc-forest-full-snapshot-table-v1","table":' + json.dumps(table) + ',"items":[').encode()
        pending_bytes = len(header) + 3

        def flush(table=table, header=header, references=references):
            nonlocal pending, pending_bytes
            if not pending:
                return
            raw = header + b",".join(pending) + b"]}\n"
            name = _catalog_path(table, len(references))
            with (output / name).open("xb") as stream:
                stream.write(raw)
            references.append({"path": name, "bytes": len(raw),
                               "sha256": hashlib.sha256(raw).hexdigest(), "count": len(pending)})
            pending, pending_bytes = [], len(header) + 3

        for item in manifest[table]:
            raw_item = json.dumps(item, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode("utf-8")
            _require(len(header) + len(raw_item) + 3 <= MAX_CATALOG_BYTES, "Single catalog record is too large")
            if len(pending) >= manifest["catalog_entries"] or pending_bytes + len(raw_item) + bool(pending) > MAX_CATALOG_BYTES:
                flush()
            pending_bytes += len(raw_item) + bool(pending)
            pending.append(raw_item)
        flush()
        index[table] = references
    raw_index = _dump(index)
    _require(len(raw_index) <= MAX_CATALOG_BYTES, "Inventory index is too large")
    with (output / "INVENTORY.json").open("xb") as stream:
        stream.write(raw_index)


def _read_inventory(snapshot, index):
    """Resolve authenticated catalog pages without exposing source locations."""
    manifest = dict(index)
    expected = {"INVENTORY.json"}
    entries = index["catalog_entries"]
    _require(_integer(entries, 1) and entries <= DEFAULT_CATALOG_ENTRIES, "Invalid catalog entry limit")
    for table in TABLES:
        references = index[table]
        _require(isinstance(references, list), "Invalid catalog reference list")
        items = []
        for number, reference in enumerate(references):
            _keys(reference, {"path", "bytes", "sha256", "count"})
            name = _relative(reference["path"])
            _require(name == _catalog_path(table, number) and name not in expected, "Invalid catalog path")
            _require(_integer(reference["bytes"], 1) and reference["bytes"] <= MAX_CATALOG_BYTES
                     and _sha(reference["sha256"]) and _integer(reference["count"], 1)
                     and reference["count"] <= entries, "Invalid catalog reference")
            target = snapshot / name
            _unlinked_ancestors(target)
            _require(target.is_file() and target.stat().st_size == reference["bytes"], "Missing or changed catalog")
            raw = _bounded_bytes(target, MAX_CATALOG_BYTES)
            _require(len(raw) == reference["bytes"] and hashlib.sha256(raw).hexdigest() == reference["sha256"],
                     "Corrupt catalog")
            try:
                value = json.loads(raw.decode("utf-8"), object_pairs_hook=_pairs)
            except (UnicodeError, json.JSONDecodeError) as exc:
                raise SnapshotError("Invalid catalog JSON") from exc
            _keys(value, {"schema", "table", "items"})
            _require(value["schema"] == "hpc-forest-full-snapshot-table-v1" and value["table"] == table
                     and isinstance(value["items"], list) and len(value["items"]) == reference["count"], "Invalid catalog contents")
            items.extend(value["items"])
            expected.add(name)
        manifest[table] = items
    return manifest, expected


def _validate_plan(plan):
    required = {"schema", "roots", "runtime_excluded_basenames", "exclude_directory_names", "chunk_bytes"}
    _require(isinstance(plan, dict) and required <= set(plan) <= required | {"created_at_utc", "catalog_entries"},
             "Invalid build plan fields")
    _require(plan["schema"] == PLAN_SCHEMA and isinstance(plan["roots"], list) and plan["roots"],
             "Invalid build plan schema or roots")
    _require(_integer(plan["chunk_bytes"], 1) and plan["chunk_bytes"] <= MAX_CHUNK_BYTES,
             "Chunk size must be between 1 and 40 MiB")
    _require(_integer(plan.get("catalog_entries", DEFAULT_CATALOG_ENTRIES), 1)
             and plan.get("catalog_entries", DEFAULT_CATALOG_ENTRIES) <= DEFAULT_CATALOG_ENTRIES, "Invalid catalog entry limit")
    for key in ("runtime_excluded_basenames", "exclude_directory_names"):
        names = plan[key]
        _require(isinstance(names, list) and all(isinstance(n, str) and n and "/" not in n
                 and "\\" not in n and n not in {".", ".."} for n in names), "Invalid exclusion names")
        _require(len({n.casefold() for n in names}) == len(names), "Duplicate exclusion names")
    ids = set()
    locations = set()
    for root in plan["roots"]:
        _keys(root, {"id", "path", "label", "exclude_prefixes"})
        key = _root_id(root["id"]).casefold()
        _require(key not in ids, "Duplicate root ID")
        ids.add(key)
        _require(isinstance(root["label"], str) and root["label"], "Invalid root label")
        _require(isinstance(root["path"], str) and Path(root["path"]).is_absolute(), "Source root must be absolute")
        source = Path(root["path"])
        _unlinked_ancestors(source)
        _require(source.is_dir(), "Source root must be a directory")
        location = _location_hash(source)
        _require(location not in locations, "Duplicate source root")
        locations.add(location)
        prefixes = root["exclude_prefixes"]
        _require(isinstance(prefixes, list), "Invalid excluded prefixes")
        for prefix in prefixes:
            _relative(prefix)
        _require(len({p.casefold() for p in prefixes}) == len(prefixes), "Duplicate excluded prefixes")


def build(plan_path: Path, output: Path):
    """Build a new snapshot from an explicit plan; never overwrite or execute."""
    plan_path, output = Path(plan_path), Path(output)
    _require(plan_path.is_absolute() and output.is_absolute(), "Plan and output must be absolute")
    plan = _json(plan_path)
    _validate_plan(plan)
    _unlinked_ancestors(output)
    _require(not output.exists(), "Output already exists")
    for root in plan["roots"]:
        source = Path(root["path"]).resolve()
        if output.resolve().is_relative_to(source):
            relative = output.resolve().relative_to(source).as_posix().casefold()
            _require(any(relative == p.casefold() or relative.startswith(p.casefold() + "/")
                         for p in root["exclude_prefixes"]), "Output inside a source must be explicitly excluded")
    output.mkdir(parents=True, exist_ok=False)
    manifest = {"schema": SCHEMA, "created_at_utc": _created(plan.get("created_at_utc")
                or datetime.now(UTC).isoformat()), "chunk_bytes": plan["chunk_bytes"],
                "catalog_entries": plan.get("catalog_entries", DEFAULT_CATALOG_ENTRIES),
                "roots": [], "directories": [], "files": [], "links": [], "exclusions": [], "objects": []}
    objects = {}
    observed = []
    directories = []
    names = {}

    def register(root_id, relative):
        for index in range(1, len(relative.split("/")) + 1):
            prefix = "/".join(relative.split("/")[:index])
            key = (root_id.casefold(), prefix.casefold())
            _require(key not in names or names[key] == prefix, "Windows path case collision")
            names[key] = prefix

    for root in plan["roots"]:
        root_id, source = root["id"], Path(root["path"])
        manifest["roots"].append({"id": root_id, "label": root["label"],
                                  "source_path_sha256": _location_hash(source)})
        prefixes = [p.casefold() for p in root["exclude_prefixes"]]
        runtime = {n.casefold() for n in plan["runtime_excluded_basenames"]}
        excluded_dirs = {n.casefold() for n in plan["exclude_directory_names"]}

        def walk(folder, source=source, root_id=root_id, prefixes=prefixes,
                 runtime=runtime, excluded_dirs=excluded_dirs):
            info = folder.lstat()
            _require(stat.S_ISDIR(info.st_mode) and not _linked(info), "Directory became a link")
            entries = sorted(folder.iterdir(), key=lambda p: p.name)
            directories.append((folder, _identity(info), tuple(p.name for p in entries)))
            for path in entries:
                relative = _relative(path.relative_to(source).as_posix())
                register(root_id, relative)
                current = path.lstat()
                kind = "link" if _linked(current) else "directory" if stat.S_ISDIR(current.st_mode) else "file"
                folded = relative.casefold()
                reason = None
                if any(folded == p or folded.startswith(p + "/") for p in prefixes):
                    reason = "excluded-prefix"
                elif path.name.casefold() in runtime:
                    reason = "runtime-excluded-basename"
                elif kind == "directory" and path.name.casefold() in excluded_dirs:
                    reason = "excluded-directory-name"
                if reason:
                    manifest["exclusions"].append({"root": root_id, "path": relative, "kind": kind, "reason": reason})
                    continue
                if kind == "link":
                    try:
                        target = os.readlink(path)
                    except OSError:
                        target = None
                    payload = _dump({"target": target, "reparse_tag": getattr(current, "st_reparse_tag", None)})
                    _require(len(payload) <= MAX_LINK_DESCRIPTOR_BYTES, "Link descriptor is too large")
                    digest = hashlib.sha256(payload).hexdigest()
                    if digest not in objects:
                        import io
                        objects[digest] = _write_parts(output, digest, len(payload), io.BytesIO(payload).read, plan["chunk_bytes"])
                    manifest["links"].append({"root": root_id, "path": relative, "kind": "link-descriptor",
                                              "bytes": len(payload), "sha256": digest})
                    observed.append((path, _identity(current), digest, "link"))
                elif kind == "directory":
                    manifest["directories"].append({"root": root_id, "path": relative})
                    walk(path)
                else:
                    digest, size, before = _digest_file(path)
                    if digest not in objects:
                        with path.open("rb") as stream:
                            _require(_identity(os.fstat(stream.fileno())) == _identity(before), "Source changed before capture")
                            objects[digest] = _write_parts(output, digest, size, stream.read, plan["chunk_bytes"])
                            _require(_identity(os.fstat(stream.fileno())) == _identity(before), "Source changed during capture")
                    _require(_identity(path.lstat()) == _identity(before), "Source changed after capture")
                    observed.append((path, _identity(before), digest, "file"))
                    manifest["files"].append({"root": root_id, "path": relative, "bytes": size, "sha256": digest})
        walk(source)
    for path, identity, digest, kind in observed:
        _require(_identity(path.lstat()) == identity, "Source changed before snapshot completed")
        if kind == "file":
            _require(_digest_file(path)[0] == digest, "Source bytes changed before snapshot completed")
        else:
            current = path.lstat()
            try:
                target = os.readlink(path)
            except OSError:
                target = None
            descriptor = _dump({"target": target, "reparse_tag": getattr(current, "st_reparse_tag", None)})
            _require(hashlib.sha256(descriptor).hexdigest() == digest, "Link target changed during capture")
    for folder, identity, members in directories:
        _require(_identity(folder.lstat()) == identity and tuple(sorted(p.name for p in folder.iterdir())) == members,
                 "Source directory changed before snapshot completed")
    manifest["objects"] = [objects[key] for key in sorted(objects)]
    manifest["counts"] = _counts(manifest)
    _write_inventory(output, manifest)
    return verify(output)


def _load_verified(snapshot):
    snapshot = Path(snapshot)
    _require(snapshot.is_absolute(), "Snapshot must be absolute")
    _unlinked_ancestors(snapshot)
    _require(snapshot.is_dir(), "Snapshot is absent")
    inventory = snapshot / "INVENTORY.json"
    _require(inventory.is_file() and not _linked(inventory.lstat()), "Missing or linked inventory")
    manifest = _bounded_json(inventory, MAX_CATALOG_BYTES)
    _keys(manifest, {"schema", "created_at_utc", "chunk_bytes", "catalog_entries", "roots", "directories", "files", "links", "exclusions", "objects", "counts"})
    _require(manifest["schema"] == SCHEMA, "Invalid snapshot schema")
    _created(manifest["created_at_utc"])
    chunk = manifest["chunk_bytes"]
    _require(_integer(chunk, 1) and chunk <= MAX_CHUNK_BYTES, "Invalid chunk size")
    manifest, expected_paths = _read_inventory(snapshot, manifest)
    for key in ("roots", "directories", "files", "links", "exclusions", "objects"):
        _require(isinstance(manifest[key], list), "Invalid inventory list")
    root_ids, locations = set(), set()
    _require(manifest["roots"], "Empty root inventory")
    for root in manifest["roots"]:
        _keys(root, {"id", "label", "source_path_sha256"})
        root_id = _root_id(root["id"])
        _require(root_id.casefold() not in {r.casefold() for r in root_ids}, "Duplicate root ID")
        _require(isinstance(root["label"], str) and root["label"] and _sha(root["source_path_sha256"]), "Invalid root metadata")
        _require(root["source_path_sha256"] not in locations, "Duplicate source location")
        root_ids.add(root_id)
        locations.add(root["source_path_sha256"])
    paths = {}
    kinds = {}
    referenced = set()
    file_sizes = {}
    for collection in ("directories", "files", "links", "exclusions"):
        for item in manifest[collection]:
            required = {"root", "path"}
            if collection in {"files", "links"}:
                required |= {"bytes", "sha256"}
            if collection == "links":
                required.add("kind")
            if collection == "exclusions":
                required |= {"kind", "reason"}
            _keys(item, required)
            _require(isinstance(item["root"], str) and item["root"] in root_ids, "Unknown source root")
            name = _relative(item["path"])
            key = (item["root"].casefold(), name.casefold())
            _require(key not in kinds, "Duplicate or conflicting source path")
            kinds[key] = collection
            for index in range(1, len(name.split("/")) + 1):
                prefix = "/".join(name.split("/")[:index])
                prefix_key = (item["root"].casefold(), prefix.casefold())
                _require(prefix_key not in paths or paths[prefix_key] == prefix, "Windows path case collision")
                paths[prefix_key] = prefix
            if collection in {"files", "links"}:
                _require(_sha(item["sha256"]) and _integer(item["bytes"]), "Invalid content reference")
                referenced.add(item["sha256"])
                _require(item["sha256"] not in file_sizes or file_sizes[item["sha256"]] == item["bytes"], "Conflicting object sizes")
                file_sizes[item["sha256"]] = item["bytes"]
            if collection == "links":
                _require(item["kind"] == "link-descriptor" and item["bytes"] <= MAX_LINK_DESCRIPTOR_BYTES,
                         "Invalid link descriptor kind or size")
            if collection == "exclusions":
                _require(item["kind"] in {"file", "directory", "link"} and item["reason"] in {
                    "excluded-prefix", "runtime-excluded-basename", "excluded-directory-name"}, "Invalid exclusion")
    for root_id, name in kinds:
        for parent in PurePosixPath(name).parents:
            if str(parent) != ".":
                _require(kinds.get((root_id, str(parent))) == "directories", "Missing directory or non-directory ancestor")
    object_ids = set()
    for obj in manifest["objects"]:
        _keys(obj, {"sha256", "bytes", "parts"})
        digest, size = obj["sha256"], obj["bytes"]
        _require(_sha(digest) and digest not in object_ids and digest in referenced and _integer(size), "Orphan or duplicate object")
        _require(file_sizes[digest] == size, "Object reference size mismatch")
        object_ids.add(digest)
        parts = obj["parts"]
        _require(isinstance(parts, list) and len(parts) == max(1, (size + chunk - 1) // chunk), "Invalid object part count")
        whole, total = hashlib.sha256(), 0
        for index, part in enumerate(parts):
            _keys(part, {"path", "bytes", "sha256"})
            wanted = min(chunk, size - total)
            name = _relative(part["path"])
            _require(name == _part_path(digest, index) and _integer(part["bytes"]) and part["bytes"] == wanted
                     and _sha(part["sha256"]), "Invalid object part metadata")
            _require(name not in expected_paths, "Duplicate object part")
            expected_paths.add(name)
            target = snapshot / name
            _unlinked_ancestors(target)
            _require(target.is_file(), "Missing object part")
            actual_sha, actual_size, _ = _digest_file(target)
            _require(actual_sha == part["sha256"] and actual_size == wanted, "Corrupt object part")
            with target.open("rb") as stream:
                while block := stream.read(1024 * 1024):
                    whole.update(block)
            total += wanted
        _require(total == size and whole.hexdigest() == digest, "Corrupt whole object")
    _require(object_ids == referenced, "Missing content objects")
    actual_paths = set()
    expected_directories = set()
    for name in expected_paths:
        expected_directories.update(str(p) for p in PurePosixPath(name).parents if str(p) != ".")
    for folder, dirs, files in os.walk(snapshot, followlinks=False):
        for name in [*dirs, *files]:
            target = Path(folder) / name
            _require(not _linked(target.lstat()), "Linked snapshot entry")
            if target.is_dir():
                relative = target.relative_to(snapshot).as_posix()
                _require(relative in expected_directories, "Orphan snapshot directory")
            else:
                actual_paths.add(target.relative_to(snapshot).as_posix())
    _require(actual_paths == expected_paths, "Unlisted snapshot files")
    _require(isinstance(manifest["counts"], dict) and manifest["counts"] == _counts(manifest)
             and all(_integer(v) for v in manifest["counts"].values()), "Invalid inventory counts")
    _link_descriptors(snapshot, manifest)
    return manifest


def verify(snapshot: Path = DEFAULT_SNAPSHOT):
    """Read-only validation of every part, object, path and declared count."""
    return dict(_load_verified(Path(snapshot))["counts"])


def _object_bytes(snapshot, obj):
    return b"".join(_bounded_bytes(snapshot / p["path"], p["bytes"]) for p in obj["parts"])


def _link_descriptors(snapshot, manifest):
    objects = {o["sha256"]: o for o in manifest["objects"]}
    links = []
    for item in manifest["links"]:
        try:
            descriptor = json.loads(_object_bytes(snapshot, objects[item["sha256"]]).decode("utf-8"), object_pairs_hook=_pairs)
        except (UnicodeError, json.JSONDecodeError) as exc:
            raise SnapshotError("Invalid link payload") from exc
        _keys(descriptor, {"target", "reparse_tag"})
        _require(descriptor["target"] is None or isinstance(descriptor["target"], str), "Invalid link target metadata")
        _require(descriptor["reparse_tag"] is None or _integer(descriptor["reparse_tag"]), "Invalid reparse metadata")
        links.append({"root": item["root"], "path": item["path"], **descriptor})
    return links


def restore(snapshot: Path, destination: Path, root_ids=None):
    """Verify everything before creating a new destination; links stay inert."""
    snapshot, destination = Path(snapshot), Path(destination)
    manifest = _load_verified(snapshot)
    _require(destination.is_absolute(), "Destination must be absolute")
    _unlinked_ancestors(destination)
    _require(not destination.exists(), "Destination already exists")
    resolved = destination.resolve()
    _require(not resolved.is_relative_to(snapshot.resolve()), "Destination is inside snapshot")
    source_hashes = {r["source_path_sha256"] for r in manifest["roots"]}
    _require(not any(_location_hash(p) in source_hashes for p in [resolved, *resolved.parents]),
             "Destination is inside an original source")
    available = {r["id"] for r in manifest["roots"]}
    selected = available if root_ids is None else set(root_ids)
    _require(selected and selected <= available, "Unknown or empty root selection")
    _require(root_ids is None or len(selected) == len(root_ids), "Duplicate root selection")
    objects = {o["sha256"]: o for o in manifest["objects"]}
    links = [item for item in _link_descriptors(snapshot, manifest) if item["root"] in selected]
    destination.mkdir(parents=True, exist_ok=False)
    for root_id in sorted(selected):
        (destination / root_id).mkdir()
    for item in sorted(manifest["directories"], key=lambda d: (d["path"].count("/"), d["root"], d["path"])):
        if item["root"] in selected:
            (destination / item["root"] / item["path"]).mkdir()
    restored = 0
    for item in manifest["files"]:
        if item["root"] not in selected:
            continue
        target = destination / item["root"] / item["path"]
        _unlinked_ancestors(target)
        with target.open("xb") as stream:
            for part in objects[item["sha256"]]["parts"]:
                with (snapshot / part["path"]).open("rb") as source:
                    while block := source.read(1024 * 1024):
                        stream.write(block)
        digest, size, _ = _digest_file(target)
        _require(digest == item["sha256"] and size == item["bytes"], "Restored file readback differs")
        restored += 1
    with (destination / "LINKS.json").open("xb") as stream:
        stream.write(_dump({"schema": "hpc-forest-inert-link-descriptors-v1", "links_activated": False, "links": links}))
    return {"restored_files": restored, "selected_roots": len(selected), "inert_links": len(links)}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    capture = sub.add_parser("build")
    capture.add_argument("--plan", required=True, type=Path)
    capture.add_argument("--output", required=True, type=Path)
    check = sub.add_parser("verify")
    check.add_argument("--snapshot", default=DEFAULT_SNAPSHOT, type=Path)
    recover = sub.add_parser("restore")
    recover.add_argument("--snapshot", default=DEFAULT_SNAPSHOT, type=Path)
    recover.add_argument("--destination", required=True, type=Path)
    recover.add_argument("--root-id", action="append")
    args = parser.parse_args(argv)
    try:
        result = (build(args.plan, args.output) if args.command == "build" else
                  verify(args.snapshot) if args.command == "verify" else
                  restore(args.snapshot, args.destination, args.root_id))
    except (SnapshotError, OSError) as exc:
        parser.exit(1, f"Snapshot refused: {exc}\n")
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
