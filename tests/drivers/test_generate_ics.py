"""
GenICS driver tests.
"""

import sys
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from pytest import fixture

APP_DIR = Path(__file__).parent.parent.parent
sys.path.append(str(APP_DIR))

from drivers import generate_ics  # noqa: E402


@fixture
def config(tmp_path):
    return {
        "aigfs_ics": {
            "execution": {
                "executable": "uw execute -h",
                "batchargs": {"walltime": "00:05:00"},
            },
            "files_to_link": {
                "data/a.t00z.pgrb2.0p25.f000": str(tmp_path / "a.grib2"),
                "data/b.t00z.pgrb2.0p25.f006": str(tmp_path / "b.grib2"),
            },
            "variable_extraction_yaml": str(APP_DIR / "parm" / "wgrib2_data_to_process.yml"),
            "rundir": str(tmp_path / "prep"),
        }
    }


@fixture
def cycle():
    return datetime(2025, 10, 1, 18, tzinfo=timezone.utc)


@fixture
def driverobj(config, cycle):
    return generate_ics.GenICS(
        config=config,
        cycle=cycle,
        batch=True,
        schema_file=APP_DIR / "drivers/generate_ics.jsonschema",
    )


def test_driver_name(driverobj):
    assert driverobj.driver_name() == "aigfs_ics"


def test_wgrib2_tasks(driverobj, tmp_path):
    def make_output(*_args, **_kwargs):
        cmd = _kwargs["cmd"]
        (driverobj.rundir / cmd.split()[-1]).touch()

    for f in ("a.grib2", "b.grib2"):
        (tmp_path / f).touch()
    with patch.object(generate_ics, "run_shell_cmd", side_effect=make_output) as run:
        driverobj.wgrib2_tasks()
        assert run.call_count == 7


def test__wgrib2_commands(driverobj):
    cmds = driverobj._wgrib2_commands
    assert len(cmds) == 7
