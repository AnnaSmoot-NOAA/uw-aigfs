from datetime import timedelta

from pydantic import ValidationError
from pytest import fixture, mark, raises

from aigfs import validation
from aigfs.strings import STR


@fixture
def args_app(args_platform, args_time, tmp_path, utc):
    return dict(
        cycle_freq=timedelta(hours=12),
        first_cycle=utc(2026, 1, 1, 0),
        home=tmp_path,
        last_cycle=utc(2026, 1, 31, 23),
        modeldir=tmp_path,
        platform=validation.Platform(**args_platform),
        rundir=tmp_path,
        time=validation.Time(**args_time),
    )


@fixture
def args_config(args_app):
    return dict(app=args_app, forecast={}, post={}, prep={}, user={}, workflow={})


@fixture
def args_partition():
    return dict(compute="p-compute", netaccess="p-netaccess", task="p-task")


@fixture
def args_platform(args_partition, args_scheduler):
    return dict(
        name="ursa",
        partition=validation.Partition(**args_partition),
        scheduler=validation.Scheduler(**args_scheduler),
    )


@fixture
def args_scheduler():
    return dict(account="me", type="slurm")


@fixture
def args_time():
    return dict(
        fff="006",
        hh="00",
        m1_hh="18",
        m1_yyyymmdd="20260826",
        m2_hh="12",
        m2_yyyymmdd="20260826",
        m6h=timedelta(hours=6),
        yyyymmdd="20260827",
    )


@mark.parametrize("compute", ["a", None])
@mark.parametrize("netaccess", ["b", None])
@mark.parametrize("task", ["c", None])
def test_validation_Partition(args_partition, compute, netaccess, task):
    assert validation.Partition(**args_partition)
    if any([compute, netaccess, task]):
        obj = validation.Partition(compute=compute, netaccess=netaccess, task=task)
        assert obj.compute == compute
        assert obj.netaccess == netaccess
        assert obj.task == task
    else:  # if no partitions are specified
        with raises(ValidationError) as e:
            validation.Partition(compute=compute, netaccess=netaccess, task=task)
        assert e.value.error_count() == 1
        msg = "Specify at least one partition name (compute, netaccess, task)"
        assert msg in e.value.errors()[0]["msg"]


def test_validation_Scheduler(args_scheduler):
    assert validation.Scheduler(**args_scheduler)
    for val in ["pbs", "slurm"]:
        assert validation.Scheduler(type=val).type == val  # type: ignore[arg-type]
    obj = validation.Scheduler(account="me", type="slurm")
    assert obj.account == "me"
    assert obj.type == "slurm"


def test_validation_Scheduler_bad_type():
    with raises(ValidationError) as e:
        validation.Scheduler(type="foo")  # type: ignore[arg-type]
    assert e.value.error_count() == 1
    msg = "Input should be 'pbs' or 'slurm'"
    assert msg in e.value.errors()[0]["msg"]


def test_validation_Platform(args_platform):
    assert validation.Platform(**args_platform)


def test_validation_Platform_bad_name(args_platform, with_set):
    with raises(ValidationError) as e:
        validation.Platform(**with_set(args_platform, "foo", STR.name))
    assert e.value.error_count() == 1
    msg = "Platform name must be one of"
    assert msg in e.value.errors()[0]["msg"]


def test_validation_Time(args_time, with_del):
    obj = validation.Time(**args_time)
    for key in obj.model_dump():
        with raises(ValidationError) as e:
            validation.Time(**with_del(args_time, key))
        assert e.value.error_count() == 1
        assert e.value.errors()[0]["type"] == "missing"


def test_validation_App(args_app, with_del):
    obj = validation.App(**args_app)
    for key in obj.model_dump():
        with raises(ValidationError) as e:
            validation.App(**with_del(args_app, key))
        assert e.value.error_count() == 1
        assert e.value.errors()[0]["type"] == "missing"


@mark.parametrize("hours", [0, -1])
def test_validation_App_bad_cycle_freq_negative(args_app, hours):
    args_app["cycle_freq"] = timedelta(hours=hours)
    with raises(ValueError, match="cycle_freq must be greater than 0"):
        validation.App(**args_app)


def test_validation_App_bad_cycle_freq_not_0_mod_6(args_app):
    args_app["cycle_freq"] = timedelta(hours=1)
    with raises(ValueError, match="cycle_freq must be a multiple of 6"):
        validation.App(**args_app)


def test_validation_App_bad_first_vs_last_cycle(args_app, utc):
    args_app["last_cycle"] = utc(1970, 1, 1, 0)
    with raises(ValueError, match="last_cycle cannot precede first_cycle"):
        validation.App(**args_app)


def test_validation_Config(args_config, with_del):
    assert validation.Config(**args_config)
    obj = validation.Config(**with_del(args_config, "user"))
    for key in obj.model_dump():
        with raises(ValidationError):
            validation.App(**with_del(args_config, key))


def test_validation_validate(args_config, with_set):
    assert validation.validate(config=args_config)
    assert validation.validate(config=with_set(args_config, {}, "user"))


def test_validation_validate_fail(args_app, logcap):
    del args_app[STR.rundir]
    with raises(SystemExit) as e:
        validation.validate({STR.app: args_app})
    assert e.value.code == 1
    assert "Config validation failed:" in logcap.text
    assert "'loc': ('app', 'rundir')" in logcap.text
