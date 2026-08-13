import logging
from datetime import datetime, timezone
from pathlib import Path

from iotaa import Asset, external
from pytest import fixture


@fixture
def atask():
    @external
    def f(ready: bool):
        yield "A %sready task" % ("" if ready else "not-")
        yield Asset(ready, lambda: ready)

    return f


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


@fixture
def utc():
    def f(*args):
        return datetime(*args, tzinfo=timezone.utc)  # type: ignore[misc]

    return f
