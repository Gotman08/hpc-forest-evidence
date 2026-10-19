set -euo pipefail
export PYTHONDONTWRITEBYTECODE=1
export PYTHONPYCACHEPREFIX=/scratch_p/nimarano/hpc-forest-q15-single-pilot-20261019-r1-6f30c842b161/no-pycache-before-Q
export OPENBLAS_NUM_THREADS=1
export OMP_NUM_THREADS=4
/scratch_p/nimarano/hpc-forest-localmodels-20261015-r1/venv-r3/bin/python -B /scratch_p/nimarano/hpc-forest-q15-single-pilot-20261019-r1-6f30c842b161/package/qualify15.py --package /scratch_p/nimarano/hpc-forest-q15-single-pilot-20261019-r1-6f30c842b161/package --plan /scratch_p/nimarano/hpc-forest-q15-single-pilot-20261019-r1-6f30c842b161/package/PLAN-Q15.json --plan-sha256 36c95aa92150239e126c95de05b596c445e20dc59d3bb68d3554ef09a7d46ad0 --output /scratch_p/nimarano/hpc-forest-q15-single-pilot-20261019-r1-6f30c842b161/result-Q15 --maximum-seconds 1800
