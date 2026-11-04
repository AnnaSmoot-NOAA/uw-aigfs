"""
Real-time ecFlow rolling-window driver for AIGFS.

Advances an open-ended, real-time ecFlow suite ("rtaigfs") whose window of cycles
is deduced from the current time rather than prescribed via first_cycle/last_cycle.
Each invocation (typically from a periodic scron job):

  1. ensures the ecFlow server is up on the ecFlow node (via the ensure-server
     script, run over ssh),
  2. deduces the active window of cycles and gates out cycles whose GFS data is
     not yet expected (now < cycle + DATA_OFFSET),
  3. renders the suite definition for the gated window (families keyed by cycle),
  4. incrementally syncs the server: adds families for new cycles, deletes
     families for cycles that have aged out of the window, forces a checkpoint,
  5. prunes trailing-edge cycle directories beyond the retention window.

This mirrors the Rocoto real-time rolling window (active_cycles / window_cycles)
while generating aigfs.yaml exactly once and advancing the suite in place.
"""

from __future__ import annotations

import argparse
import logging
import os
import re
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from shutil import rmtree

from uwtools.api import ecflow as uwecflow
from uwtools.api.config import YAMLConfig
from uwtools.api.logging import use_uwtools_logger

from aigfs import setup
from aigfs.strings import STR

SUITE_NAME = "rtaigfs"
CYCLE_FMT = "%Y%m%dT%H%M%S"
WORKFLOW = "ecflow-realtime"
STR_RTCYCLES = "RTCYCLES"

# GFS data-availability cutoff: a cycle's inputs are not expected until this long
# after the cycle time (cf. the Rocoto timedep and aigfs.workflow._timegate).
DATA_OFFSET = timedelta(hours=3, minutes=35)

# Defaults mirroring the Rocoto rolling window (active_cycles / window_cycles).
DEFAULT_ACTIVE_CYCLES = 4
DEFAULT_WINDOW_CYCLES = 12


# Cycle math (pure)


def deduce_cycles(now: datetime, cycle_freq: timedelta, count: int) -> list[datetime]:
    """
    Return the latest `count` cycles, newest first.

    The newest cycle is the most recent cycle_freq boundary at or before `now`.
    """
    secs = cycle_freq.total_seconds()
    ts = now.timestamp()
    latest = datetime.fromtimestamp(ts - (ts % secs), UTC)
    return [latest - n * cycle_freq for n in range(count)]


def gated_cycles(
    cycles: list[datetime], now: datetime, offset: timedelta = DATA_OFFSET
) -> list[datetime]:
    """
    Return the subset of `cycles` whose data-availability cutoff has passed.

    A cycle is included when now >= cycle + offset; cycles whose GFS data is not
    yet expected are withheld.
    """
    return [c for c in cycles if now >= _utc(c) + offset]


def family_name(cycle: datetime) -> str:
    """Return the ecFlow family name for a cycle (matches ecflow-realtime.yaml)."""
    return "cycle_%s" % _utc(cycle).strftime(CYCLE_FMT)


