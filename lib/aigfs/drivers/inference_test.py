from itertools import product
from pathlib import Path
from unittest.mock import Mock, patch

import numpy as np
import pandas as pd
import xarray as xr
from graphcast import checkpoint, graphcast  # type: ignore[import-untyped]
from iotaa import Asset, task
from pytest import fixture, mark

from aigfs.drivers import inference

# Fixtures


@fixture
def config(tmp_path):
    return {
        "aigfs_inference": {
            "diffs_stddev_path": str(tmp_path / "diffs_stddev_by_level.nc"),
            "execution": {"executable": "uw execute -h"},
            "forecast_freq": 6,
            "forecast_length": 24,
            "ics_path": str(tmp_path / "aigfs.t18z.ic.nc"),
            "json_path": str(tmp_path / "tables"),
            "mean_path": str(tmp_path / "mean_by_level.nc"),
            "model_weights_path": str(tmp_path / "weights.npz"),
            "rundir": str(tmp_path / "run"),
            "stddev_path": str(tmp_path / "stddev_by_level.nc"),
        }
    }


@fixture
def cycle(utc):
    return utc(2025, 10, 1, 18)


@fixture
def driverobj(config, cycle):
    return inference.AIGFSInference(
        config=config,
        cycle=cycle,
        schema_file=Path(__file__).parent / "inference.jsonschema",
    )


@fixture
def ds():
    t0 = np.datetime64("2025-10-01T18:00")
    times = np.array([np.timedelta64(0, "h"), np.timedelta64(6, "h")])
    datetimes = np.array([t0, t0 + np.timedelta64(6, "h")])
    ones = np.ones((1, 2, 1))
    return xr.Dataset(
        {
            "geopotential_at_surface": (["batch", "time", "x"], ones.copy()),
            "land_sea_mask": (["batch", "time", "x"], ones.copy()),
            "pressure": (["batch", "time", "x"], ones.copy()),
            "temperature": (["batch", "time", "x"], ones.copy(), {"long_name": "temp"}),
            "total_precipitation_6hr": (["batch", "time", "x"], ones.copy()),
        },
        coords={
            "batch": [0],
            "datetime": (["batch", "time"], datetimes.reshape(1, 2)),
            "time": times,
            "x": [0],
        },
    )


@fixture
def model_config():
    return graphcast.ModelConfig(
        resolution=0.25,
        mesh_size=4,
        latent_size=32,
        gnn_msg_steps=4,
        hidden_layers=1,
        radius_query_fraction_edge_length=0.6,
    )


@fixture
def task_config():
    return graphcast.TaskConfig(
        input_variables=("t",),
        target_variables=("t",),
        forcing_variables=("f",),
        pressure_levels=(850,),
        input_duration="12h",
    )


@fixture
def weights(config, model_config, task_config):
    cp = graphcast.CheckPoint(
        params={"w": np.array([1.0, 2.0])},
        model_config=model_config,
        task_config=task_config,
        description="test",
        license="test",
    )
    with Path(config["aigfs_inference"]["model_weights_path"]).open("wb") as f:
        checkpoint.dump(f, cp)
    return cp


@fixture
def mock_mws(weights):
    @task
    def mock_mws():
        yield "mock model_weights"
        ref: list[graphcast.CheckPoint] = []
        yield Asset(ref, lambda: bool(ref))
        yield None
        ref.append(weights)

    return mock_mws


# Tests


def test_drivers_AIGFSInference_initial_conditions(driverobj, ds, logcap):
    path = Path(driverobj.config["ics_path"])
    ds.to_netcdf(path)
    node = driverobj.initial_conditions()
    assert node.ready
    ds_check(node.ref)
    assert "initial conditions" in logcap.text


def test_drivers_AIGFSInference_inputs_targets_forcings(driverobj, logcap, mock_mws):
    @task
    def ics():
        yield "mock initial_conditions"
        ref = xr.Dataset()
        yield Asset(ref, lambda: bool(ref))
        yield None
        ref.update(xr.Dataset({"temperature": (["x"], [10, 20])}))

    inputs = xr.Dataset({"input_var": (["x"], [1, 2])})
    targets = xr.Dataset({"target_var": (["x"], [3, 4])})
    forcings = xr.Dataset({"forcing_var": (["x"], [5, 6])})
    with (
        patch.object(inference.data_utils, "extract_inputs_targets_forcings") as extract,
        patch.object(driverobj, "initial_conditions", Mock(wraps=ics)),
        patch.object(driverobj, "model_weights", Mock(wraps=mock_mws)),
    ):
        extract.return_value = (inputs, targets, forcings)
        node = driverobj.inputs_targets_forcings()
    assert node.ready
    assert len(node.ref) == 3
    xr.testing.assert_identical(node.ref[0], inputs)
    xr.testing.assert_identical(node.ref[1], targets)
    xr.testing.assert_identical(node.ref[2], forcings)
    call_args = extract.call_args
    xr.testing.assert_identical(call_args[0][0], xr.Dataset({"temperature": (["x"], [10, 20])}))
    assert call_args[1]["target_lead_times"] == slice("6h", "24h")
    assert "inputs, targets, and forcings" in logcap.text


