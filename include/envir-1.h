module load ecflow

# Convert ecFlow repeat_datetime format (YYYYmmddTHHMMSS) to uwtools cycle format (YYYY-mm-ddTHH:MM:SS).
ISOCYCLE=$(echo "%CYCLE%" | sed -E 's/([0-9]{4})([0-9]{2})([0-9]{2})T([0-9]{2})([0-9]{2})([0-9]{2})/\1-\2-\3T\4:\5:\6/')
export ISOCYCLE
