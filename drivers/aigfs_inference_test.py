from datetime import datetime, timezone
from pathlib import Path

from pytest import fixture

from . import aigfs_inference

# Fixtures


@fixture
def config(tmp_path):
    return {
        "aigfs_inference": {
            "diffs_stddev_path": str(tmp_path / "diffs_stddev"),
            "execution": {"executable": "uw execute -h"},
            "forecast_freq": 6,
            "forecast_length": 24,
            "ics_path": str(tmp_path / "ics"),
            "json_path": str(tmp_path / "json"),
            "mean_path": str(tmp_path / "mean"),
            "model_weights_path": str(tmp_path / "model_weihts"),
            "rundir": str(tmp_path / "run"),
            "stddev_path": str(tmp_path / "stddev"),
        }
    }


@fixture
def cycle():
    return datetime(2025, 10, 1, 18, tzinfo=timezone.utc)


@fixture
def driverobj(config, cycle):
    return aigfs_inference.AIGFSInference(
        config=config,
        cycle=cycle,
        schema_file=Path(__file__).parent / "aigfs_inference.jsonschema",
    )


# Tests


def test_drivers_AIGFSInference_driver_name(driverobj):
    assert driverobj.driver_name() == "aigfs_inference"
