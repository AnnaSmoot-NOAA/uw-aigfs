from datetime import timedelta

from pytest import fixture, raises

from . import validation


@fixture
def kwargs(tmp_path, utc):
    return dict(
        cycle_freq=timedelta(hours=1),
        experiment_dir=tmp_path,
        first_cycle=utc(2026, 1, 1, 0),
        last_cycle=utc(2026, 1, 31, 23),
        platform="ursa",
    )


@fixture
def user(kwargs):
    return validation.User(**kwargs)


def test_ush_validation_Config(user):
    assert validation.Config(user=user)


def test_ush_validation_User(kwargs):
    assert validation.User(**kwargs)


def test_ush_validation_User_fail(kwargs, utc):
    kwargs["last_cycle"] = utc(1970, 1, 1, 0)
    with raises(ValueError, match="last_cycle cannot precede first_cycle"):
        validation.User(**kwargs)


def test_ush_validation_validate(user):
    assert validation.validate(config=dict(user=user))
