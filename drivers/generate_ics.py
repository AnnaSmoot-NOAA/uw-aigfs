"""
A driver for generating ICS for AIGFS.
"""

from __future__ import annotations

import logging
import re
from functools import cached_property

import xarray as xr
from iotaa import Asset, collection, task
from uwtools.api.config import get_yaml_config
from uwtools.api.driver import DriverCycleBased
from uwtools.drivers.stager import FileStager
from uwtools.utils.processing import run_shell_cmd


class GenICS(DriverCycleBased, FileStager):
    """
    A driver for generating GraphCast initial conditions.
    """

    # Tasks

    @collection
    def provisioned_rundir(self):
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

    @task
    def merged_netcdf_files(self):
        """
        Open the intermediate netcdf files, process the data and write the result in a single file.
        """
        path = self.rundir / f"aigfs.t{self.cycle.strftime('%H')}z.ic.nc"
        yield f"Merged NetCDF file {path}"
        yield Asset(path, path.is_file)
        yield self.wgrib2_tasks()

        output_files = [cmd.split()[-1] for cmd in self._wgrib2_commands]

        extracted_datasets = [xr.open_dataset(f) for f in output_files]
        ds = xr.merge(extracted_datasets, compat="no_conflicts", join="outer")
        ds = ds.drop_dims("level")
        ds = ds.rename(
            {
                "latitude": "lat",
                "longitude": "lon",
                "plevel": "level",
                "HGT_surface": "geopotential_at_surface",
                "LAND_surface": "land_sea_mask",
                "PRMSL_meansealevel": "mean_sea_level_pressure",
                "TMP_2maboveground": "2m_temperature",
                "UGRD_10maboveground": "10m_u_component_of_wind",
                "VGRD_10maboveground": "10m_v_component_of_wind",
                "APCP_surface": "total_precipitation_6hr",
                "HGT": "geopotential",
                "TMP": "temperature",
                "SPFH": "specific_humidity",
                "VVEL": "vertical_velocity",
                "UGRD": "u_component_of_wind",
                "VGRD": "v_component_of_wind",
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

        # Update geopotential unit to m2/s2 by multiplying 9.80665
        ds["geopotential_at_surface"] = ds["geopotential_at_surface"] * 9.80665
        ds["geopotential"] = ds["geopotential"] * 9.80665

        # Update total_precipitation_6hr unit to (m) from (kg/m^2) by dividing it by 1000kg/m³
        ds["total_precipitation_6hr"] = ds["total_precipitation_6hr"] / 1000

        ds.to_netcdf(path)

    @collection
    def wgrib2_tasks(self):
        """
        Map wgrib2 executions to tasks to extract variables at levels.
        """
        yield "wgrib2 tasks"
        yield [self._single_shell_command(cmd) for cmd in self._wgrib2_commands]

    @task
    def _single_shell_command(self, cmd: str):
        """
        Run a shell command.
        """
        path = self.rundir / cmd.split(maxsplit=-1)[-1]
        taskname = f"Running wgrib2 command: {cmd}"
        yield taskname
        yield Asset(path, path.is_file)
        yield [self.files_copied(), self.files_hardlinked(), self.files_linked()]
        run_shell_cmd(cmd=cmd, cwd=self.rundir, taskname=taskname)

    # Public helper methods

    @classmethod
    def driver_name(cls) -> str:
        """
        Returns the name of this driver.
        """
        return "aigfs_ics"

    # Private helper methods

    @cached_property
    def _wgrib2_commands(self):
        """
        Generate wgrib2 commands for variables to extract at specified levels.
        """
        variables_to_extract = get_yaml_config(self.config["variable_extraction_yaml"])
        datadir = self.rundir / "data"
        files = set()
        for sect in ("files_to_copy", "files_to_hardlink", "files_to_link"):
            rel_paths = self.config.get(sect, [])
            for path in rel_paths:
                if path.startswith("data"):
                    files.add(self.rundir / path)
        wgrib2_commands = []
        file_pattern = r"\w*\.t(\d{2})z(\.\w*)"
        outfile_pattern = "{var}_{lev}_{hr}{ext}.nc"
        for file_extension, variable_config in variables_to_extract.items():
            matching_files = [f for f in files if f.name.endswith(file_extension)]
            for variable, var_config in variable_config.items():
                level = var_config["levels"][0]
                for grib_file in matching_files:
                    if (load_once := var_config.get("load_once")) is False:
                        continue
                    logging.info("loading %s", variable)
                    hour_match = re.match(file_pattern, grib_file.name)
                    if hour_match:
                        hour = hour_match.groups()[0]
                    else:
                        msg = "Files don't have names expected by this driver!"
                        raise ValueError(msg)
                    if load_once is True:
                        var_config["load_once"] = False
                    var = re.sub(r"[|()]", ".", variable)
                    lev = re.sub(r"[|()]", ".", level)
                    nc_file = datadir / outfile_pattern.format(
                        var=var.replace(":", ""),
                        lev=lev.replace(":", "").replace(" ", "_"),
                        hr=hour,
                        ext=file_extension,
                    )
                    num_levs = level.count("|") + 1
                    wgrib2_commands.append(
                        f"wgrib2 -nc_nlev {num_levs} {grib_file} -match '{variable}' "
                        f"-match '{level}' -netcdf {nc_file}.tmp && mv {nc_file}.tmp {nc_file}"
                    )
        return wgrib2_commands
