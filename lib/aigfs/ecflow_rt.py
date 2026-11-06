"""
Real-time ecFlow rolling-window driver for AIGFS.

Advances an open-ended, real-time ecFlow suite ("rtaigfs") whose window of cycles
is deduced from the current time rather than specified explicitly via first_cycle/last_cycle.
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
from time import sleep

from uwtools.api import ecflow as uwecflow
from uwtools.api.config import YAMLConfig
from uwtools.api.logging import use_uwtools_logger

from aigfs import setup
from aigfs.strings import STR
from aigfs.validation import Config

SUITE_NAME = "rtaigfs"
CYCLE_FMT = "%Y%m%dT%H%M%S"
WORKFLOW = "ecflow-realtime"
RTCYCLES_ENV = "RTCYCLES"

# GFS data-availability cutoff: a cycle's inputs are not expected until this long
# after the cycle time. Matches the Rocoto real-time stream's 03:45 cutoff
# (current-cycle analysis reaches /public at 03:42); cf. rtaigfs_ursa/files/rtaigfs.yaml.
DATA_OFFSET = timedelta(hours=3, minutes=45)

# Defaults mirroring the Rocoto rolling window (active_cycles / window_cycles).
DEFAULT_ACTIVE_CYCLES = 4
DEFAULT_WINDOW_CYCLES = 12

# Per-user base offset for the deterministic default ecFlow port (matches the
# ensure-server script's $(($(id -u) + 1500)) so both agree without configuration).
PORT_BASE = 1500


def default_port() -> int:
    """Return the per-user default ecFlow port (user id + PORT_BASE)."""
    return os.getuid() + PORT_BASE


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
    os.environ[RTCYCLES_ENV] = ",".join(_utc(c).strftime(CYCLE_FMT) for c in cycles)
    # Supply a concrete app.rundir override so nested, cycle-parameterized rundir templates (e.g.
    # "{{ app.rundir }}/{{ app.time.yyyymmdd }}.../prep") resolve their rundir portion at generation
    # time, leaving only the per-cycle part deferred to task execution. Without this, app.rundir's
    # "{{ RUNDIR | env }}" value is held unresolved (alongside the deferred cycle) and then fails in
    # the task's environment, where RUNDIR is not set.
    raw = setup.compose_configs(
        WORKFLOW, platform, [user_config], app_overrides={STR.rundir: str(rundir)}
    )
    config = setup.validate(raw, Config)
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


def _client(host: str, port: int):
    """Return an SSL-enabled ecFlow client for the given host/port."""
    from ecflow import Client  # type: ignore[import-untyped]  # noqa: PLC0415

    client = Client(host, str(port))
    client.enable_ssl()
    return client


def wait_until_running(host: str, port: int, *, attempts: int = 60, delay: float = 1.0) -> None:
    """
    Wait until the ecFlow server is reachable, then move it to the RUNNING state.

    ensure-server starts the server in the background and returns immediately, so
    the server may not be accepting connections yet. A freshly started server (or
    one recovered from a checkpoint) comes up HALTED, so restart it to RUNNING.
    """
    client = _client(host, port)
    for _ in range(attempts):
        try:
            client.ping()
        except RuntimeError:
            sleep(delay)
            continue
        client.restart_server()
        return
    msg = "ecFlow server at %s:%s did not become reachable after %d attempts" % (
        host,
        port,
        attempts,
    )
    raise RuntimeError(msg)


def sync_window(
    host: str, port: int, rundir: Path, cycles: list[datetime], *, begin: bool = True
) -> None:
    """
    Incrementally bring the server's rtaigfs suite into line with `cycles`.

    Load (and begin) the suite if absent, otherwise add families for new cycles
    and delete families for cycles that have aged out. Force a checkpoint
    afterward so a hard server crash does not lose the change.
    """
    client = _client(host, port)
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
    os.environ[RTCYCLES_ENV] = datetime.now(UTC).strftime(CYCLE_FMT)
    config = setup.validate(setup.compose_configs(WORKFLOW, args.platform, [user_config]), Config)
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
        port = args.port if args.port is not None else default_port()
        ensure_server(install, args.ecflow_host, rundir, port, args.platform)
        wait_until_running(args.ecflow_host, port)
        sync_window(args.ecflow_host, port, rundir, cycles)
        # Prune only when advancing the live server, never in render-only mode:
        # render-only may target an existing run directory, and pruning there would
        # delete cycle outputs without a corresponding server-side change.
        prune_cycle_dirs(rundir, window)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Advance the real-time ecFlow AIGFS window.")
    parser.add_argument("--config", required=True, help="path to the real-time user config YAML")
    parser.add_argument("--install", required=True, help="role install directory (contains bin/)")
    parser.add_argument("--ecflow-host", required=True, help="dedicated ecFlow node hostname")
    parser.add_argument(
        "--port", type=int, help="ecFlow server port (default: per-user, user id + 1500)"
    )
    parser.add_argument("--platform", default="ursa", help="platform name")
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
