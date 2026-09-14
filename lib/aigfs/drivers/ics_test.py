from itertools import product
from pathlib import Path
from textwrap import dedent
from unittest.mock import Mock, patch

import numpy as np
import xarray as xr
from iotaa import Asset, external, task
from pytest import fixture, mark, raises

from aigfs.drivers import ics
from aigfs.strings import STR

# Fixtures


@fixture
def config(tmp_path):
    return {
        STR.aigfs_ics: {
            "execution": {
                "executable": "uw execute -h",
                "batchargs": {"walltime": "00:05:00"},
            },
            STR.files_to_link: {
                "data/a.t00z.pgrb2.0p25.f000": str(tmp_path / "fh0.grib2"),
                "data/a.t00z.pgrb2.0p25.f006": str(tmp_path / "fh6.grib2"),
                "foo/bar": "/baz/quz",
            },
            STR.grib_in_config: str(tmp_path / "grib-in.yaml"),
            STR.rundir: str(tmp_path / "prep"),
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
    Path(driverobj.config[STR.grib_in_config]).write_text(dedent(content))
    d = driverobj.rundir / STR.data
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
                v: ([STR.time, STR.plevel, STR.latitude, STR.longitude], np.ones((1, 3, 1, 1)))
                for v in varnames
            }
            data_vars["_dummy"] = ([STR.level], np.zeros(1))  # to exercise drop_dims("level")
            return xr.Dataset(
                data_vars,
                coords={
                    STR.time: [time],
                    STR.plevel: np.array([200.0, 850.0, 1000.0], dtype="float64"),
                    STR.level: [0.0],
                    STR.latitude: lat,
                    STR.longitude: lon,
                },
            )

        def ds_sfc(varname: str, time: np.datetime64) -> xr.Dataset:
            return xr.Dataset(
                {varname: ([STR.time, STR.latitude, STR.longitude], np.ones((1, 1, 1)))},
                coords={STR.time: [time], STR.latitude: lat, STR.longitude: lon},
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
            if STR.HGT_surface in name:
                datasets[name] = ds_sfc(STR.HGT_surface, t0)
            elif "TMP_2_m_above_ground" in name:
                datasets[name] = ds_sfc(STR.TMP_2maboveground, t0)
            elif "PRMSL_mean_sea_level" in name:
                datasets[name] = ds_sfc(STR.PRMSL_meansealevel, t0)
            elif "VGRD.UGRD_10_m_above_ground" in name:
                ds = ds_sfc(STR.UGRD_10maboveground, t0)
                ds[STR.VGRD_10maboveground] = ds[STR.UGRD_10maboveground].copy()
                datasets[name] = ds
            elif "SPFH.VVEL" in name:
                datasets[name] = ds_atm(
                    [STR.SPFH, STR.VVEL, STR.VGRD, STR.UGRD, STR.HGT, STR.TMP], t0
                )
            elif STR.LAND_surface in name:
                datasets[name] = ds_sfc(STR.LAND_surface, t6)
            else:
                datasets[name] = ds_sfc(STR.APCP_surface, t6)
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
        STR.total_precipitation_6hr,
        STR.geopotential,
        STR.geopotential_at_surface,
        STR.land_sea_mask,
        STR.mean_sea_level_pressure,
        STR.specific_humidity,
        STR.temperature,
        STR.two_m_temperature,
        STR.u_component_of_wind,
        STR.ten_m_u_component_of_wind,
        STR.v_component_of_wind,
        STR.ten_m_v_component_of_wind,
        STR.vertical_velocity,
    ]
    for name in renamed:
        assert name in ds.data_vars
    # Original GRIB names should not be present:
    for name in [STR.HGT, STR.HGT_surface, STR.LAND_surface, STR.APCP_surface, STR.TMP, STR.SPFH]:
        assert name not in ds.data_vars
    # Coordinate types were converted:
    assert ds[STR.lat].dtype == np.float32
    assert ds[STR.lon].dtype == np.float32
    assert ds[STR.level].dtype == np.int32
    # Level values are the pressure levels:
    np.testing.assert_array_equal(ds[STR.level].values, [200, 850, 1000])
    # Time is relative (first time step is zero):
    assert ds[STR.time].values[0] == np.timedelta64(0)
    # batch dimension was added:
    assert STR.batch in ds.dims
    # datetime coordinate exists with batch dimension:
    assert STR.datetime in ds.coords
    assert STR.batch in ds[STR.datetime].dims
    # geopotential_at_surface was scaled by 9.80665 and has no time dim (selected one time):
    assert STR.time not in ds[STR.geopotential_at_surface].dims
    np.testing.assert_allclose(ds[STR.geopotential_at_surface].values.flat[0], 9.80665)
    # land_sea_mask was selected at one time (no time dim):
    assert STR.time not in ds[STR.land_sea_mask].dims
    # geopotential (on pressure levels) was scaled by 9.80665:
    np.testing.assert_allclose(ds[STR.geopotential].values.flat[0], 9.80665)
    # total_precipitation_6hr was divided by 1000 (use last time since it's from f006):
    np.testing.assert_allclose(
        float(ds[STR.total_precipitation_6hr].isel(batch=0, time=-1).values.flat[0]),
        0.001,
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


def test_drivers_AIGFSICs_provisioned_rundir(driverobj):
    node = driverobj.provisioned_rundir()
    assert node.req is None
    assert node.ready


def test_drivers_AIGFSICs_run(atask, driverobj):
    merged_netcdf_files = Mock(wraps=atask(ready=True))
    with patch.object(driverobj, "merged_netcdf_files", merged_netcdf_files):
        node = driverobj.run()
    merged_netcdf_files.assert_called_once_with()
    assert node.ready


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
    assert driverobj.driver_name() == STR.aigfs_ics


def test_drivers_AIGFSICs__ncfiles_to_cmds(varkit):
    driverobj, expected = varkit
    mapping = driverobj._ncfiles_to_cmds
    assert mapping == expected


def test_drivers_AIGFSICs__ncfiles_to_cmds__bad_grib_filenames(varkit):
    driverobj, _ = varkit
    config = driverobj._config[STR.files_to_link]
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
    assert not ok(with_set(config, [], STR.aigfs_ics))
    assert "is not of type 'object'" in logcap.text
    logcap.clear()
    # files_to_link is not required (but one of files_to_* must satisfy anyOf):
    cfg_no_link = with_del(config, STR.aigfs_ics, STR.files_to_link)
    # Without any files_to_* the anyOf still passes (it just checks pattern if present):
    assert ok(with_set(cfg_no_link, {"data/x": "/y"}, STR.aigfs_ics, STR.files_to_copy))
    assert ok(with_set(cfg_no_link, {"data/x": "/y"}, STR.aigfs_ics, STR.files_to_hardlink))


def test_drivers_ics_schema_content(config, logcap, tmp_path, validator, with_del, with_set):
    ok = validator(ics, tmp_path, "properties", STR.aigfs_ics)
    cfg = config[STR.aigfs_ics]
    # Required:
    for key in ("execution", STR.rundir, STR.grib_in_config):
        assert not ok(with_del(cfg, key))
        assert f"'{key}' is a required property" in logcap.text
        logcap.clear()
    # No additional properties:
    assert not ok(with_set(cfg, "bar", "foo"))
    assert "Additional properties are not allowed" in logcap.text
    logcap.clear()
    # Expecting a string:
    for key in (STR.rundir, STR.grib_in_config):
        assert not ok(with_set(cfg, 42, key))
        assert "is not of type 'string'" in logcap.text
        logcap.clear()