def _utc(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


# Suite rendering


def render_suite(
    user_config: Path, platform: str, rundir: Path, cycles: list[datetime]
) -> YAMLConfig:
    """
    Render suite.def and ecf scripts for the given window of cycles into rundir.

    The cycle list is passed to the suite template via the RTCYCLES environment
    variable. aigfs.yaml (the task config) is written once and left in place on
    subsequent invocations, since its content does not depend on the window.
    """
    os.environ[STR_RTCYCLES] = ",".join(_utc(c).strftime(CYCLE_FMT) for c in cycles)
    raw = setup.compose_configs(WORKFLOW, platform, [user_config])
    config = setup.validate(raw)
    # model_dump() yields pathlib.Path objects for app paths; stringify them so the
    # dumped aigfs.yaml is plain YAML that uw ecflow server / uwtools can re-parse.
    data = config.model_dump()
    data[STR.app] = {k: (str(v) if isinstance(v, Path) else v) for k, v in data[STR.app].items()}
    yaml_config = YAMLConfig(data)
    final = rundir / STR.aigfs_yaml
    rundir.mkdir(parents=True, exist_ok=True)
    if not final.is_file():
        yaml_config.dump(final)
    uwecflow.realize(yaml_config, rundir, scripts_path=rundir / "ecf")
    return yaml_config


# Server sync


def sync_window(
    host: str,
    port: int,
    rundir: Path,
    cycles: list[datetime],
    *,
    ssl: bool,
    begin: bool = True,
) -> None:
    """
    Incrementally bring the server's rtaigfs suite into line with `cycles`.

    Load (and begin) the suite if absent, otherwise add families for new cycles
    and delete families for cycles that have aged out. Force a checkpoint
    afterward so a hard server crash does not lose the change.
    """
    from ecflow import Client  # type: ignore[import-untyped]  # noqa: PLC0415

    client = Client(host, str(port))
    if ssl:
        client.enable_ssl()
    suite_def = str(rundir / "suite.def")
    wanted = {family_name(c) for c in cycles}

    client.sync_local()
    defs = client.get_defs()
    suite = defs.find_suite(SUITE_NAME) if defs else None

    if suite is None:
        logging.info("Loading suite /%s with %d cycle families", SUITE_NAME, len(wanted))
        client.replace("/%s" % SUITE_NAME, suite_def, True, True)  # noqa: FBT003
        if begin:
            client.begin_suite(SUITE_NAME, True)  # noqa: FBT003
    else:
        existing = {node.name() for node in suite.nodes if node.name().startswith("cycle_")}
        for fam in sorted(wanted - existing):
            logging.info("Adding cycle family /%s/%s", SUITE_NAME, fam)
            client.replace("/%s/%s" % (SUITE_NAME, fam), suite_def, True, True)  # noqa: FBT003
        for fam in sorted(existing - wanted):
            logging.info("Deleting aged-out cycle family /%s/%s", SUITE_NAME, fam)
            client.delete("/%s/%s" % (SUITE_NAME, fam), True)  # noqa: FBT003

    client.checkpt()


# Pruning


def prune_cycle_dirs(rundir: Path, keep: int) -> None:
    """Remove trailing-edge per-cycle directories (YYYYMMDDHH), keeping the newest `keep`."""
    if not rundir.is_dir():
        return
    is_cycledir = lambda p: p.is_dir() and re.match(r"^\d{10}$", p.name)
    cycledirs = sorted(filter(is_cycledir, rundir.iterdir()))
    for path in cycledirs[:-keep] if keep else cycledirs:
        logging.info("Pruning cycle directory %s", path)
        rmtree(path, ignore_errors=True)


# Server bootstrap


def ensure_server(install: Path, ecflow_host: str, rundir: Path, port: int, platform: str) -> None:
    """Run ensure-server on the ecFlow node over ssh to start/recover the server."""
    cmd = [
        "ssh",
        "-o",
        "BatchMode=yes",
        ecflow_host,
        str(install / "bin" / "ensure-server"),
        "--rundir",
        str(rundir),
        "--config",
        str(rundir / STR.aigfs_yaml),
        "--port",
        str(port),
        "--platform",
        platform,
    ]
    logging.info("Ensuring ecFlow server on %s:%d", ecflow_host, port)
    subprocess.run(cmd, check=True)


# Entry point


def drive(args: argparse.Namespace) -> None:
    """Advance the real-time window by one step."""
    install = Path(args.install).resolve()
    user_config = Path(args.config)

    # Compose once (placeholder window) to read rundir and window parameters.
    os.environ[STR_RTCYCLES] = datetime.now(UTC).strftime(CYCLE_FMT)
    config = setup.validate(setup.compose_configs(WORKFLOW, args.platform, [user_config]))
    rundir = Path(config.app.rundir)
    cycle_freq = config.app.cycle_freq
    assert cycle_freq is not None  # guaranteed by validation when a workflow engine is configured
    user = config.user or {}
    active = int(user.get("active_cycles", DEFAULT_ACTIVE_CYCLES))
    window = int(user.get("window_cycles", DEFAULT_WINDOW_CYCLES))

    now = datetime.now(UTC)
    cycles = gated_cycles(deduce_cycles(now, cycle_freq, active), now)
    if not cycles:
        logging.info("No cycles past the data-availability cutoff yet; nothing to do.")
        return

    render_suite(user_config, args.platform, rundir, cycles)
    if not args.render_only:
        ensure_server(install, args.ecflow_host, rundir, args.port, args.platform)
        sync_window(args.ecflow_host, args.port, rundir, cycles, ssl=not args.insecure)
    prune_cycle_dirs(rundir, window)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Advance the real-time ecFlow AIGFS window.")
    parser.add_argument("--config", required=True, help="path to the real-time user config YAML")
    parser.add_argument("--install", required=True, help="role install directory (contains bin/)")
    parser.add_argument("--ecflow-host", required=True, help="dedicated ecFlow node hostname")
    parser.add_argument("--port", required=True, type=int, help="ecFlow server port")
    parser.add_argument("--platform", default="ursa", help="platform name")
    parser.add_argument("--insecure", action="store_true", help="connect without SSL")
    parser.add_argument("--render-only", action="store_true", help="render suite.def only")
    parser.add_argument("--verbose", action="store_true", help="enable verbose logging")
    return parser.parse_args(argv)


def main() -> None:
    args = parse_args()
    use_uwtools_logger(verbose=args.verbose)
    try:
        drive(args)
    except Exception as e:  # noqa: BLE001
        logging.error("Real-time driver failed: %s", e)
        sys.exit(1)


if __name__ == "__main__":
    main()  # pragma: no cover
