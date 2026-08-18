from itertools import product
from pathlib import Path
from textwrap import dedent
from unittest.mock import Mock, patch

import numpy as np
import xarray as xr
from iotaa import Asset, external, task
from pytest import fixture, mark, raises

from aigfs.drivers import ics

# Fixtures


@fixture
def config(tmp_path):
    return {
        "aigfs_ics": {
            "execution": {
                "executable": "uw execute -h",
                "batchargs": {"walltime": "00:05:00"},
            },
            "files_to_link": {
                "data/a.t00z.pgrb2.0p25.f000": str(tmp_path / "fh0.grib2"),
                "data/a.t00z.pgrb2.0p25.f006": str(tmp_path / "fh6.grib2"),
                "foo/bar": "/baz/quz",
            },
            "rundir": str(tmp_path / "prep"),
            "variable_extraction_yaml": str(tmp_path / "vars.yaml"),
        }
    }


@fixture
def cycle(utc):
    return utc(2025, 10, 1, 18)


@fixture
def driverobj(config, cycle):
    return ics.AIGFSICs(
        config=config,
        cycle=cycle,
        batch=True,
        schema_file=Path(__file__).parent / "ics.jsonschema",
    )


@fixture
def varkit(driverobj):
    content = """
    ".pgrb2.0p25.f000":
      ":HGT:":
        levels:
          - ":surface:"
        load_once: true
      ":TMP:":
        levels:
          - ":2 m above ground:"
      ":PRMSL:":
        levels:
          - ":mean sea level:"
      ":VGRD|UGRD:":
        levels:
          - ":10 m above ground:"
      ":SPFH|VVEL|VGRD|UGRD|HGT|TMP:":
        levels:
          - ":(200|850|1000) mb:"
    ".pgrb2.0p25.f006":
      ":LAND:":
        levels:
          - ":surface:"
        load_once: true
      "^(597):":
        levels:
          - ":surface:"
      ":FOO:":
        levels:
          - ":surface:"
        load_once: false
    """
    Path(driverobj.config["variable_extraction_yaml"]).write_text(dedent(content))
    d = driverobj.rundir / "data"
    keys = [
        Path(f"{d}/HGT_surface_00.pgrb2.0p25.f000.nc"),
        Path(f"{d}/TMP_2_m_above_ground_00.pgrb2.0p25.f000.nc"),
        Path(f"{d}/PRMSL_mean_sea_level_00.pgrb2.0p25.f000.nc"),
        Path(f"{d}/VGRD.UGRD_10_m_above_ground_00.pgrb2.0p25.f000.nc"),
        Path(f"{d}/SPFH.VVEL.VGRD.UGRD.HGT.TMP_.200.850.1000._mb_00.pgrb2.0p25.f000.nc"),
        Path(f"{d}/LAND_surface_00.pgrb2.0p25.f006.nc"),
        Path(f"{d}/^.597._surface_00.pgrb2.0p25.f006.nc"),
    ]
    cmd = "wgrib2 -match ':%s:' -match '%s' -nc_nlev %s -netcdf {ncfile} %s/a.t00z.pgrb2.0p25.f00%s"
    vals = [
        cmd % ("surface", ":HGT:", 1, d, 0),
        cmd % ("2 m above ground", ":TMP:", 1, d, 0),
        cmd % ("mean sea level", ":PRMSL:", 1, d, 0),
        cmd % ("10 m above ground", ":VGRD|UGRD:", 1, d, 0),
        cmd % ("(200|850|1000) mb", ":SPFH|VVEL|VGRD|UGRD|HGT|TMP:", 3, d, 0),
        cmd % ("surface", ":LAND:", 1, d, 6),
        cmd % ("surface", "^(597):", 1, d, 6),
    ]
    expected = dict(zip(keys, vals, strict=True))
    return driverobj, expected


# Tests


