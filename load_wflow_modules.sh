scrfunc_fp=$( readlink -f "${BASH_SOURCE[0]}" )
scrfunc_dir=$( dirname "${scrfunc_fp}" )

platform=${1:?"Usage: source load_wflow_modules.sh <platform>"}

case $platform in
  ursa)
    source "${scrfunc_dir}/conda/etc/profile.d/conda.sh"
    conda activate aigfs
    ;;
  wcoss2)
    module use "${scrfunc_dir}/modulefiles"
    module load wflow_wcoss
    ;;
  *)
    echo "ERROR: Unknown platform '${platform}'. Valid options: ursa, wcoss2" >&2
    return 1
    ;;
esac
