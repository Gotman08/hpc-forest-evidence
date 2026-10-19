"""Create one private transfer directory and concrete ROOT job arguments; no network."""
from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path
from xml.etree import ElementTree

ROOT = Path(__file__).resolve().parent
CURRENT = ROOT.parents[1]
OUTPUT = CURRENT / "outputs/HPC-Forest-Q15-Pilote-Unique-r1"
TRANSFER = OUTPUT / "transfer-root-r1"
REMOTE_INPUT = "/gpfs/scratch/nimarano/hpc-forest-q15-single-pilot-20261019-root-01-inputs"
REMOTE_ROOT = "/gpfs/scratch/nimarano/hpc-forest-q15-single-pilot-20261019-root-01"
PYTHON = "/scratch_p/nimarano/hpc-forest-localmodels-20261015-r1/venv-r3/bin/python"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def ref(path):
    return {"path": str(path), "sha256": sha(path)}


def write(path, value):
    with path.open("x", encoding="utf8", newline="\n") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write("\n")


assert not TRANSFER.exists()
TRANSFER.mkdir()
archive = OUTPUT / "HPC-Forest-Q15-baseline-source-r1.tar.gz"
bootstrap = ROOT / "bootstrap_q15.py"
for path in (archive, bootstrap):
    shutil.copyfile(path, TRANSFER / path.name)
    assert sha(path) == sha(TRANSFER / path.name)
manifest = {
    "schema": "hpc-forest-Q15-single-pilot-private-transfer-manifest-v1",
    "files": {path.name: {"sha256": sha(path), "bytes": path.stat().st_size} for path in (archive, bootstrap)},
    "remote_input_root": REMOTE_INPUT, "remote_execution_root": REMOTE_ROOT,
    "plan_sha256": "36c95aa92150239e126c95de05b596c445e20dc59d3bb68d3554ef09a7d46ad0",
    "package_manifest_sha256": "dc43083bb65d49fd477a7edcb56d675d77b7cdc9f4dfde04611e9715962baa45",
    "transfer_performed": False, "jobs_submitted": 0, "native_model_calls": 0,
}
write(TRANSFER / "transfer-manifest.json", manifest)
boot_sha, archive_sha, manifest_sha = sha(bootstrap), sha(archive), sha(TRANSFER / "transfer-manifest.json")
body = f'''set -euo pipefail
[[ -x '{PYTHON}' ]] || {{ echo 'Existing ARM Python missing' >&2; exit 70; }}
[[ ! -e '{REMOTE_ROOT}' && ! -L '{REMOTE_ROOT}' ]] || {{ echo 'Execution root exists; no replay' >&2; exit 71; }}
command -v timeout >/dev/null
command -v sha256sum >/dev/null
cd -- '{REMOTE_INPUT}'
printf '%s  %s\\n' '{boot_sha}' 'bootstrap_q15.py' '{archive_sha}' 'HPC-Forest-Q15-baseline-source-r1.tar.gz' '{manifest_sha}' 'transfer-manifest.json' | sha256sum --check --strict
export PYTHONDONTWRITEBYTECODE=1
export PYTHONPYCACHEPREFIX='{REMOTE_ROOT}-bootstrap-pycache-must-remain-absent'
export OPENBLAS_NUM_THREADS=1
export OMP_NUM_THREADS=4
[[ ! -e "$PYTHONPYCACHEPREFIX" && ! -L "$PYTHONPYCACHEPREFIX" ]] || {{ echo 'Fresh bootstrap pycache prefix required' >&2; exit 72; }}
srun --nodes=1 --ntasks=1 --cpus-per-task=4 --mem=16G --cpu-bind=cores timeout --signal=TERM --kill-after=10s 1920s '{PYTHON}' -I -B '{REMOTE_INPUT}/bootstrap_q15.py'
'''
body_path = OUTPUT / "SCRIPT-LINUX-ROOT-r1.sh"
with body_path.open("x", encoding="utf8", newline="\n") as stream:
    stream.write(body)
args = {"name": "forest-q15-single-pilot-r1", "arch": "armgpu", "nodes": 1, "ntasks_per_node": 1,
        "cpus_per_task": 4, "mem_gb": 16, "gpus_per_node": 0, "time_limit": "00:35:00",
        "workdir": "/gpfs/scratch/nimarano", "spack_packages": ["/zrtbeqke25s2vbqo4yrhsowjz7mg3pjf"],
        "command": body, "redirect_caches": False, "job_tmpdir": False}
write(OUTPUT / "JOB-PREPARE-ARGS-ROOT-r1.json", args)
tests = ROOT / "TESTS-BOOTSTRAP-r1.xml"
suite = ElementTree.parse(tests).getroot().find("testsuite")
assert suite is not None and suite.attrib["tests"] == "29" and suite.attrib["failures"] == suite.attrib["errors"] == "0"
write(OUTPUT / "BOOTSTRAP-TRANSFERT-PRET-LOCAL.json", {
    "schema": "hpc-forest-Q15-single-pilot-bootstrap-transfer-local-preparation-v1",
    "transfer_directory": str(TRANSFER), "transfer_manifest": ref(TRANSFER / "transfer-manifest.json"),
    "archive": ref(TRANSFER / archive.name), "bootstrap": ref(TRANSFER / bootstrap.name),
    "bootstrap_source": ref(bootstrap), "bootstrap_tests": {"passed": 29, "junit": ref(tests)},
    "ruff": {"exit_code": 0, "result": "All checks passed!"},
    "linux_body": ref(body_path), "job_prepare_arguments": ref(OUTPUT / "JOB-PREPARE-ARGS-ROOT-r1.json"),
    "remote_inputs": REMOTE_INPUT, "remote_execution_root": REMOTE_ROOT,
    "remote_paths_checked": False, "transfer_performed": False, "job_prepared": False,
    "job_submitted": False, "bootstrap_main_executed": False, "native_model_calls": 0,
    "cold_result_archive_expected": REMOTE_ROOT + "/result-Q15.tar.gz",
    "cold_result_sidecar_expected": REMOTE_ROOT + "/result-Q15-archive.json",
    "root_separate_from_uploaded_inputs": True,
})
print(json.dumps({"transfer_root": str(TRANSFER), "bootstrap_sha256": boot_sha,
                  "transfer_manifest_sha256": manifest_sha, "job_args": str(OUTPUT / "JOB-PREPARE-ARGS-ROOT-r1.json")}))