@mark.filterwarnings("ignore:Times can't be serialized faithfully:UserWarning")
def test_drivers_AIGFSICs_merged_netcdf_files(driverobj, varkit):
    @task
    def mock_ncfiles():

        def ds_atm(varnames: list[str], time: np.datetime64) -> xr.Dataset:
            data_vars: dict = {
                v: (["time", "plevel", "latitude", "longitude"], np.ones((1, 3, 1, 1)))
                for v in varnames
            }
            data_vars["_dummy"] = (["level"], np.zeros(1))  # to exercise drop_dims("level")
            return xr.Dataset(
                data_vars,
                coords={
                    "time": [time],
                    "plevel": np.array([200.0, 850.0, 1000.0], dtype="float64"),
                    "level": [0.0],
                    "latitude": lat,
                    "longitude": lon,
                },
            )

        def ds_sfc(varname: str, time: np.datetime64) -> xr.Dataset:
            return xr.Dataset(
                {varname: (["time", "latitude", "longitude"], np.ones((1, 1, 1)))},
                coords={"time": [time], "latitude": lat, "longitude": lon},
            )

        yield "mock ncfiles"
        ncfiles = list(driverobj._ncfiles_to_cmds.keys())
        yield Asset(ncfiles, lambda: all(x.is_file() for x in ncfiles))
        yield None
        lat = np.array([90.0], dtype="float64")
        lon = np.array([0.0], dtype="float64")
        t0 = np.datetime64("2025-10-01T18:00")
        t6 = np.datetime64("2025-10-02T00:00")
        datasets: dict[str, xr.Dataset] = {}
        for ncfile in ncfiles:
            name = ncfile.name
            if "HGT_surface" in name:
                datasets[name] = ds_sfc("HGT_surface", t0)
            elif "TMP_2_m_above_ground" in name:
                datasets[name] = ds_sfc("TMP_2maboveground", t0)
            elif "PRMSL_mean_sea_level" in name:
                datasets[name] = ds_sfc("PRMSL_meansealevel", t0)
            elif "VGRD.UGRD_10_m_above_ground" in name:
                ds = ds_sfc("UGRD_10maboveground", t0)
                ds["VGRD_10maboveground"] = ds["UGRD_10maboveground"].copy()
                datasets[name] = ds
            elif "SPFH.VVEL" in name:
                datasets[name] = ds_atm(["SPFH", "VVEL", "VGRD", "UGRD", "HGT", "TMP"], t0)
            elif "LAND_surface" in name:
                datasets[name] = ds_sfc("LAND_surface", t6)
            else:
                datasets[name] = ds_sfc("APCP_surface", t6)
        for ncfile in ncfiles:
            ncfile.parent.mkdir(exist_ok=True, parents=True)
            datasets[ncfile.name].to_netcdf(ncfile)

    driverobj, _ = varkit
    with patch.object(driverobj, "ncfiles", Mock(wraps=mock_ncfiles)) as ncfiles:
        node = driverobj.merged_netcdf_files()
    assert node.ready
    ncfiles.assert_called_once_with()
    ds = xr.open_dataset(node.ref)
    # Variables were renamed from GRIB names to descriptive names:
    renamed = [
        "total_precipitation_6hr",
        "geopotential",
        "geopotential_at_surface",
        "land_sea_mask",
        "mean_sea_level_pressure",
        "specific_humidity",
        "temperature",
        "2m_temperature",
        "u_component_of_wind",
        "10m_u_component_of_wind",
        "v_component_of_wind",
        "10m_v_component_of_wind",
        "vertical_velocity",
    ]
    for name in renamed:
        assert name in ds.data_vars
    # Original GRIB names should not be present:
    for name in ["HGT", "HGT_surface", "LAND_surface", "APCP_surface", "TMP", "SPFH"]:
        assert name not in ds.data_vars
    # Coordinate types were converted:
    assert ds["lat"].dtype == np.float32
    assert ds["lon"].dtype == np.float32
    assert ds["level"].dtype == np.int32
    # Level values are the pressure levels:
    np.testing.assert_array_equal(ds["level"].values, [200, 850, 1000])
    # Time is relative (first time step is zero):
    assert ds["time"].values[0] == np.timedelta64(0)
    # batch dimension was added:
    assert "batch" in ds.dims
    # datetime coordinate exists with batch dimension:
    assert "datetime" in ds.coords
    assert "batch" in ds["datetime"].dims
    # geopotential_at_surface was scaled by 9.80665 and has no time dim (selected one time):
    assert "time" not in ds["geopotential_at_surface"].dims
    np.testing.assert_allclose(ds["geopotential_at_surface"].values.flat[0], 9.80665)
    # land_sea_mask was selected at one time (no time dim):
    assert "time" not in ds["land_sea_mask"].dims
    # geopotential (on pressure levels) was scaled by 9.80665:
    np.testing.assert_allclose(ds["geopotential"].values.flat[0], 9.80665)
    # total_precipitation_6hr was divided by 1000 (use last time since it's from f006):
    np.testing.assert_allclose(
        float(ds["total_precipitation_6hr"].isel(batch=0, time=-1).values.flat[0]), 0.001
    )
    ds.close()


