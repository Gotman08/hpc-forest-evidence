"""Local pure preparation and shell boundary checks; no native worker or model."""
import importlib.util
import json
import shlex
import subprocess
from pathlib import Path

import pytest

PATH = Path(__file__).with_name("materialize_unit.py")
spec = importlib.util.spec_from_file_location("unit_packet", PATH)
unit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(unit)
PENDING = unit.OUTPUT / "sol-count-pending-r1"
BASH = Path("C:/Program Files/Git/bin/bash.exe")
EXPECTED = {"OMP_NUM_THREADS": "4", "OMP_DYNAMIC": "FALSE", "OMP_PROC_BIND": "TRUE",
            "CUDA_VISIBLE_DEVICES": "", "PYTHONDONTWRITEBYTECODE": "1", "OPENBLAS_NUM_THREADS": "1"}


def example_body():
    builder, _upstream, _reader, _dynamic, _capacity, _bootstrap, prefix = unit.runtime()
    data = json.loads((PENDING / "INPUT-BOOTSTRAP-TEMPLATE.json").read_bytes())
    stage = data["scientific_root"] + "-bootstrap-inputs"
    result = unit.body(data, unit.ref(PENDING / "INPUT-BOOTSTRAP-TEMPLATE.json")["sha256"], stage,
        builder.BOOT_PINS["bootstrap_extension.py"], builder.PINS["extension_gate.py"], prefix)
    return data, stage, result.decode("utf8"), prefix


def test_pending_requires_real_prerequisites():
    value = json.loads((PENDING / "PREPARATION.json").read_bytes())
    assert value["operational_files_emitted"] is False
    assert value["job_prepare_arguments"] is value["upload_manifest"] is None
    assert value["native_authorization"] is False
    assert value["native_model_calls"] == value["jobs_submitted"] == 0
    assert not (PENDING / "stage").exists() and not (PENDING / "job-body.sh").exists()
    assert json.loads((PENDING / "INPUT-BOOTSTRAP-TEMPLATE.json").read_bytes())["first_batch_gate"] is None


def test_next_cell_is_exact_registered_sol_max_count():
    value = json.loads((PENDING / "PREPARATION.json").read_bytes())
    binding = value["binding_without_job_id"]
    assert binding["session_id"] == "4bb93e081ad042a185b7029f3ade2605"
    assert (binding["model"], binding["effort"], binding["subject_id"]) == ("gpt-6.1-sol", "max", "2023-count")


def test_body_reuses_shared_and_checks_exact_three_files():
    data, stage, text, _prefix = example_body()
    assert "[[ -d " + shlex.quote(data["shared_root"]) in text
    assert "Existing shared375 required" in text
    assert "tar " not in text and "mkdir" not in text
    line = next(line for line in text.splitlines() if line.startswith("printf "))
    assert all(name in line for name in ("bootstrap_extension.py", "extension_gate.py", "INPUT-BOOTSTRAP.json"))
    assert "cd -- " + shlex.quote(stage) in text


def test_unique_fresh_paths_guarded():
    data, _stage, text, _prefix = example_body()
    for target in (data["scientific_root"], data["admission_root"], data["scientific_root"] + "-bootstrap-pycache-must-remain-absent"):
        assert "[[ ! -e " + shlex.quote(target) + " && ! -L " + shlex.quote(target) + " ]]" in text


def test_exact_pinned_srun_timeout_and_python_tail():
    data, stage, text, prefix = example_body()
    lines = [line for line in text.splitlines() if line.startswith("srun ")]
    assert len(lines) == 1
    argv = shlex.split(lines[0])
    expected = prefix.argument_prefix()
    assert argv[:len(expected)] == expected
    assert argv[len(expected):len(expected) + 3] == [data["python"], "-I", "-B"]
    assert argv[len(expected) + 3:len(expected) + 6] == [stage + "/bootstrap_extension.py", "--input", stage + "/INPUT-BOOTSTRAP.json"]
    assert expected[-3:] == ["--signal=TERM", "--kill-after=10s", "3310s"]


def test_bash_syntax():
    _data, _stage, text, _prefix = example_body()
    result = subprocess.run([str(BASH), "--noprofile", "--norc", "-n"], input=text, capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr


def test_fake_srun_environment_reset_is_repaired_inside_step():
    _data, _stage, text, _prefix = example_body()
    argv = shlex.split(next(line for line in text.splitlines() if line.startswith("srun ")))
    prefix = argv[:argv.index("timeout")]
    fake = """set -euo pipefail
srun() {
  while [[ "$1" == --* ]]; do shift; done
  export OMP_NUM_THREADS=BAD OMP_DYNAMIC=BAD OMP_PROC_BIND=BAD
  export PYTHONDONTWRITEBYTECODE=BAD OPENBLAS_NUM_THREADS=BAD
  unset CUDA_VISIBLE_DEVICES
  "$@"
}
"""
    receiver = "\n".join(f"printf '%s\\t%s\\t%s\\n' '{name}' \"${{{name}+present}}\" \"${{{name}-}}\"" for name in EXPECTED)
    script = fake + shlex.join([*prefix, "/bin/bash", "--noprofile", "--norc", "-c", receiver]) + "\n"
    result = subprocess.run([str(BASH), "--noprofile", "--norc", "-c", script], capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr
    records = {}
    for line in result.stdout.splitlines():
        name, present, value = line.split("\t")
        assert name in EXPECTED and name not in records
        records[name] = value if present == "present" else None
    assert records == EXPECTED


def test_existing_output_refused():
    with pytest.raises(ValueError, match="New owned unit output"):
        unit.materialize(PENDING)


def test_unknown_cell_refused_before_emission():
    output = unit.OUTPUT / "must-remain-absent-unknown-cell"
    with pytest.raises(ValueError, match="Registered sixty-cell"):
        unit.materialize(output, "forest-r2/gpt-6.1-sol/high/2023-count/seed-23")
    assert not output.exists()


def test_unreceived_preparation_cannot_be_prerequisite():
    output = unit.OUTPUT / "must-remain-absent-incomplete-prerequisite"
    with pytest.raises(ValueError, match="Exact continuation prerequisite"):
        unit.materialize(output, prerequisite=unit.ref(PENDING / "PREPARATION.json"))
    assert not output.exists()


