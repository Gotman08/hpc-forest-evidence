set -euo pipefail
export PYTHONDONTWRITEBYTECODE=1
export PYTHONPYCACHEPREFIX=/gpfs/scratch/nimarano/hpc-forest-q15-single-pilot-20261019-root-01/no-pycache-before-Q
export OPENBLAS_NUM_THREADS=1
export OMP_NUM_THREADS=4
/scratch_p/nimarano/hpc-forest-localmodels-20261015-r1/venv-r3/bin/python -B /gpfs/scratch/nimarano/hpc-forest-q15-single-pilot-20261019-root-01/package/qualify15.py --package /gpfs/scratch/nimarano/hpc-forest-q15-single-pilot-20261019-root-01/package --plan /gpfs/scratch/nimarano/hpc-forest-q15-single-pilot-20261019-root-01/package/PLAN-Q15.json --plan-sha256 7e6b90fe3f50190b42eb3cd02f902802e4d87deb83d3080329fe248e46fe6c49 --output /gpfs/scratch/nimarano/hpc-forest-q15-single-pilot-20261019-root-01/result-Q15 --maximum-seconds 1800
