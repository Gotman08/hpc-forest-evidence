set -euo pipefail
[[ -x '/scratch_p/nimarano/hpc-forest-localmodels-20261015-r1/venv-r3/bin/python' ]] || { echo 'Existing ARM Python missing' >&2; exit 70; }
[[ ! -e '/gpfs/scratch/nimarano/hpc-forest-q15-single-pilot-20261019-root-01' && ! -L '/gpfs/scratch/nimarano/hpc-forest-q15-single-pilot-20261019-root-01' ]] || { echo 'Execution root exists; no replay' >&2; exit 71; }
command -v timeout >/dev/null
command -v sha256sum >/dev/null
cd -- '/gpfs/scratch/nimarano/hpc-forest-q15-single-pilot-20261019-root-01-inputs'
printf '%s  %s\n' '0a458dc8eda09b3a037b3317babf2d8359f4c062096d56d7dbf608526bd69b57' 'bootstrap_q15.py' '6f30c842b161f23719c877f70684a58b796f8f724539282a2b99756e8ccdaf9d' 'HPC-Forest-Q15-baseline-source-r1.tar.gz' '42b0151d54a811e521bfdacd816894ba0fe76573edf0067dea89696b56b765f6' 'transfer-manifest.json' | sha256sum --check --strict
export PYTHONDONTWRITEBYTECODE=1
export PYTHONPYCACHEPREFIX='/gpfs/scratch/nimarano/hpc-forest-q15-single-pilot-20261019-root-01-bootstrap-pycache-must-remain-absent'
export OPENBLAS_NUM_THREADS=1
export OMP_NUM_THREADS=4
[[ ! -e "$PYTHONPYCACHEPREFIX" && ! -L "$PYTHONPYCACHEPREFIX" ]] || { echo 'Fresh bootstrap pycache prefix required' >&2; exit 72; }
srun --nodes=1 --ntasks=1 --cpus-per-task=4 --mem=16G --cpu-bind=cores timeout --signal=TERM --kill-after=10s 1920s '/scratch_p/nimarano/hpc-forest-localmodels-20261015-r1/venv-r3/bin/python' -I -B '/gpfs/scratch/nimarano/hpc-forest-q15-single-pilot-20261019-root-01-inputs/bootstrap_q15.py'
