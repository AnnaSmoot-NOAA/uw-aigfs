import json
import os
from unittest.mock import patch

import grib2io  # type: ignore[import-untyped]
import numpy as np
import xarray as xr
from pytest import fixture, raises

from aigfs.strings import STR

from .grib2writer import SECTION3, Grib2Writer

# Fixtures


@fixture
def ds() -> xr.Dataset:
    """
    A minimal xarray Dataset for save_grib2 testing.
    """
    nlat, nlon = 721, 1440
    lat = np.linspace(90, -90, nlat, dtype="float32")
    lon = np.linspace(0, 359.75, nlon, dtype="float32")
    time = [np.timedelta64(6, "h")]
    level = np.array([850, 500], dtype="int32")
    ones_sfc = np.ones((1, 1, nlat, nlon), dtype="float32")
    ones_pres = np.ones((1, 1, 2, nlat, nlon), dtype="float32")
    return xr.Dataset(
        {
            STR.two_m_temperature: ([STR.batch, STR.time, STR.lat, STR.lon], ones_sfc.copy()),
            STR.geopotential: (
                [STR.batch, STR.time, STR.level, STR.lat, STR.lon],
                ones_pres.copy(),
            ),
            STR.temperature: ([STR.batch, STR.time, STR.level, STR.lat, STR.lon], ones_pres.copy()),
            STR.specific_humidity: (
                [STR.batch, STR.time, STR.level, STR.lat, STR.lon],
                ones_pres * 0.01,
            ),
            STR.total_precipitation_6hr: (
                [STR.batch, STR.time, STR.lat, STR.lon],
                ones_sfc * 0.002,
            ),
        },
        coords={
            STR.batch: [0],
            STR.time: time,
            STR.lat: lat,
            STR.lon: lon,
            STR.level: level,
        },
    )


@fixture
def json_path(tmp_path):
    table = {
        STR.temperature: {
            STR.templates: {STR.pdtn: 0, STR.drtn: 40},
            STR.attrs: {STR.discipline: 0, STR.parameter_category: 0, STR.parameter_number: 0},
        },
        STR.specific_humidity: {
            STR.templates: {STR.pdtn: 0, STR.drtn: 40},
            STR.attrs: {STR.discipline: 0, STR.parameter_category: 1, STR.parameter_number: 0},
        },
        STR.total_precipitation_6hr: {
            STR.templates: {STR.pdtn: 8, STR.drtn: 40},
            STR.attrs: {STR.discipline: 0, STR.parameter_category: 1, STR.parameter_number: 8},
        },
        STR.total_precipitation_cumsum: {
            STR.templates: {STR.pdtn: 8, STR.drtn: 40},
            STR.attrs: {STR.discipline: 0, STR.parameter_category: 1, STR.parameter_number: 8},
        },
        STR.geopotential: {
            STR.templates: {STR.pdtn: 0, STR.drtn: 40},
            STR.attrs: {STR.discipline: 0, STR.parameter_category: 3, STR.parameter_number: 5},
        },
        STR.two_m_temperature: {
            STR.templates: {STR.pdtn: 0, STR.drtn: 40},
            STR.attrs: {STR.discipline: 0, STR.parameter_category: 0, STR.parameter_number: 0},
        },
    }
    (tmp_path / STR.tables_aigfs_json).write_text(json.dumps(table))
    (tmp_path / STR.tables_aigefs_json).write_text(json.dumps(table))
    return tmp_path


@fixture
def start_date(utc):
    return utc(2025, 10, 1, 18)


@fixture
def writer(json_path, start_date):
    return Grib2Writer(start_date=start_date, case_name=STR.aigfs, json_path=json_path)


@fixture
def writer_ens(json_path, start_date):
    return Grib2Writer(start_date=start_date, case_name="aigep01", json_path=json_path)


@fixture
def writer_ens_ctrl(json_path, start_date):
    return Grib2Writer(start_date=start_date, case_name="aigec00", json_path=json_path)


# Tests


def test_drivers_utils_grib2writer_create_grib2_message_basic(utc, writer):
    msg = writer.create_grib2_message(STR.temperature, lead=6, level=85000)
    assert msg.refDate == utc(2025, 10, 1, 18, 0).replace(tzinfo=None)
    assert msg.unitOfForecastTime == 1
    assert msg.scaledValueOfFirstFixedSurface == 85000


def test_drivers_utils_grib2writer_create_grib2_message_ensemble(writer_ens):
    msg = writer_ens.create_grib2_message(STR.temperature, lead=6, level=85000)
    assert msg.perturbationNumber == 1
    assert msg.typeOfEnsembleForecast == 3
    assert msg.typeOfData == 4


def test_drivers_utils_grib2writer_create_grib2_message_ensemble_ctrl(writer_ens_ctrl):
    msg = writer_ens_ctrl.create_grib2_message(STR.temperature, lead=6, level=85000)
    assert msg.perturbationNumber == 0
    assert msg.typeOfEnsembleForecast == 1
    assert msg.typeOfData == 3


