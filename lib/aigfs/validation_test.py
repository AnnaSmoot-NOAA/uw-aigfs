from datetime import timedelta

from pytest import fixture, raises

from aigfs import validation


@fixture
def app(kwargs):
    return validation.App(**kwargs)


@fixture
def kwargs(tmp_path, utc):
    return dict(
        cycle_freq=timedelta(hours=1),
        first_cycle=utc(2026, 1, 1, 0),
        home=tmp_path,
        last_cycle=utc(2026, 1, 31, 23),
        modeldir=tmp_path,
        platform="ursa",
        rundir=tmp_path,
    )


def test_validation_Config(app):
    assert validation.Config(app=app)


def test_validation_Config_with_platform(app):
    platform = validation.Platform(scheduler="slurm")
    assert validation.Config(app=app, platform=platform)


def test_validation_App(kwargs):
    assert validation.App(**kwargs)


def test_validation_App_fail(kwargs, utc):
    kwargs["last_cycle"] = utc(1970, 1, 1, 0)
    with raises(ValueError, match="last_cycle cannot precede first_cycle"):
        validation.App(**kwargs)


def test_validation_validate(app):
    assert validation.validate(config=dict(app=app))


def test_validation_Platform_minimal():
    p = validation.Platform(scheduler="slurm")
    assert p.partition is None
    assert p.account is None


def test_validation_Platform_with_partition():
    p = validation.Platform(
        scheduler="slurm",
        partition=validation.Partition(compute="u1-compute", task="u1-service", netaccess="u1-service"),
    )
    assert p.partition.compute == "u1-compute"


def test_validation_Partition_all_none():
    p = validation.Partition()
    assert p.compute is None
    assert p.task is None
    assert p.netaccess is None


def test_validation_Partition_partial():
    p = validation.Partition(compute="u1-compute")
    assert p.compute == "u1-compute"
    assert p.task is None
    assert p.netaccess is None
