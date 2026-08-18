from datetime import timedelta
from pathlib import Path
from unittest.mock import Mock, patch

from iotaa import Asset, Node, external, task
from pytest import fixture

from aigfs.drivers import post

# Fixtures


@fixture
def config(tmp_path):
    return {
        "aigfs_post": {
            "deliver_to": str(tmp_path / "delivery"),
            "execution": {"executable": "uw execute -h"},
            "inputfiles": [
                str(tmp_path / "run" / "aigfs.t00z.sfc.f006.grib2"),
                str(tmp_path / "run" / "aigfs.t00z.pres.f006.grib2"),
            ],
            "outputdir": str(tmp_path / "post"),
            "rundir": str(tmp_path / "run"),
        }
    }


@fixture
def cycle(utc):
    return utc(2025, 10, 1, 18)


@fixture
def driverobj(config, cycle):
    return post.AIGFSPost(
        config=config,
        cycle=cycle,
        leadtime=timedelta(hours=6),
        schema_file=Path(__file__).parent / "post.jsonschema",
    )


# Tests


def test_drivers_AIGFSPost_delivery(driverobj, logcap):
    @external
    def mock__idx_delivered(path: Path):
        yield f"mock__idx_delivered {path}"
        yield Asset(path, lambda: True)

    with patch.object(
        driverobj, "_idx_delivered", Mock(wraps=mock__idx_delivered)
    ) as _idx_delivered:
        assert driverobj.delivery().ready
    assert "Delivered GRIB indexes" in logcap.text
    del driverobj._deliver_to
    del driverobj._config["deliver_to"]
    node = driverobj.delivery()
    assert not node.ready
    assert "Definition of 'deliver_to' in 'delivery' task config block" in logcap.text


def test_drivers_AIGFSPost_indexes(driverobj, logcap, touch):
    @external
    def mock__idx(path: Path):
        yield f"mock__idx {path}"
        yield Asset(path, path.is_file)

    indexes = list(driverobj._idx2grib.keys())
    assert not any(x.is_file() for x in indexes)
    with patch.object(driverobj, "_idx", Mock(wraps=mock__idx)):
        assert not driverobj.indexes().ready
        for index in indexes:
            touch(index)
        assert driverobj.indexes().ready
    assert "GRIB indexes" in logcap.text


def test_drivers_AIGFSPost_provisioned_rundir(driverobj, logcap):
    path = driverobj.rundir / "runscript.aigfs_post"
    assert not path.exists()
    assert driverobj.provisioned_rundir().ready
    assert path.is_file()
    assert "provisioned run directory" in logcap.text


def test_drivers_AIGFSPost__gribfile(driverobj, logcap, touch):
    path = driverobj.rundir / "a.grib2"
    assert not driverobj._gribfile(path).ready
    touch(path)
    assert driverobj._gribfile(path).ready
    assert f"GRIB file {path}" in logcap.text


def test_drivers_AIGFSPost__idx(driverobj, logcap, touch):
    @task
    def mock__gribfile(path: Path):
        yield f"mock__gribfile {path}"
        yield Asset(path, path.is_file)
        yield None
        touch(path)

    path = Path(driverobj.config["outputdir"], "aigfs.t00z.sfc.f006.grib2.idx")
    assert not path.exists()
    with (
        patch.object(driverobj, "_gribfile", Mock(wraps=mock__gribfile)) as _gribfile,
        patch.object(post, "run_shell_cmd") as run_shell_cmd,
    ):
        run_shell_cmd.side_effect = lambda *_args, **_kwargs: touch(path)
        node = driverobj._idx(path)
    assert node.ready
    src = driverobj._idx2grib[path]
    _gribfile.assert_called_once_with(src)
    assert path.is_file()
    assert f"GRIB index {path}" in logcap.text
    assert run_shell_cmd.call_args[0][0].startswith(f"wgrib2 -s {src}")


