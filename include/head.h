set -euo pipefail

# Export ecFlow connection variables so ecflow_client can phone home.
export ECF_PORT=%ECF_PORT%
export ECF_HOST=%ECF_HOST%
export ECF_NAME=%ECF_NAME%
export ECF_PASS=%ECF_PASS%
export ECF_TRYNO=%ECF_TRYNO%
export ECF_RID=%ECF_RID%
# Empty unless the server was started with SSL (e.g. via `uw ecflow server`).
export ECF_SSL=%ECF_SSL:%
SSL_FLAG=${ECF_SSL:+--ssl}

ERROR() {
    set +e
    wait
    ecflow_client $SSL_FLAG --abort=trap
    trap 0
    exit 0
}
trap ERROR 0
trap '{ echo "Signal received — aborting task."; ERROR; }' 1 2 3 4 5 6 7 8 10 12 13 15

# Use the Slurm job ID (not the local shell PID) so the server can identify
# batch jobs running on a different node than the one that submitted them.
ecflow_client $SSL_FLAG --init=${SLURM_JOB_ID:-$$}