def test_drivers_AIGFSInference_normalization_stats(driverobj, logcap):
    diffs_stddev = xr.Dataset({"diffs_stddev": (["x"], [1.0])})
    mean = xr.Dataset({"mean": (["x"], [2.0])})
    stddev = xr.Dataset({"stddev": (["x"], [3.0])})
    diffs_stddev.to_netcdf(driverobj.config["diffs_stddev_path"])
    mean.to_netcdf(driverobj.config["mean_path"])
    stddev.to_netcdf(driverobj.config["stddev_path"])
    node = driverobj.normalization_stats()
    assert node.ready
    assert len(node.ref) == 3
    xr.testing.assert_identical(node.ref[0], diffs_stddev)
    xr.testing.assert_identical(node.ref[1], mean)
    xr.testing.assert_identical(node.ref[2], stddev)
    assert "normalization stats" in logcap.text


def test_drivers_AIGFSInference_model_weights(driverobj, logcap, weights):
    node = driverobj.model_weights()
    assert node.ready
    assert len(node.ref) == 1
    datasets = node.ref[0]
    np.testing.assert_array_equal(datasets.params["w"], weights.params["w"])
    assert datasets.model_config == weights.model_config
    assert datasets.task_config == weights.task_config
    assert datasets.description == weights.description
    assert datasets.license == weights.license
    assert "model weights" in logcap.text


@mark.parametrize("ready", list(product([True, False], repeat=1)))
def test_drivers_AIGFSInference_provisioned_rundir(atask, driverobj, logcap, ready):
    mocks = [Mock(wraps=atask(x)) for x in ready]
    with patch.object(driverobj, "runscript", mocks[0]) as runscript:
        node = driverobj.provisioned_rundir()
    for x in [runscript]:
        x.assert_called_once_with()
    assert node.ready is all(ready)
    assert "provisioned run directory" in logcap.text


def test_drivers_AIGFSInference_driver_name(driverobj):
    assert driverobj.driver_name() == "aigfs_inference"


def test_drivers_AIGFSInference__drop_state():
    fn = lambda **kw: (kw["a"] + kw["b"], "state")
    wrapped = inference.AIGFSInference._drop_state(fn)
    assert wrapped(a=1, b=2) == 3


def test_drivers_AIGFSInference_predictions(driverobj, ds, logcap, mock_mws, utc):

    @task
    def mock_ics():
        yield "mock initial_conditions"
        ref = xr.Dataset()
        yield Asset(ref, lambda: bool(ref))
        yield None
        ref.update(ds)
        ref.attrs.update(ds.attrs)

    @task
    def mock_itfs():
        yield "mock inputs_targets_forcings"
        ref: list[xr.Dataset] = []
        yield Asset(ref, lambda: bool(ref))
        yield None
        ref.extend([inputs, targets, forcings])

    @task
    def mock_norm():
        yield "mock normalization_stats"
        ref: list[xr.Dataset] = []
        yield Asset(ref, lambda: bool(ref))
        yield None
        ref.extend([diffs_stddev, mean, stddev])

    inputs = xr.Dataset({"input_var": (["x"], [1.0])})
    targets = xr.Dataset({"target_var": (["x"], [2.0])})
    forcings = xr.Dataset({"forcing_var": (["x"], [3.0])})
    diffs_stddev = xr.Dataset({"diffs_stddev": (["x"], [1.0])})
    mean = xr.Dataset({"mean": (["x"], [2.0])})
    stddev = xr.Dataset({"stddev": (["x"], [3.0])})
    with (
        patch.object(driverobj, "initial_conditions", Mock(wraps=mock_ics)),
        patch.object(driverobj, "inputs_targets_forcings", Mock(wraps=mock_itfs)),
        patch.object(driverobj, "model_weights", Mock(wraps=mock_mws)),
        patch.object(driverobj, "normalization_stats", Mock(wraps=mock_norm)),
        patch.object(inference, "Grib2Writer") as mock_writer_cls,
        patch.object(inference, "rollout") as mock_rollout,
        patch.object(inference, "jax") as mock_jax,
    ):
        mock_jit_result = Mock()
        mock_jax.jit.return_value = mock_jit_result
        mock_jax.random.PRNGKey.return_value = "rng"
        node = driverobj.predictions()
    assert node.ready
    assert node.ref.is_file()
    mock_writer_cls.assert_called_once_with(
        start_date=pd.to_datetime(utc(2025, 10, 2, 0).replace(tzinfo=None)),
        case_name="aigfs",
        json_path=Path(driverobj.config["json_path"]),
    )
    # rollout.chunked_prediction was called:
    mock_rollout.chunked_prediction.assert_called_once()
    rp_kw = mock_rollout.chunked_prediction.call_args
    assert rp_kw[0][0] == driverobj.rundir
    xr.testing.assert_identical(rp_kw[1]["inputs"], inputs)
    xr.testing.assert_identical(rp_kw[1]["forcings"], forcings)
    assert "predictions" in logcap.text


