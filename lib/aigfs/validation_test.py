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
        last_cycle=utc(2026, 1, 31, 23),
        platform="ursa",
        rundir=tmp_path,
    )


def test_ush_validation_Config(app):
    assert validation.Config(app=app)


def test_ush_validation_App(kwargs):
    assert validation.App(**kwargs)


def test_ush_validation_App_fail(kwargs, utc):
    kwargs["last_cycle"] = utc(1970, 1, 1, 0)
    with raises(ValueError, match="last_cycle cannot precede first_cycle"):
        validation.App(**kwargs)


def test_ush_validation_validate(app):
    assert validation.validate(config=dict(app=app))
