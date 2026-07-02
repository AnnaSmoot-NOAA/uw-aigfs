scrfunc_fp=$( readlink -f "${BASH_SOURCE[0]}" )
scrfunc_dir=$( dirname "${scrfunc_fp}" )

source ./conda/etc/profile.d/conda.sh
conda activate aigfs
