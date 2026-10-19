"""Synthetic path/inventory gates only; no official source or executable is read."""
from __future__ import annotations

import copy
import os
from pathlib import Path

import pytest

from hpc_forest import native_matrix15 as native
from hpc_forest.core import InfrastructureError, digest, file_digest


@pytest.fixture
def directories(tmp_path):
    root = tmp_path / "NEUTRAL-knn"
    fixtures = {"source/src/fixture.txt": b"NEUTRAL non-executable metadata only", "validation/contract.json": b"{}"}
    for name, raw in fixtures.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
    prefix = "preparation/knn/frozen"
    manifest = {"files": {prefix + "/" + name: file_digest(root / name) for name in fixtures}}
    canonical = "/gpfs/NEUTRAL/prepared/" + prefix
    entries = []
    for role, suffix in (("official", ""), ("source", "/source"), ("validation", "/validation")):
        host = root if not suffix else root / suffix[1:]
        windows = str(host) if os.name == "nt" else "C:/NEUTRAL/knn" + suffix
        arm = str(host) if os.name != "nt" else "/scratch_p/NEUTRAL/knn" + suffix
        selected_prefix = prefix + suffix
        inventory = {name[len(selected_prefix) + 1:]: sha for name, sha in manifest["files"].items()
                     if name.startswith(selected_prefix + "/")}
        entries.append({"kind": "directory", "subject_id": "2022-knn", "role": role,
                        "canonical_path": canonical + suffix, "windows_path": windows, "arm_path": arm,
                        "inventory_prefix": selected_prefix, "inventory_sha256": digest(inventory)})
    aliases = {"schema": "hpc-forest-matrix15-artifact-aliases-v2", "scope_id": native.SCOPE,
               "source_zip_sha256": "1" * 64, "preparation_manifest_sha256": "3" * 64, "entries": entries}
    native.validate_aliases(aliases, "1" * 64)
    return root, canonical, manifest, aliases


def resolve(case, role="official", *, verify=True):
    _, canonical, manifest, aliases = case
    return native.directory_artifact(canonical + ("" if role == "official" else "/" + role),
        subject_id="2022-knn", role=role, preparation_manifest=manifest,
        preparation_manifest_sha256="3" * 64, aliases=aliases, verify=verify)


@pytest.mark.parametrize("role", ["official", "source", "validation"])
def test_explicit_directory_roles_preserve_actual_2022_knn_slug(directories, role):
    root, canonical, _, _ = directories
    path, inventory = resolve(directories, role)
    assert path == (root if role == "official" else root / role)
    assert inventory and "/2022-knn/" not in canonical


@pytest.mark.parametrize("mutation", ["extra", "missing", "changed", "extra_empty_directory"])
def test_exact_membership_rejects_changed_missing_or_extra_bytes(directories, mutation):
    root, _, _, _ = directories
    if mutation == "extra":
        (root / "extra.txt").write_bytes(b"extra")
    elif mutation == "missing":
        (root / "source/src/fixture.txt").unlink()
    elif mutation == "changed":
        (root / "source/src/fixture.txt").write_bytes(b"changed")
    else:
        (root / "extra-empty").mkdir()
    with pytest.raises(InfrastructureError):
        resolve(directories)


def test_metadata_only_validation_does_not_claim_or_require_a_remote_directory(directories):
    _, canonical, manifest, aliases = directories
    projected, inventory = native.directory_artifact(canonical, subject_id="2022-knn", role="official",
        preparation_manifest=manifest, preparation_manifest_sha256="3" * 64, aliases=aliases,
        platform="arm" if os.name == "nt" else "windows", verify=False)
    assert str(projected) and inventory


@pytest.mark.parametrize("mutation", ["role", "subject", "canonical", "manifest", "inventory"])
def test_directory_alias_cannot_cross_subject_role_prefix_or_inventory(directories, mutation):
    _, canonical, manifest, aliases = directories
    if mutation == "manifest":
        aliases["preparation_manifest_sha256"] = "4" * 64
    elif mutation == "inventory":
        aliases["entries"][0]["inventory_sha256"] = "4" * 64
    elif mutation == "role":
        aliases["entries"][0]["role"] = "validation"
    elif mutation == "subject":
        aliases["entries"][0]["subject_id"] = "2022-sum"
    else:
        aliases["entries"][0]["canonical_path"] = canonical + "-similar-prefix"
    with pytest.raises(InfrastructureError):
        native.directory_artifact(canonical, subject_id="2022-knn", role="official",
            preparation_manifest=manifest, preparation_manifest_sha256="3" * 64, aliases=aliases, verify=False)


def test_aliases_reject_cross_entry_path_ambiguity(directories):
    _, _, _, aliases = directories
    extra = copy.deepcopy(aliases["entries"][0])
    extra["canonical_path"] = aliases["entries"][1]["arm_path"]
    extra["windows_path"] = "C:/NEUTRAL/other"
    extra["arm_path"] = "/scratch_p/NEUTRAL/other"
    aliases["entries"].append(extra)
    with pytest.raises(InfrastructureError):
        native.validate_aliases(aliases, "1" * 64)


def test_same_sha_at_different_explicit_files_is_not_the_same_reference(tmp_path):
    left, right = tmp_path / "left.txt", tmp_path / "right.txt"
    left.write_bytes(b"NEUTRAL same content")
    right.write_bytes(left.read_bytes())
    left_ref = {"path": str(left), "sha256": file_digest(left)}
    right_ref = {"path": str(right), "sha256": file_digest(right)}
    assert native.same_artifact_reference(left_ref, left_ref)
    assert not native.same_artifact_reference(left_ref, right_ref)


def test_directory_link_refusal_does_not_need_windows_symlink_privilege(directories, monkeypatch):
    root, _, _, _ = directories
    original = Path.is_symlink
    monkeypatch.setattr(Path, "is_symlink", lambda path: path == root / "source" or original(path))
    with pytest.raises(InfrastructureError):
        resolve(directories)