def test_drivers_utils_grib2writer_create_grib2_message_no_level(utc, writer):
    msg = writer.create_grib2_message(STR.two_m_temperature, lead=12)
    assert msg.refDate == utc(2025, 10, 1, 18, 0).replace(tzinfo=None)


def test_drivers_utils_grib2writer_create_grib2_message_precip_6hr(writer):
    # Just verify it creates without error for pdtn=8
    msg = writer.create_grib2_message(STR.total_precipitation_6hr, lead=12)
    assert msg is not None


def test_drivers_utils_grib2writer_create_grib2_message_precip_cumsum(writer):
    msg = writer.create_grib2_message(STR.total_precipitation_cumsum, lead=24)
    assert msg is not None


def test_drivers_utils_grib2writer_create_grib2_message_spfh_bad_level(writer):
    with raises(ValueError, match="not included"):
        writer.create_grib2_message(STR.specific_humidity, lead=6, level=1000)


def test_drivers_utils_grib2writer_create_grib2_message_spfh_scale_high(writer):
    msg = writer.create_grib2_message(STR.specific_humidity, lead=6, level=5000)
    assert msg.decScaleFactor == 12


def test_drivers_utils_grib2writer_create_grib2_message_spfh_scale_low(writer):
    msg = writer.create_grib2_message(STR.specific_humidity, lead=6, level=85000)
    assert msg.decScaleFactor == 8


def test_drivers_utils_grib2writer_create_grib2_message_spfh_scale_mid(writer):
    msg = writer.create_grib2_message(STR.specific_humidity, lead=6, level=25000)
    assert msg.decScaleFactor == 10


def test_drivers_utils_grib2writer_init(utc, writer):
    assert writer.case_name == STR.aigfs
    assert writer.start_date == utc(2025, 10, 1, 18)
    assert STR.temperature in writer.attrs
    assert writer.attrs[STR.temperature][STR.templates][STR.pdtn] == 0


def test_drivers_utils_grib2writer_init_aigefs(writer_ens):
    assert writer_ens.case_name == "aigep01"
    assert STR.temperature in writer_ens.attrs


def test_drivers_utils_grib2writer_init_unsupported_case(json_path, start_date):
    with raises(ValueError, match="not supported"):
        Grib2Writer(start_date=start_date, case_name="badname", json_path=json_path)


def test_drivers_utils_grib2writer_save_grib2(writer, ds, tmp_path, logcap):
    writer.save_grib2(ds, tmp_path)
    # Check output files exist:
    sfc_file = tmp_path / "aigfs.t18z.sfc.f006.grib2"
    pres_file = tmp_path / "aigfs.t18z.pres.f006.grib2"
    assert sfc_file.is_file()
    assert pres_file.is_file()
    # Read back and verify content:
    with grib2io.open(str(sfc_file)) as f:
        msgs = list(f)
    # Surface vars: 2m_temperature and total_precipitation_6hr
    assert len(msgs) == 2
    with grib2io.open(str(pres_file)) as f:
        msgs = list(f)
    # Pressure vars: geopotential, specific_humidity, temperature each with 2 levels = 6 msgs
    assert len(msgs) == 6
    assert "Writing surface variables to" in logcap.text


def test_drivers_utils_grib2writer_save_grib2_cumsum_aigfs(writer, tmp_path):
    # total_precipitation_cumsum is kept for aigfs and scaled.
    nlat, nlon = 721, 1440
    lat = np.linspace(90, -90, nlat, dtype="float32")
    lon = np.linspace(0, 359.75, nlon, dtype="float32")
    ones_sfc = np.ones((1, 1, nlat, nlon), dtype="float32")
    ds = xr.Dataset(
        {
            STR.geopotential: (
                [STR.batch, STR.time, STR.level, STR.lat, STR.lon],
                np.ones((1, 1, 1, nlat, nlon), dtype="float32"),
            ),
            STR.total_precipitation_cumsum: (
                [STR.batch, STR.time, STR.lat, STR.lon],
                ones_sfc * 0.003,
            ),
        },
        coords={
            STR.batch: [0],
            STR.time: [np.timedelta64(12, "h")],
            STR.lat: lat,
            STR.lon: lon,
            STR.level: [850],
        },
    )
    writer.save_grib2(ds, tmp_path)
    np.testing.assert_allclose(
        float(ds[STR.total_precipitation_cumsum].isel(batch=0, time=0, lat=0, lon=0)),
        3.0,
    )


