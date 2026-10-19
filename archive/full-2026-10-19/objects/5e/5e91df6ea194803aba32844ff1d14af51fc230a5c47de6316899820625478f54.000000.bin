set -euo pipefail
[[ -x '/scratch_p/nimarano/hpc-forest-localmodels-20261015-r1/venv-r3/bin/python' ]] || { echo 'Existing ARM Python missing' >&2; exit 70; }
[[ ! -e '/gpfs/scratch/nimarano/hpc-forest-q15-single-pilot-20261019-root-01' && ! -L '/gpfs/scratch/nimarano/hpc-forest-q15-single-pilot-20261019-root-01' ]] || { echo 'Execution root exists; no replay' >&2; exit 71; }
command -v timeout >/dev/null
command -v sha256sum >/dev/null
cd -- '/gpfs/scratch/nimarano/hpc-forest-q15-single-pilot-20261019-root-01-inputs'
printf '%s  %s\n' 'a79c6d2a80506b11f03310389e820f0d9c6467aeed778a1d78afe70b1e9da1e5' 'bootstrap_q15.py' '98cac3314d27795c0ad32a27105690392e6ff8851e82fed509c092f41777f194' 'HPC-Forest-Q15-baseline-source-r1.tar.gz' '8acdb4c7d91ffb91eee4711b581488ccf02777ff9bda528eb7383e2917638ebd' 'transfer-manifest.json' | sha256sum --check --strict
export PYTHONDONTWRITEBYTECODE=1
export PYTHONPYCACHEPREFIX='/gpfs/scratch/nimarano/hpc-forest-q15-single-pilot-20261019-root-01-bootstrap-pycache-must-remain-absent'
export OPENBLAS_NUM_THREADS=1
export OMP_NUM_THREADS=4
[[ ! -e "$PYTHONPYCACHEPREFIX" && ! -L "$PYTHONPYCACHEPREFIX" ]] || { echo 'Fresh bootstrap pycache prefix required' >&2; exit 72; }
srun --nodes=1 --ntasks=1 --cpus-per-task=4 --mem=16G --cpu-bind=cores timeout --signal=TERM --kill-after=10s 1920s '/scratch_p/nimarano/hpc-forest-localmodels-20261015-r1/venv-r3/bin/python' -I -B '/gpfs/scratch/nimarano/hpc-forest-q15-single-pilot-20261019-root-01-inputs/bootstrap_q15.py'
