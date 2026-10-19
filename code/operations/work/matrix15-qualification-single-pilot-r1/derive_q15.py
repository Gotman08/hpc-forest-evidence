"""Derive local Q tools with a concrete binding to the reviewed single-pilot source."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CURRENT = ROOT.parents[1]
MANIFEST = CURRENT / "outputs/HPC-Forest-Matrice15-Pilote-Unique-r1/RUNTIME-PRIVE-LOCAL.json"
PROTOCOL = CURRENT / "outputs/HPC-Forest-Matrice15-Pilote-Unique-r1/PROTOCOLE-60-CELLULES-PILOTE-UNIQUE.json"


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def data(value):
    return (json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False, separators=(",", ":")) + "\n").encode()


manifest = json.loads(MANIFEST.read_bytes())
parent_sha = sha(data(manifest))
protocol_sha = sha(PROTOCOL.read_bytes())
helper = ROOT / "qualification_contract.py"
text = helper.read_text(encoding="utf8")
assert "PARENT_RUNTIME_MANIFEST_SHA256" not in text
marker = 'SHA = re.compile(r"[0-9a-f]{64}\\Z")'
assert marker in text
text = text.replace(marker, 'PARENT_RUNTIME_MANIFEST_SHA256 = "' + parent_sha + '"\n'
                    'SINGLE_PILOT_PROTOCOL_SHA256 = "' + protocol_sha + '"\n' + marker)
text += '''

def verify_source_bindings(plan, parent_manifest_raw, q_manifest_raw):
    """Verify the declared private source before any HPC/runtime import."""
    fields = {"schema", "parent_runtime_manifest_sha256", "q_runtime_manifest_sha256",
              "single_pilot_protocol_sha256"}
    binding = plan.get("source_bindings")
    need(type(binding) is dict and set(binding) == fields
         and binding["schema"] == "hpc-forest-Q15-single-pilot-source-binding-v1"
         and binding["parent_runtime_manifest_sha256"] == PARENT_RUNTIME_MANIFEST_SHA256
         and sha(parent_manifest_raw) == PARENT_RUNTIME_MANIFEST_SHA256
         and binding["single_pilot_protocol_sha256"] == SINGLE_PILOT_PROTOCOL_SHA256
         and sha(q_manifest_raw) == binding["q_runtime_manifest_sha256"],
         "Q15 plan is not bound to the reviewed single-pilot parent and actual Q runtime")
    return copy.deepcopy(binding)
'''
helper.write_text(text, encoding="utf8", newline="\n")

prepare = ROOT / "prepare.py"
text = prepare.read_text(encoding="utf8")
old = '    parent_runtime = source_files(project)\n    runtime = dict(parent_runtime)'
assert old in text
text = text.replace(old, '    parent_runtime = source_files(project)\n'
                    '    q.need(q.sha(q.data({name: q.sha(raw) for name, raw in parent_runtime.items()}))\n'
                    '           == q.PARENT_RUNTIME_MANIFEST_SHA256, "Reviewed single-pilot source bytes required")\n'
                    '    runtime = dict(parent_runtime)')
old = '        "native_authorization": False, "native_model_calls": 0, "Controller_instances": 0,'
assert old in text
text = text.replace(old, '        "source_bindings": {"schema": "hpc-forest-Q15-single-pilot-source-binding-v1",\n'
                    '            "parent_runtime_manifest_sha256": q.PARENT_RUNTIME_MANIFEST_SHA256,\n'
                    '            "q_runtime_manifest_sha256": q.sha(payload["RUNTIME-Q-MANIFEST.json"]),\n'
                    '            "single_pilot_protocol_sha256": q.SINGLE_PILOT_PROTOCOL_SHA256},\n' + old)
prepare.write_text(text, encoding="utf8", newline="\n")

runner = ROOT / "qualify15.py"
text = runner.read_text(encoding="utf8")
old = '    sha,\n)'
assert old in text
text = text.replace(old, '    sha,\n    verify_source_bindings,\n)')
old = '    runtime_manifest_raw = (package / "RUNTIME-Q-MANIFEST.json").read_bytes()\n'
assert old in text
text = text.replace(old, old + '    source_binding = verify_source_bindings(plan,\n'
                    '        (package / "ORIGINAL-RUNTIME-MANIFEST.json").read_bytes(), runtime_manifest_raw)\n')
old = '        "allocation": allocation, "plan": plan_ref, "qualification_complete": False, "qualified_subjects": [],'
assert old in text
text = text.replace(old, old + '\n        "source_bindings": source_binding,')
runner.write_text(text, encoding="utf8", newline="\n")
print(json.dumps({"parent_manifest_sha256": parent_sha, "protocol_sha256": protocol_sha}))
