import json
import logging
from collections.abc import Callable
from copy import deepcopy
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path
from types import ModuleType
from typing import Any, cast

from iotaa import Asset, external
from pytest import fixture
from uwtools.api.config import validate


@fixture
def atask():
    @external
    def f(ready: bool):
        yield "A %sready task" % ("" if ready else "not-")
        yield Asset(ready, lambda: ready)

    return f


@fixture
def config(tmp_path):
    return {
        "app": {
            "cycle_freq": timedelta(hours=12),
            "first_cycle": datetime(2026, 1, 1, tzinfo=UTC),
            "home": tmp_path,
            "last_cycle": datetime(2026, 1, 31, tzinfo=UTC),
            "modeldir": tmp_path,
            "platform": {
                "name": "ursa",
                "partition": None,
                "scheduler": None,
            },
            "rundir": tmp_path,
            "time": {
                "fff": "006",
                "hh": "00",
                "m1_hh": "18",
                "m1_yyyymmdd": "20260826",
                "m2_hh": "12",
                "m2_yyyymmdd": "20260826",
                "m6h": timedelta(hours=6),
                "yyyymmdd": "20260827",
            },
        },
        "ecflow": None,
        "forecast": {},
        "post": {},
        "prep": {},
        "user": {},
        "workflow": None,
    }


@fixture
def logcap(caplog):
    caplog.handler.setFormatter(logging.Formatter("%(message)s"))
    caplog.set_level(logging.DEBUG)
    return caplog


@fixture
def touch():
    def touch(path: Path) -> None:
        path.parent.mkdir(exist_ok=True, parents=True)
        path.touch()

    return touch


@fixture
def utc():
    def utc(*args):
        return datetime(*args, tzinfo=timezone.utc)  # type: ignore[misc]

    return utc


@fixture
def validator():
    def validator(module: ModuleType, outdir: Path, *args: Any) -> Callable:
        schema = json.loads(Path(cast(str, module.__file__)).with_suffix(".jsonschema").read_text())
        defs = schema.get("$defs", {})
        for arg in args:
            schema = schema[arg]
        if args and args[0] != "$defs":
            schema.update({"$defs": deepcopy(defs)})
        path = outdir / "test.jsonschema"
        path.write_text(json.dumps(schema))
        return lambda c: validate(schema_file=path, config_data=c)

    return validator


@fixture
def with_del():
    def with_del(d: dict, *args: Any) -> dict:
        new = deepcopy(d)
        p = new
        for key in args[:-1]:
            p = p[key]
        del p[args[-1]]
        return new

    return with_del


@fixture
def with_set():
    def with_set(d: dict, val: Any, *args: Any) -> dict:
        new = deepcopy(d)
        p = new
        for key in args[:-1]:
            p = p[key]
        p[args[-1]] = val
        return new

    return with_set
