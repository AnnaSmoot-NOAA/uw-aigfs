set -euo pipefail

# Export ecFlow connection variables so ecflow_client can phone home.
export ECF_PORT=%ECF_PORT%
export ECF_HOST=%ECF_HOST%
export ECF_NAME=%ECF_NAME%
export ECF_PASS=%ECF_PASS%
export ECF_TRYNO=%ECF_TRYNO%
export ECF_RID=%ECF_RID%

ERROR() {
    set +e
    wait
    ecflow_client --ssl --abort=trap
    trap 0
    exit 0
}
trap ERROR 0
trap '{ echo "Signal received — aborting task."; ERROR; }' 1 2 3 4 5 6 7 8 10 12 13 15

# Use the Slurm job ID (not the local shell PID) so the server can identify
# batch jobs running on a different node than the one that submitted them.
ecflow_client --ssl --init=${SLURM_JOB_ID:-$$}

# Convert ecFlow repeat_datetime format (YYYYmmddTHHMMSS) to uwtools cycle format (YYYY-mm-ddTHH:MM:SS).
ISOCYCLE=$(echo "%CYCLE%" | sed -E 's/([0-9]{4})([0-9]{2})([0-9]{2})T([0-9]{2})([0-9]{2})([0-9]{2})/\1-\2-\3T\4:\5:\6/')
export ISOCYCLE
