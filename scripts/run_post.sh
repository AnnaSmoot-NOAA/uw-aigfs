#!/bin/bash
set -x

echo "Starting $0"

cycle=${ISOCYCLE:11:2}

for prod in pres sfc; do
  file=aigfs.${cycle}.${prod}.f${FH}.grib2

  echo "[$(date)]: Opening GRIB2 file"
  wgrib2 -s ${INPUTDIR}/${file} > ${INPUTDIR}/${file}.idx
  export err=$?; err_chk
  echo "[$(date)]: Index file created successfully"

done

echo "$0 completed normally"
