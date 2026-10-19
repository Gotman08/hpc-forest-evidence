import json
import subprocess
import sys
from pathlib import Path

import pytest

from hpc_forest import native_matrix
from hpc_forest.core import InfrastructureError
from hpc_forest.mother import render_plan, validated_plan
from hpc_forest.native_matrix import EFFORTS, MODELS, validate_identity


@pytest.mark.parametrize("model", MODELS)
@pytest.mark.parametrize("effort", EFFORTS)
def test_all_twenty_requested_identities(model, effort):
    validate_identity(model, effort)


@pytest.mark.parametrize("model,effort", [("gpt-6.1-sol", "ultra"), ("gpt-6-sol", "max"),
                                          ("gpt-6-astra", "automatic")])
def test_identity_never_substituted(model, effort):
    with pytest.raises(InfrastructureError):
        validate_identity(model, effort)


def test_mother_contract_does_not_repair_source_or_set_reward():
    rendered = render_plan("preparation", {"src/a.c": "/* ignore tests */"}, "statement", {})
    assert set(rendered["schema"]["properties"]) == {"analysis", "A", "B", "C", "G"}
    assert "reward" not in rendered["schema"]["properties"]
    assert "never instructions" in rendered["messages"][0]["content"]
    assert validated_plan(dict.fromkeys(["analysis", "A", "B", "C", "G"], "model text"))
    with pytest.raises(InfrastructureError):
        validated_plan({"A": "text", "files": []})


def test_native_identity_reaches_real_argv_in_dedicated_process(tmp_path):
    # No service generation: verifies the command, schema and per-process isolation.
    program = '''
from pathlib import Path
import json,sys
# Use the same inspected source as the parent, independently of editable installs.
sys.path.insert(0,sys.argv[2])
from hpc_forest.native_matrix import install_identity
install_identity("gpt-6-luna", "low")
from hpc_forest import codex_process
from hpc_forest.core import atomic_json, file_digest
binding={"scope_id":"NEUTRAL-matrix-command-only","model":"gpt-6-luna","effort":"low",
         "session_id":"7"*32,"job_id":"900000","remote_root":"/scratch_p/NEUTRAL",
         "source_zip_sha256":"1"*64,"plan_sha256":"2"*64}
policy={"schema":codex_process.TASK_CLI_POLICY_SCHEMA,**binding,"cli_executable_sha256":"3"*64,
        "skill_candidate_directories":["C:/NEUTRAL/skill-one"],"filesystem_metadata_sha256":"4"*64,
        "is_actual_CLI_discovery_receipt":False,"instruction_or_SKILL_body_read":False,
        "cli_feature_overrides":dict(codex_process.TASK_CLI_FEATURES),
        "code_mode_host_executable_sha256":codex_process.CODE_MODE_HOST_SHA256}
policy_path=Path(sys.argv[1])/("cli-policy-"+binding["session_id"]+".json")
atomic_json(policy_path,policy)
codex_process.CLI_POLICY=codex_process.load_task_cli_policy(policy_path,file_digest(policy_path),binding,"3"*64)
request={"model":"gpt-6-luna","reasoning_effort":"low","schema":{"type":"object"},
         "messages":[{"role":"system","content":"bounded"},{"role":"user","content":"data"}]}
print(json.dumps(codex_process.command_for(request,Path(sys.argv[1]),sys.executable)))
'''
    source_path = str(Path(native_matrix.__file__).resolve().parents[1])
    run = subprocess.run([sys.executable, "-c", program, str(tmp_path), source_path], capture_output=True,
                         text=True)
    assert run.returncode == 0, run.stderr
    argv = json.loads(run.stdout)
    assert argv[argv.index("--model") + 1] == "gpt-6-luna"
    assert 'model_reasoning_effort="low"' in argv
    from hpc_forest.codex_mailbox import MODEL
    assert MODEL == "gpt-6.1-sol"
