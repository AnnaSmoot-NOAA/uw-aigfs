import json
import logging
import os
import subprocess
from datetime import datetime, timedelta
from pathlib import Path

import grib2io  # type: ignore[import-untyped]
import numpy as np
import xarray as xr
from uwtools.api.utils import atomic

SECTION3 = np.array(
    [
        0,
        1038240,
        0,
        0,
        0,
        6,
        0,
        0,
        0,
        0,
        0,
        0,
        1440,
        721,
        0,
        -1,
        90000000,
        0,
        48,
        -90000000,
        359750000,
        250000,
        250000,
        0,
    ]
)


class Grib2Writer:
    def __init__(
        self, start_date: datetime, case_name: str = "aigfs", json_path: Path | None = None
    ) -> None:
        self.case_name = case_name
        if self.case_name == "aigfs":
            assert json_path
            table_file = json_path / "tables_aigfs.json"
        elif self.case_name.startswith("aige"):
            assert json_path
            table_file = json_path / "tables_aigefs.json"
        else:
            msg = f"name {self.case_name} is not supported!"
            raise ValueError(msg)
        with table_file.open() as f:
            self.attrs = json.load(f)
        self.start_date = start_date

    def create_grib2_message(
        self, var: str, lead: int, level: int | None = None
    ) -> grib2io.Grib2Message:
        # Set duration. NOTE: the duration attr exists for all Grib2Message objects.
        # For Grib2Messages that are instantaneous, the duration is just 0.
        duration = timedelta(hours=0)
        if var == "total_precipitation_6hr":
            duration = timedelta(hours=6)
        elif var == "total_precipitation_cumsum":
            duration = timedelta(hours=lead)
        # Create GRIB2 message.
        msg = grib2io.Grib2Message(
            section3=SECTION3,
            pdtn=self.attrs[var]["templates"]["pdtn"],
            drtn=self.attrs[var]["templates"]["drtn"],
        )
        # Set GRIB2 attributes from json table.
        for k, v in self.attrs[var]["attrs"].items():
            setattr(msg, k, v)
        # Set GRIB2 attributes for ensemble members.
        if self.case_name.startswith("aige"):
            number = int(self.case_name[-2:])
            msg.perturbationNumber = number
            if "c00" in self.case_name:
                msg.typeOfEnsembleForecast = 1
                msg.typeOfData = 3
            else:
                msg.typeOfEnsembleForecast = 3
                msg.typeOfData = 4
        # Update decScaleFactor for specific humidity:
        # 12 for [5000, 10000]Pa, 10 for [15000, ..., 40000]Pa, 8 for [50000, ..., 100000]Pa
        if var == "specific_humidity":
            assert level is not None
            if level >= 5000 and level <= 10000:
                msg.decScaleFactor = 12
            elif level >= 15000 and level <= 40000:
                msg.decScaleFactor = 10
            elif level >= 50000 and level <= 100000:
                msg.decScaleFactor = 8
            else:
                msg = f"level {level} Pa is not included in this model!"
                raise ValueError(msg)
        # Set GRIB2 attributes unique to each iteration.
        msg.refDate = self.start_date
        msg.duration = duration
        msg.unitOfForecastTime = 1  # hour
        msg.leadTime = timedelta(hours=lead)
        if level is not None:
            msg.scaledValueOfFirstFixedSurface = level
        return msg

    def save_grib2(self, ds: xr.Dataset, outdir: Path) -> None:
        prefix = "aigefs" if self.case_name.startswith("aige") else "aigfs"
        # Convert geopotential to geopotential height.
        ds["geopotential"] = ds["geopotential"] / 9.80665
        # Update total_precipitation_6h unit to (kg/m^2) and set min to zero.
        if "total_precipitation_6hr" in ds:
            ds["total_precipitation_6hr"] = ds["total_precipitation_6hr"].clip(min=0) * 1000
        # Drop total_precipitation_cumsum for AIGEFS. Otherwise update unit to (kg/m^2) and set min
        # to zero.
        if "total_precipitation_cumsum" in ds:
            if self.case_name.startswith("aige"):
                ds = ds.drop_vars("total_precipitation_cumsum")
            else:
                ds["total_precipitation_cumsum"] = (
                    ds["total_precipitation_cumsum"].clip(min=0) * 1000
                )
        # Set min spfh to zero.
        if "specific_humidity" in ds:
            ds["specific_humidity"] = ds["specific_humidity"].clip(min=0)
        # Convert levels values from mb to Pa.
        ds["level"] = ds["level"] * 100  # mb to Pa
        ds = ds.squeeze(dim="batch")
        # Reverse lat.
        ds = ds.reindex(lat=ds.lat[::-1])
        # Set output GRIB2 file.
        cycle = self.start_date.hour
        lead = int((ds.time.dt.total_seconds() // 3600).values[0])
        outfile_sfc = outdir / f"{prefix}.t{cycle:02d}z.sfc.f{lead:03d}.grib2"
        outfile_pres = outdir / f"{prefix}.t{cycle:02d}z.pres.f{lead:03d}.grib2"
        # Delete the old files.
        for outfile in [outfile_sfc, outfile_pres]:
            outfile.unlink(missing_ok=True)
        logging.info("Writing surface variables to %s", outfile_sfc)
        logging.info("Writing pressure-level varibles to %s", outfile_pres)
        # Write to temporary GRIB2 files, then atomically rename them:
        with atomic(outfile_sfc) as tmp_sfc, atomic(outfile_pres) as tmp_pres:
            grib2_out_sfc = grib2io.open(tmp_sfc, mode="w")
            grib2_out_pres = grib2io.open(tmp_pres, mode="w")
            for var in sorted(ds.data_vars):
                da: xr.DataArray = ds[var]
                if "level" in da.coords:
                    for level in da.coords["level"]:
                        msg = self.create_grib2_message(var, lead, level=level)
                        msg.data = da.sel(level=level).isel(time=0).values
                        msg.pack()
                        logging.info("  %s", msg)
                        grib2_out_pres.write(msg)
                else:
                    msg = self.create_grib2_message(var, lead)
                    msg.data = da.isel(time=0).values
                    msg.pack()
                    logging.info("  %s", msg)
                    grib2_out_sfc.write(msg)
            grib2_out_sfc.close()
            grib2_out_pres.close()
        # Release post job to create index files and copy files to COM.
        if os.environ.get("SENDECF", "NO") != "NO":
            seteventsh = os.environ["SETEVENTSH"]
            cmd = [seteventsh, f"{lead:03d}"]
            logging.info("Running shell subprocess %s", cmd)
            subprocess.run(cmd, check=True)
