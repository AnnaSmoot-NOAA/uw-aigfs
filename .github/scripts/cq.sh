set -eu
source conda/etc/profile.d/conda.sh
conda activate aigfs
set -x
make test
