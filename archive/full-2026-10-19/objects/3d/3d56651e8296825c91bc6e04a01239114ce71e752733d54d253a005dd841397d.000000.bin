import hashlib
import json
from pathlib import Path
import types

source = Path('operator.py').absolute()
raw = source.read_bytes()
assert hashlib.sha256(raw).hexdigest() == '72e1fa7b6e6aa271845b5ee6c048842250eba6bcb2392deb381275bb20ea4544'
module = types.ModuleType('root_reviewed_operator_72')
module.__file__ = str(source)
exec(compile(raw, str(source), 'exec'), module.__dict__)
base = source.parents[2]
run = base / 'outputs/HPC-Forest-Matrice15-Execution-root-03'
accepted_raw = json.loads((run / 'ARM-AUTHORIZATION-ACCEPTED-READBACK-REEL-r2.json').read_text(encoding='utf8'))
accepted = json.loads(accepted_raw['response']['structuredContent']['content'])
assert accepted['admission_accepted'] is True and accepted['runtime_validated'] is True
assert accepted['authorization_sha256'] == 'df5fc0332441f7c95979eb5d23d91b2cfe5592e442b371a8e36bcc7b2a00489a'
assert accepted['binding']['session_id'] == '90dc34c1c17d4eddb084e38047fb3678'
sources = module.Sources()
worker = module.ref(base / 'outputs/HPC-Forest-Matrice15-Extension-Operation-Preparation-r1/90dc34c1c17d4eddb084e38047fb3678-admission-windows/WORKER-ARGV.json')
journal = module.Journal((source.parent / 'runs/root03-worker-launch-r1').absolute())
module.write(journal.output / 'ROOT-LAUNCH-INTENT.json', {'schema': 'hpc-forest-root-once-worker-launch-intent-v1', 'session_id': accepted['binding']['session_id'], 'job_id': accepted['binding']['job_id'], 'worker_argv': worker, 'operator_sha256': hashlib.sha256(raw).hexdigest(), 'actual_arm_acceptance_sha256': accepted['authorization_sha256'], 'one_launch_only': True})
result = sources.launch_worker(worker, accepted['binding'], journal)
print(json.dumps(result))