def test_drivers_AIGFSICs_ncfiles(varkit):
    @external
    def mock__ncfile(path: Path, _: str):
        yield "mock _ncfile"
        yield Asset(path, lambda: True)

    driverobj, expected = varkit
    with patch.object(driverobj, "_ncfile", Mock(wraps=mock__ncfile)) as _ncfile:
        node = driverobj.ncfiles()
    assert node.ready
    for path, cmd in expected.items():
        _ncfile.assert_any_call(path, cmd)


@mark.parametrize("ready", list(product([True, False], repeat=4)))
def test_drivers_AIGFSICs_provisioned_rundir(atask, ready, driverobj, logcap):
    mocks = [Mock(wraps=atask(x)) for x in ready]
    with (
        patch.object(driverobj, "files_copied", mocks[0]) as files_copied,
        patch.object(driverobj, "files_hardlinked", mocks[1]) as files_hardlinked,
        patch.object(driverobj, "files_linked", mocks[2]) as files_linked,
        patch.object(driverobj, "runscript", mocks[3]) as runscript,
    ):
        node = driverobj.provisioned_rundir()
    assert "provisioned run directory" in logcap.text
    for x in [files_copied, files_hardlinked, files_linked, runscript]:
        x.assert_called_once_with()
    assert node.ready is all(ready)


@mark.parametrize("ready", list(product([True, False], repeat=3)))
def test_drivers_AIGFSICs__ncfile(atask, ready, driverobj, logcap):
    path = driverobj.rundir / "a.nc"
    mocks = [Mock(wraps=atask(x)) for x in ready]
    with (
        patch.object(driverobj, "files_copied", mocks[0]) as files_copied,
        patch.object(driverobj, "files_hardlinked", mocks[1]) as files_hardlinked,
        patch.object(driverobj, "files_linked", mocks[2]) as files_linked,
    ):
        node = driverobj._ncfile(path=path, cmd="touch {ncfile}")
    assert f"netCDF file {path}" in logcap.text
    for x in [files_copied, files_hardlinked, files_linked]:
        x.assert_called_once_with()
    assert node.ready is all(ready)


def test_drivers_AIGFSICs_driver_name(driverobj):
    assert driverobj.driver_name() == "aigfs_ics"


def test_drivers_AIGFSICs__ncfiles_to_cmds(varkit):
    driverobj, expected = varkit
    mapping = driverobj._ncfiles_to_cmds
    assert mapping == expected


def test_drivers_AIGFSICs__ncfiles_to_cmds__bad_grib_filenames(varkit):
    driverobj, _ = varkit
    config = driverobj._config["files_to_link"]
    key = next(iter(config))
    config[key.replace("t00z", "z00t")] = config[key]
    with raises(ValueError, match="GRIB files don't have names expected by this driver!"):
        assert driverobj._ncfiles_to_cmds


# Schema tests


def test_drivers_ics_schema(config, logcap, tmp_path, validator, with_del, with_set):
    ok = validator(ics, tmp_path)
    # Valid config passes:
    assert ok(config)
    # Top-level aigfs_ics key is required:
    assert not ok({})
    assert "'aigfs_ics' is a required property" in logcap.text
    logcap.clear()
    # Expecting an object:
    assert not ok(with_set(config, [], "aigfs_ics"))
    assert "is not of type 'object'" in logcap.text
    logcap.clear()
    # files_to_link is not required (but one of files_to_* must satisfy anyOf):
    cfg_no_link = with_del(config, "aigfs_ics", "files_to_link")
    # Without any files_to_* the anyOf still passes (it just checks pattern if present):
    assert ok(with_set(cfg_no_link, {"data/x": "/y"}, "aigfs_ics", "files_to_copy"))
    assert ok(with_set(cfg_no_link, {"data/x": "/y"}, "aigfs_ics", "files_to_hardlink"))


def test_drivers_ics_schema_content(config, logcap, tmp_path, validator, with_del, with_set):
    ok = validator(ics, tmp_path, "properties", "aigfs_ics")
    cfg = config["aigfs_ics"]
    # Required:
    for key in ("execution", "rundir", "variable_extraction_yaml"):
        assert not ok(with_del(cfg, key))
        assert f"'{key}' is a required property" in logcap.text
        logcap.clear()
    # No additional properties:
    assert not ok(with_set(cfg, "bar", "foo"))
    assert "Additional properties are not allowed" in logcap.text
    logcap.clear()
    # Expecting a string:
    for key in ("rundir", "variable_extraction_yaml"):
        assert not ok(with_set(cfg, 42, key))
        assert "is not of type 'string'" in logcap.text
        logcap.clear()
