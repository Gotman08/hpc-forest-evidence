"""Neutral Python fixtures: real controller closure, no scientific/model work."""
import time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from hpc_forest.backends import Generated
from hpc_forest.config import load_config
from hpc_forest.controller import Controller, create_workspace
from hpc_forest.core import BudgetExhausted, InfrastructureError, Mission
from hpc_forest.generation_admission import SCHEMA
from hpc_forest.mother import plan_for
from hpc_forest.node_harness import NodeHarness


@pytest.fixture
def config():
    """Self-contained neutral fixture, also usable by effect-blocked ARM Q."""
    value = load_config()
    value["budget"].update(search_slots=6, confirmation_slots=3,
                           wall_seconds=600, infrastructure_retries=0)
    value["schedule"].update(cycles=1, trials_per_role_per_cycle=1, integrations_per_cycle=2)
    value["protocol"].update(repetitions=2, confirmation_repetitions=2, warmups=0)
    return value


def policy(config, seconds=60):
    config["budget"].update(generation_seconds=seconds,
        generation_admission={"schema": SCHEMA, "minimum_episode_seconds": seconds})


def test_role_refusal_precedes_slot_trial_and_source_creation(config):
    config["backend"] = "codex"
    policy(config, 600)
    controller = Controller.__new__(Controller)
    controller.config = config
    controller.db = Mock()
    controller.db.get.return_value = time.time() + config["budget"]["confirmation_seconds"] + 21
    with pytest.raises(BudgetExhausted):
        controller._new_mission("A", {})
    controller.db.reserve.assert_not_called()
    controller.db.event.assert_not_called()


def test_queued_episode_rechecks_time_before_any_call_or_file(tmp_path, config):
    config["backend"] = "codex"
    config["harness"].update(enabled=True, max_attempts=3, call_token_ceiling=100)
    config["budget"].update(mission_tokens=300, confirmation_seconds=120)
    policy(config, 600)
    mission = Mission("queued", "e1:A", "t1", 1, "A", "base", None,
                      "R/A", 1, 1, str(tmp_path / "never-opened"))
    context = {"deadline": time.time() + 120 + 450}
    backend = Mock()
    generated = NodeHarness(backend).generate(mission, context, config, tmp_path)
    assert generated.tokens == 0 and generated.usage["llm_calls"] == 0
    assert generated.usage["budget_exhausted_before_invocation"] is True
    assert not generated.infrastructure_error and not generated.tokens_upper_bound
    backend.generate.assert_not_called()
    assert list(tmp_path.iterdir()) == []


def test_mother_refusal_does_not_claim_or_publish(tmp_path, config):
    policy(config, 600)
    db = Mock()
    db.get.return_value = None
    controller = SimpleNamespace(config=config, db=db, root=tmp_path)
    result = plan_for(controller, None,
        {"deadline": time.time() + config["budget"]["confirmation_seconds"] + 21}, "preparation")
    assert result == {"phase": "preparation", "status": "not_invoked_budget", "model_calls": 0}
    db.reserve.assert_not_called()
    assert list(tmp_path.iterdir()) == []


def test_late_reentry_cannot_reclassify_a_started_unknown_episode_as_zero(tmp_path, config):
    config["harness"].update(enabled=True, max_attempts=3, call_token_ceiling=100)
    config["budget"].update(mission_tokens=300)
    policy(config, 600)
    mission = Mission("already-started", "e1:A", "t1", 1, "A", "base", None,
                      "R/A", 1, 1, str(tmp_path / "unused"))
    journal = tmp_path / "logs" / mission.id / "node-harness.json"
    journal.parent.mkdir(parents=True)
    original = b'{"state":"model_call_claimed","unknown_usage":true}\n'
    journal.write_bytes(original)
    backend = Mock()
    with pytest.raises(InfrastructureError, match="never replay"):
        NodeHarness(backend).generate(mission, {"deadline": time.time() + 21}, config, tmp_path)
    assert journal.read_bytes() == original
    backend.generate.assert_not_called()


def test_budget_stop_keeps_five_real_confirmations_within_unchanged_deadline(tmp_path, config, monkeypatch):
    source, trusted = tmp_path / "source", tmp_path / "validation"
    (source / "src").mkdir(parents=True)
    (source / "src/main.py").write_text("RESULT = 7\n", encoding="utf8")
    trusted.mkdir()
    (trusted / "build.py").write_text(
        "import pathlib,shutil,sys\n"
        "b=pathlib.Path(sys.argv[2]);b.mkdir(exist_ok=True)\n"
        "shutil.copyfile(pathlib.Path(sys.argv[1])/'src/main.py',b/('solution.exe' if sys.platform=='win32' else 'solution'))\n",
        encoding="utf8")
    (trusted / "check.py").write_text(
        "import json,runpy,sys\nassert runpy.run_path(sys.argv[1])['RESULT']==7\n"
        "print(json.dumps({'correct':True,'cases':1}))\n", encoding="utf8")
    config["backend"] = "codex"
    config["roles"] = ["A"]
    config["harness"].update(enabled=True, max_attempts=3, call_token_ceiling=100)
    config["budget"].update(mission_tokens=300, confirmation_seconds=30, max_workers=1)
    config["protocol"].update(confirmation_repetitions=5, warmups=0,
        benchmark=["{python}", "-c", "pass"])
    policy(config)
    monkeypatch.setattr("hpc_forest.controller.compiler_identity", lambda: {"fixture": "python-only"})
    root = create_workspace(tmp_path / "campaign", config, source, trusted)
    backend = Mock()

    def neutral_proposal(mission, context, settings, campaign):
        (Path(mission.worktree) / "src/main.py").write_text("RESULT = 7\n# NEUTRAL fixture\n")
        return Generated(17, {"llm_calls": 1})

    backend.generate.side_effect = neutral_proposal
    with Controller(root) as controller:
        controller.backend = backend
        assert controller.run(max_batches=1)["status"] == "checkpointed"
        assert backend.generate.call_count == 1
        assert len(controller.db.rows("SELECT id FROM trials")) == 1
        # Test-only clock position; production never changes an existing deadline.
        fixed_deadline = time.time() + 45
        controller.db.set("deadline", fixed_deadline)
        stopped = controller.run()
        assert stopped["status"] == "budget_exhausted"
        assert backend.generate.call_count == 1
        assert len(controller.db.rows("SELECT id FROM trials")) == 1
        controller.confirm()
        confirmed = controller.db.evaluations("confirmation", 1)
        assert len(confirmed) == 2
        assert all(row["outcome"]["correct"] is True for row in confirmed)
        assert all(len(row["outcome"]["times"]) == 5 for row in confirmed)
        assert controller.db.get("deadline") == fixed_deadline
        assert time.time() < fixed_deadline
        assert controller.db.costs()["exact_tokens_used"] == 17
        assert controller.db.costs()["unknown_usage_calls"] == 0
        assert controller.db.get("status") == "confirmed"