def test_drivers_AIGFSPost__idx_delivered(driverobj, logcap, touch):
    @task
    def mock__idx(path: Path):
        yield f"mock__idx {path}"
        yield Asset(path, path.is_file)
        yield None
        touch(path)

    path = Path(driverobj._deliver_to, "aigfs.t00z.sfc.f006.grib2.idx")
    assert not path.exists()
    with patch.object(driverobj, "_idx", Mock(wraps=mock__idx)) as _idx:
        node = driverobj._idx_delivered(path)
    assert node.ready
    src = driverobj._delivered2idx[path]
    _idx.assert_called_once_with(src)
    assert path.is_file()
    assert f"Delivered GRIB index {path}" in logcap.text
    assert f"Copied {src} -> {path}" in logcap.text


def test_drivers_AIGFSPost__valid_driver_config(driverobj, logcap):
    reason = "Catastrophic failure"
    node = driverobj._valid_driver_config(reason=reason)
    assert not node.ready
    assert reason in logcap.text


def test_drivers_AIGFSPost_driver_name(driverobj):
    assert driverobj.driver_name() == "aigfs_post"


def test_drivers_AIGFSPost_output(driverobj):
    do = Path(driverobj.config["outputdir"])
    assert driverobj.output == {
        "idx": [do / "aigfs.t00z.sfc.f006.grib2.idx", do / "aigfs.t00z.pres.f006.grib2.idx"]
    }


def test_drivers_AIGFSPost__deliver_to(driverobj):
    assert driverobj._deliver_to == Path(driverobj.config["deliver_to"])


def test_drivers_AIGFSPost__deliver_to__fail(driverobj):
    del driverobj._config["deliver_to"]
    node = driverobj._deliver_to
    assert isinstance(node, Node)
    assert not node.ready


def test_drivers_AIGFSPost__delivered2idx(driverobj):
    dd = driverobj._deliver_to
    do = Path(driverobj.config["outputdir"])
    assert driverobj._delivered2idx == {
        dd / "aigfs.t00z.sfc.f006.grib2.idx": do / "aigfs.t00z.sfc.f006.grib2.idx",
        dd / "aigfs.t00z.pres.f006.grib2.idx": do / "aigfs.t00z.pres.f006.grib2.idx",
    }


def test_drivers_AIGFSPost__idx2grib(driverobj):
    di = driverobj.rundir
    do = Path(driverobj.config["outputdir"])
    assert driverobj._idx2grib == {
        do / "aigfs.t00z.sfc.f006.grib2.idx": di / "aigfs.t00z.sfc.f006.grib2",
        do / "aigfs.t00z.pres.f006.grib2.idx": di / "aigfs.t00z.pres.f006.grib2",
    }


# Schema tests


def test_drivers_post_schema(config, logcap, tmp_path, validator, with_set):
    ok = validator(post, tmp_path)
    # Valid config passes:
    assert ok(config)
    # Top-level aigfs_post key is required:
    assert not ok({})
    assert "'aigfs_post' is a required property" in logcap.text
    logcap.clear()
    # Expecting an object:
    assert not ok(with_set(config, [], "aigfs_post"))
    assert "is not of type 'object'" in logcap.text
    logcap.clear()


def test_drivers_post_schema_content(config, logcap, tmp_path, validator, with_del, with_set):
    ok = validator(post, tmp_path, "properties", "aigfs_post")
    cfg = config["aigfs_post"]
    # Required:
    for key in ("execution", "inputfiles", "outputdir", "rundir"):
        assert not ok(with_del(cfg, key))
        assert f"'{key}' is a required property" in logcap.text
        logcap.clear()
    # Optional:
    assert ok(with_del(cfg, "deliver_to"))
    # No additional properties:
    assert not ok(with_set(cfg, "bar", "foo"))
    assert "Additional properties are not allowed" in logcap.text
    logcap.clear()
    # Expecting a string:
    for key in ("deliver_to", "outputdir", "rundir"):
        assert not ok(with_set(cfg, 42, key))
        assert "is not of type 'string'" in logcap.text
        logcap.clear()
    # Expecting an array:
    assert not ok(with_set(cfg, "bad", "inputfiles"))
    assert "is not of type 'array'" in logcap.text
    logcap.clear()
    # Expecting an array with at least 2 strings:
    assert not ok(with_set(cfg, ["foo"], "inputfiles"))
    assert "is too short" in logcap.text
    logcap.clear()
    assert not ok(with_set(cfg, [1, 2, 3], "inputfiles"))
    assert "1 is not of type 'string'" in logcap.text
    logcap.clear()
