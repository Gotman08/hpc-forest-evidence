"""Cold checks of the real packet; no mocked positive transfer is created."""
import importlib.util
from pathlib import Path

import pytest

PATH = Path(__file__).with_name("prepare_packet.py")
spec = importlib.util.spec_from_file_location("gate_packet", PATH)
packet = importlib.util.module_from_spec(spec)
spec.loader.exec_module(packet)
PREP = packet.OWNED / "preparation-r1/PREPARATION.json"


def test_preparation_is_explicitly_pending():
    value = packet.read(PREP)
    assert value["mode"] == "PREPARE"
    assert value["verified"] is False
    assert value["local_historical_gate_semantics_passed"] is True
    assert value["missing_actual_readbacks"] == 5
    assert value["native_authorization"] is False
    assert value["native_model_calls"] == value["jobs_submitted"] == 0


def test_existing_scp_subset_revalidates():
    _b, _u, _r, dynamic, _c, _bs = packet.runtime()
    inventory_ref = packet.read(PREP)["partial_inventory"]
    inventory = packet.read(inventory_ref["path"])
    assert len(inventory["received"]) == 8
    dynamic.received_evidence(inventory_ref).recheck()


def test_incomplete_inventory_cannot_admit_gate():
    _b, _u, _r, dynamic, _c, _bs = packet.runtime()
    prepared = packet.read(PREP)
    with pytest.raises(ValueError, match="Unreceived/unlisted"):
        dynamic.verify_extension_gate(prepared["gate"], prepared["partial_inventory"])


def test_no_duplicate_or_pilot_extension_selection():
    _b, _u, _r, _dynamic, _c, _bs = packet.runtime()
    state = packet.read(packet.read(PREP)["selection_state"]["path"])
    assert len(state["records"]) == 60
    assert len({row["session_id"] for row in state["records"]}) == 60
    first = [row for row in state["records"] if row["cell_key"].startswith("forest-r2/gpt-6-luna/max/2020-quicksort/")]
    assert len(first) == 1 and first[0]["status"] == "held" and len(first[0]["evidence_refs"]) == 1
    assert sum(row["status"] == "not_started" for row in state["records"]) == 59
    assert all(row["effort"] == "max" for row in state["records"])


def test_pending_exports_exclude_private_raws():
    uploads = packet.read(packet.read(PREP)["pending_uploads"]["path"])
    assert uploads["uploaded"] is False
    names = [Path(row["local"]["path"]).name for row in uploads["ordered_members"]]
    assert names == ["RECU-PROPOSITION.json", "ROOT-REVIEW-REEL.json", "extension-gate.json"]
    assert all("AUDIT-PRIVE" not in row["local"]["path"] for row in uploads["ordered_members"])


def test_prepare_overwrite_refused():
    with pytest.raises(ValueError, match="New packet directory"):
        packet.prepare(PREP.parent)


def test_output_escape_refused(tmp_path):
    target = tmp_path / "escaped.json"
    with pytest.raises(ValueError, match="ownership"):
        packet.emit(target, {})
    assert not target.exists()


def test_relative_input_refused():
    with pytest.raises(ValueError, match="absolute"):
        packet.sized(Path("prepare_packet.py"))


def test_empty_catalog_refused_without_output(tmp_path):
    catalog = tmp_path / "empty.json"
    catalog.write_text("[]", encoding="utf8")
    destination = packet.OWNED / "must-remain-absent-empty-catalog"
    with pytest.raises(ValueError, match="five pending"):
        packet.finalize(PREP, catalog, destination)
    assert not destination.exists()


def test_existing_catalog_cannot_impersonate_new_readbacks(tmp_path):
    inventory = packet.read(packet.read(PREP)["partial_inventory"]["path"])
    catalog = tmp_path / "wrong.json"
    catalog.write_bytes(packet.raw(inventory["received"][:5]))
    destination = packet.OWNED / "must-remain-absent-wrong-catalog"
    with pytest.raises(ValueError, match="five pending"):
        packet.finalize(PREP, catalog, destination)
    assert not destination.exists()
