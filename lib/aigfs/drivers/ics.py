import logging
import re
from collections.abc import Iterator
from functools import cached_property
from pathlib import Path

import xarray as xr
from iotaa import Asset, collection, task
from uwtools.api.config import get_yaml_config
from uwtools.api.driver import DriverCycleBased, FileStager
from uwtools.api.utils import atomic, run_shell_cmd


class AIGFSICs(DriverCycleBased, FileStager):
    """
    A driver for generating AIGFS initial conditions.
    """

    # Public tasks

    @task
    def merged_netcdf_files(self) -> Iterator:
        """
        A netCDF file comprising multiple processed intermediate netCDF files.
        """
        path = self.rundir / f"aigfs.t{self.cycle.strftime('%H')}z.ic.nc"
        yield f"Merged netCDF file {path}"
        yield Asset(path, path.is_file)
        reqs = self.ncfiles()
        yield reqs
        datasets = map(xr.open_dataset, reqs.ref)
        ds = xr.merge(datasets, compat="no_conflicts", join="outer")
        ds = ds.drop_dims("level")
        ds = ds.rename(
            {
                "APCP_surface": "total_precipitation_6hr",
                "HGT": "geopotential",
                "HGT_surface": "geopotential_at_surface",
                "LAND_surface": "land_sea_mask",
                "PRMSL_meansealevel": "mean_sea_level_pressure",
                "SPFH": "specific_humidity",
                "TMP": "temperature",
                "TMP_2maboveground": "2m_temperature",
                "UGRD": "u_component_of_wind",
                "UGRD_10maboveground": "10m_u_component_of_wind",
                "VGRD": "v_component_of_wind",
                "VGRD_10maboveground": "10m_v_component_of_wind",
                "VVEL": "vertical_velocity",
                "latitude": "lat",
                "longitude": "lon",
                "plevel": "level",
            }
        )
        ds = ds.assign_coords(datetime=ds.time)
        ds["lat"] = ds["lat"].astype("float32")
        ds["lon"] = ds["lon"].astype("float32")
        ds["level"] = ds["level"].astype("int32")
        ds["time"] = ds["time"] - ds.time[0]  # time now relative to the first time step
        ds = ds.expand_dims(dim="batch")
        ds["datetime"] = ds["datetime"].expand_dims(dim="batch")
        sfc_geop = ds["geopotential_at_surface"].squeeze("batch")
        sfc_geop = (
            sfc_geop.isel(time=1) if sfc_geop.isel(time=0).isnull().all() else sfc_geop.isel(time=0)
        )
        ds["geopotential_at_surface"] = sfc_geop
        ls_mask = ds["land_sea_mask"].squeeze("batch")
        ls_mask = (
            ls_mask.isel(time=0) if ls_mask.isel(time=1).isnull().all() else ls_mask.isel(time=1)
        )
        ds["land_sea_mask"] = ls_mask
        # Update geopotential unit to m2/s2 by multiplying 9.80665.
        ds["geopotential_at_surface"] = ds["geopotential_at_surface"] * 9.80665
        ds["geopotential"] = ds["geopotential"] * 9.80665
        # Update total_precipitation_6hr unit to (m) from (kg/m^2) by dividing it by 1000kg/m³.
        ds["total_precipitation_6hr"] = ds["total_precipitation_6hr"] / 1000
        ds.to_netcdf(path)

    @collection
    def ncfiles(self) -> Iterator:
        """
        netCDF files comprising extracted GRIB variables at various levels.
        """
        yield "netCDF files from GRIB inputs"
        yield [self._ncfile(path, cmd) for path, cmd in self._ncfiles_to_cmds.items()]

    @collection
    def provisioned_rundir(self) -> Iterator:
        """
        Run directory provisioned with all required content.
        """
        yield self.taskname("provisioned run directory")
        required = [
            self.files_copied(),
            self.files_hardlinked(),
            self.files_linked(),
            self.runscript(),
        ]
        yield required

    # Private tasks

    @task
    def _ncfile(self, path: Path, cmd: str) -> Iterator:
        taskname = f"netCDF file {path}"
        yield taskname
        yield Asset(path, path.is_file)
        yield [self.files_copied(), self.files_hardlinked(), self.files_linked()]
        with atomic(path) as tmp:
            run_shell_cmd(cmd=cmd.format(ncfile=tmp), cwd=self.rundir, taskname=taskname)

    # Public helper methods

    @classmethod
    def driver_name(cls) -> str:
        """
        Returns the name of this driver.
        """
        return "aigfs_ics"

    # Private helper methods

    @cached_property
    def _ncfiles_to_cmds(self) -> dict[Path, str]:
        """
        A mapping from netCDF file paths to the commands that create them.
        """
        datadir = self.rundir / "data"
        paths = [
            self.rundir / dst
            for section in ("files_to_copy", "files_to_hardlink", "files_to_link")
            for dst in self.config.get(section, [])
            if Path(dst).parts[0] == datadir.name
        ]
        paths = sorted(set(paths), reverse=True)
        mapping: dict[Path, str] = {}
        for suffix, cfgs in get_yaml_config(self.config["variable_extraction_yaml"]).items():
            for var, cfg in cfgs.items():
                lev = cfg["levels"][0]
                for path in filter(lambda x: x.name.endswith(suffix), paths):
                    if (load_once := cfg.get("load_once")) is False:
                        continue
                    logging.info("Loading %s", var)
                    if not (m := re.match(rf"^.*\.t(\d\d)z{suffix}$", path.name)):
                        msg = "GRIB files don't have names expected by this driver!"
                        raise ValueError(msg)
                    if load_once is True:
                        cfg["load_once"] = False
                    fmt = lambda x: re.sub(r"[|()]", ".", x).replace(":", "")
                    ncfile = datadir / "{var}_{lev}_{hh}{suffix}.nc".format(
                        var=fmt(var),
                        lev=fmt(lev).replace(" ", "_"),
                        hh=m.groups()[0],
                        suffix=suffix,
                    )
                    form = "wgrib2 -match '%s' -match '%s' -nc_nlev %s -netcdf {ncfile} %s"
                    mapping[ncfile] = form % (lev, var, lev.count("|") + 1, path)
        return mapping
