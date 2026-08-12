import logging
from pathlib import Path

from pytest import fixture


@fixture
def logcap(caplog):
    caplog.handler.setFormatter(logging.Formatter("%(message)s"))
    caplog.set_level(logging.DEBUG)
    return caplog


@fixture
def touch():
    def f(path: Path) -> None:
        path.parent.mkdir(exist_ok=True, parents=True)
        path.touch()

    return f