def test_drivers_inference__adjust_time(ds, logcap):
    # fcst_steps=4 => needs 6 time steps, ds has 2, so the if block is entered.
    ds_check(inference._adjust_time(ds=ds, fcst_steps=4, taskname="test"))
    assert "test: Updating dataset to account for forecast length" in logcap.text


def test_drivers_inference__adjust_time__noop(ds):
    # fcst_steps=0 => needs 2 time steps, ds has 2, so the if block is NOT entered.
    result = inference._adjust_time(ds=ds, fcst_steps=0, taskname="test")
    xr.testing.assert_identical(result, ds)


def test_drivers_inference__clean_ics(ds):
    result = inference._clean_ics(ds)
    # Dropped variables are gone:
    for var in ["geopotential_at_surface", "land_sea_mask", "total_precipitation_6hr"]:
        assert var not in result.data_vars
    # long_name attribute was removed:
    assert "long_name" not in result["temperature"].attrs
    # Only time index 1 was kept, and time was shifted back by 6h:
    assert len(result["time"]) == 1
    np.testing.assert_array_equal(result["time"].values, [np.timedelta64(0, "h")])


def test_drivers_inference_construct_wrapped_graphcast(model_config, task_config):
    diffs_stddev = xr.Dataset({"x": ([], 1.0)})
    mean = xr.Dataset({"x": ([], 2.0)})
    stddev = xr.Dataset({"x": ([], 3.0)})
    with patch.object(inference.graphcast, "GraphCast") as mock_gc:
        result = inference.construct_wrapped_graphcast(
            model_config, task_config, diffs_stddev, mean, stddev
        )
    # GraphCast was called with model_config and task_config:
    mock_gc.assert_called_once_with(model_config, task_config)
    # The result is an autoregressive.Predictor wrapping the composition:
    assert isinstance(result, inference.autoregressive.Predictor)


# Helpers


def ds_check(ds: xr.Dataset) -> None:
    # Should have fcst_steps + 2 = 6 time steps now:
    assert len(ds["time"]) == 6
    # Time values are 6-hourly timedeltas:
    expected_times = np.array([np.timedelta64(6 * i, "h") for i in range(6)])
    np.testing.assert_array_equal(ds["time"].values, expected_times)
    # Datetime values are absolute times starting from the original start:
    t0 = np.datetime64("2025-10-01T18:00")
    expected_datetimes = np.array([t0 + np.timedelta64(6 * i, "h") for i in range(6)])
    np.testing.assert_array_equal(ds["datetime"].to_numpy()[0], expected_datetimes)
    # Original data at existing time indices is preserved, new indices are NaN:
    assert float(ds["temperature"].isel(batch=0, time=0, x=0)) == 1.0
    assert np.isnan(float(ds["temperature"].isel(batch=0, time=2, x=0)))


# Schema tests


def test_drivers_inference_schema(config, logcap, tmp_path, validator, with_set):
    ok = validator(inference, tmp_path)
    # Valid config passes:
    assert ok(config)
    # Top-level aigfs_inference key is required:
    assert not ok({})
    assert "'aigfs_inference' is a required property" in logcap.text
    logcap.clear()
    # Expecting an object:
    assert not ok(with_set(config, [], "aigfs_inference"))
    assert "is not of type 'object'" in logcap.text
    logcap.clear()


def test_drivers_inference_schema_content(config, logcap, tmp_path, validator, with_del, with_set):
    ok = validator(inference, tmp_path, "properties", "aigfs_inference")
    cfg = config["aigfs_inference"]
    # Required:
    for key in (
        "diffs_stddev_path",
        "execution",
        "forecast_length",
        "ics_path",
        "json_path",
        "mean_path",
        "model_weights_path",
        "rundir",
        "stddev_path",
    ):
        assert not ok(with_del(cfg, key))
        assert f"'{key}' is a required property" in logcap.text
        logcap.clear()
    # Optional:
    assert ok(with_del(cfg, "forecast_freq"))
    # No additional properties:
    assert not ok(with_set(cfg, "bar", "foo"))
    assert "Additional properties are not allowed" in logcap.text
    logcap.clear()
    # Expecting an integer:
    for key in ("forecast_freq", "forecast_length"):
        assert not ok(with_set(cfg, "bad", key))
        assert "is not of type 'integer'" in logcap.text
        logcap.clear()
    # Expecting a string:
    for key in (
        "diffs_stddev_path",
        "ics_path",
        "json_path",
        "mean_path",
        "model_weights_path",
        "rundir",
        "stddev_path",
    ):
        assert not ok(with_set(cfg, 42, key))
        assert "is not of type 'string'" in logcap.text
        logcap.clear()