def test_drivers_utils_grib2writer_save_grib2_cumsum_ensemble_dropped(writer_ens, tmp_path):
    # total_precipitation_cumsum is dropped for ensemble.
    nlat, nlon = 721, 1440
    lat = np.linspace(90, -90, nlat, dtype="float32")
    lon = np.linspace(0, 359.75, nlon, dtype="float32")
    ones_sfc = np.ones((1, 1, nlat, nlon), dtype="float32")
    ds = xr.Dataset(
        {
            STR.geopotential: (
                [STR.batch, STR.time, STR.level, STR.lat, STR.lon],
                np.ones((1, 1, 1, nlat, nlon), dtype="float32"),
            ),
            STR.total_precipitation_cumsum: (
                [STR.batch, STR.time, STR.lat, STR.lon],
                ones_sfc * 0.003,
            ),
        },
        coords={
            STR.batch: [0],
            STR.time: [np.timedelta64(12, "h")],
            STR.lat: lat,
            STR.lon: lon,
            STR.level: [850],
        },
    )
    writer_ens.save_grib2(ds, tmp_path)
    # Should have been dropped — check the sfc file has no cumsum messages:
    sfc_file = tmp_path / "aigefs.t18z.sfc.f012.grib2"
    with grib2io.open(str(sfc_file)) as f:
        msgs = list(f)
    assert len(msgs) == 0


def test_drivers_utils_grib2writer_save_grib2_deletes_old_files(writer, ds, tmp_path):
    # Old grib2 files are deleted before writing.
    sfc_file = tmp_path / "aigfs.t18z.sfc.f006.grib2"
    pres_file = tmp_path / "aigfs.t18z.pres.f006.grib2"
    sfc_file.write_text("old")
    pres_file.write_text("old")
    writer.save_grib2(ds, tmp_path)
    # Files should exist with new content (not "old"):
    assert sfc_file.read_bytes() != b"old"
    assert pres_file.read_bytes() != b"old"


def test_drivers_utils_grib2writer_save_grib2_ensemble_prefix(writer_ens, ds, tmp_path):
    writer_ens.save_grib2(ds, tmp_path)
    assert (tmp_path / "aigefs.t18z.sfc.f006.grib2").is_file()
    assert (tmp_path / "aigefs.t18z.pres.f006.grib2").is_file()


def test_drivers_utils_grib2writer_save_grib2_geopotential_scaled(writer, ds, tmp_path):
    # geopotential input is 1.0; after save_grib2 it should be divided by 9.80665
    writer.save_grib2(ds, tmp_path)
    # ds was mutated in place:
    expected = 1.0 / 9.80665
    np.testing.assert_allclose(
        float(ds[STR.geopotential].isel(batch=0, time=0, level=0, lat=0, lon=0)),
        expected,
    )


def test_drivers_utils_grib2writer_save_grib2_lat_reversed(writer, ds, tmp_path):
    # save_grib2 reverses lat internally; verify via grib2 output data orientation.
    # The input lat goes 90 -> -90. After reindex, data rows are flipped.
    nlat = ds.sizes[STR.lat]
    # Set 2m_temperature first row (lat=90) to 1.0, last row (lat=-90) to 2.0.
    ds[STR.two_m_temperature].values[0, 0, 0, :] = 1.0
    ds[STR.two_m_temperature].values[0, 0, nlat - 1, :] = 2.0
    writer.save_grib2(ds, tmp_path)
    sfc_file = tmp_path / "aigfs.t18z.sfc.f006.grib2"
    with grib2io.open(str(sfc_file)) as f:
        msgs = list(f)
        data = msgs[0].data
    # After lat reversal, the original last row (value 2.0) becomes the first row in the grib2
    # output, and the original first row (value 1.0) becomes the last row.
    np.testing.assert_allclose(data[0, :], 2.0)
    np.testing.assert_allclose(data[-1, :], 1.0)


def test_drivers_utils_grib2writer_save_grib2_levels_in_pa(writer, ds, tmp_path):
    writer.save_grib2(ds, tmp_path)
    np.testing.assert_array_equal(ds[STR.level].values, [85000, 50000])


def test_drivers_utils_grib2writer_save_grib2_precip_scaled(writer, ds, tmp_path):
    # total_precipitation_6hr input is 0.002; after save_grib2: clip(min=0) * 1000 = 2.0
    writer.save_grib2(ds, tmp_path)
    np.testing.assert_allclose(
        float(ds[STR.total_precipitation_6hr].isel(batch=0, time=0, lat=0, lon=0)),
        2.0,
    )


def test_drivers_utils_grib2writer_save_grib2_sendecf(writer, ds, tmp_path, logcap):
    # When SENDECF is set, subprocess is called.
    script = tmp_path / "setevent.sh"
    script.write_text("#!/bin/bash\nexit 0\n")
    script.chmod(0o755)
    env = {"SENDECF": "YES", "SETEVENTSH": str(script)}
    with patch.dict(os.environ, env):
        writer.save_grib2(ds, tmp_path)
    assert "Running shell subprocess" in logcap.text


def test_drivers_utils_grib2writer_save_grib2_spfh_clipped(writer, ds, tmp_path):
    # Set some specific_humidity values negative to test clipping:
    ds[STR.specific_humidity].values[0, 0, 0, 0, 0] = -0.01
    writer.save_grib2(ds, tmp_path)
    assert float(ds[STR.specific_humidity].isel(batch=0, time=0, level=0, lat=0, lon=0)) == 0.0


def test_drivers_utils_grib2writer_section3():
    # SECTION3 has expected shape and key values.
    assert SECTION3.shape == (24,)
    assert SECTION3[12] == 1440  # nlon
    assert SECTION3[13] == 721  # nlat
