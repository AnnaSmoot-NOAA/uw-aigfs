set -euo pipefail

# Configure error handling:

ERROR() {
  set +e
  ecflow_client --abort=trap
  trap 0
  exit 0
}

trap ERROR 0
trap '{ echo "Signal received, aborting task."; ERROR; }' 1 2 3 4 5 6 7 8 10 12 13 15

# Export variables that let ecflow_client communicate with ecflow_server:

export ECF_HOST=%ECF_HOST%
export ECF_NAME=%ECF_NAME%
export ECF_PASS=%ECF_PASS%
export ECF_PORT=%ECF_PORT%
test -n "%ECF_SSL:%" && export ECF_SSL=%ECF_SSL:%
export ECF_TRYNO=%ECF_TRYNO%

# Export the appropriate ECF_RID value:

export ECF_RID=$%RID_VAR%

# Convert ecFlow repeat_datetime format (YYYYmmddTHHMMSS) to ISO8601 (YYYY-mm-ddTHH:MM:SS):

export ISOCYCLE=$(echo "%CYCLE%" | sed -E 's/([0-9]{4})([0-9]{2})([0-9]{2})T([0-9]{2})([0-9]{2})([0-9]{2})/\1-\2-\3T\4:\5:\6/')

# Inform the server that the job has started:

ecflow_client --init=$ECF_RID
