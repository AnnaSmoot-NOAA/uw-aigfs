import os
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import Mock, patch

from pytest import mark, raises

from aigfs import ecflow_rt
from aigfs.strings import STR

# deduce_cycles


def test_ecflow_rt_deduce_cycles_newest_first(utc):
    # 07:30 falls between the 06Z and 12Z 6-hourly boundaries, so the newest cycle is 06Z.
    cycles = ecflow_rt.deduce_cycles(utc(2026, 9, 13, 7, 30), timedelta(hours=6), 4)
    assert cycles == [
        utc(2026, 9, 13, 6),
        utc(2026, 9, 13, 0),
        utc(2026, 9, 12, 18),
        utc(2026, 9, 12, 12),
    ]


def test_ecflow_rt_deduce_cycles_on_boundary(utc):
    # Exactly on a boundary, that boundary is the newest cycle.
    cycles = ecflow_rt.deduce_cycles(utc(2026, 9, 13, 12), timedelta(hours=6), 2)
    assert cycles == [utc(2026, 9, 13, 12), utc(2026, 9, 13, 6)]


# gated_cycles


def test_ecflow_rt_gated_cycles_withholds_until_cutoff(utc):
    now = utc(2026, 9, 13, 7, 30)
    cycles = ecflow_rt.deduce_cycles(now, timedelta(hours=6), 4)
    gated = ecflow_rt.gated_cycles(cycles, now)
    # 06Z cutoff is 09:45 (> now) so it is withheld; 00Z cutoff is 03:45 (<= now) so it is included.
    assert utc(2026, 9, 13, 6) not in gated
    assert gated[0] == utc(2026, 9, 13, 0)
    assert len(gated) == 3


def test_ecflow_rt_gated_cycles_custom_offset(utc):
    now = utc(2026, 9, 13, 6, 0)
    cycles = [utc(2026, 9, 13, 0)]
    assert ecflow_rt.gated_cycles(cycles, now, timedelta(hours=3)) == cycles
    assert ecflow_rt.gated_cycles(cycles, now, timedelta(hours=7)) == []


# family_name / _utc


@mark.parametrize(
    ("args", "expected"),
    [
        ((2026, 9, 13, 0), "cycle_20260913T000000"),
        ((2026, 9, 13, 6), "cycle_20260913T060000"),
    ],
)
def test_ecflow_rt_family_name(args, expected, utc):
    assert ecflow_rt.family_name(utc(*args)) == expected


def test_ecflow_rt_family_name_naive_treated_as_utc():
    # A naive datetime exercises the _utc() tz-adding branch.
    naive = datetime(2026, 9, 13, 0)  # noqa: DTZ001
    assert ecflow_rt.family_name(naive) == "cycle_20260913T000000"


# render_suite


def _render_config(app):
    config = Mock()
    config.model_dump.return_value = {STR.app: dict(app)}
    return config


def test_ecflow_rt_render_suite_writes_config_when_absent(tmp_path, utc):
    # Mix of Path and non-Path app values exercises both arms of the stringify comprehension.
    config = _render_config({"home": Path("/h"), "rundir": Path("/r"), "n": 1})
    with (
        patch.object(ecflow_rt.setup, "compose_configs") as compose,
        patch.object(ecflow_rt.setup, "validate", return_value=config) as validate,
        patch.object(ecflow_rt, "YAMLConfig") as yamlconfig,
        patch.object(ecflow_rt.uwecflow, "realize") as realize,
    ):
        result = ecflow_rt.render_suite(
            Path("/u/user.yaml"), "ursa", tmp_path, [utc(2026, 9, 13, 0)]
        )
    assert os.environ[ecflow_rt.RTCYCLES_ENV] == "20260913T000000"
    compose.assert_called_once_with(
        ecflow_rt.WORKFLOW,
        "ursa",
        [Path("/u/user.yaml")],
        app_overrides={STR.rundir: str(tmp_path)},
    )
    validate.assert_called_once_with(compose.return_value, ecflow_rt.Config)
    assert yamlconfig.call_args.args[0][STR.app] == {"home": "/h", "rundir": "/r", "n": 1}
    yamlconfig.return_value.dump.assert_called_once_with(tmp_path / STR.aigfs_yaml)
    realize.assert_called_once_with(
        yamlconfig.return_value, tmp_path, scripts_path=tmp_path / "ecf"
    )
    assert result is yamlconfig.return_value


def test_ecflow_rt_render_suite_skips_config_when_present(tmp_path, utc):
    (tmp_path / STR.aigfs_yaml).touch()
    config = _render_config({"home": Path("/h")})
    with (
        patch.object(ecflow_rt.setup, "compose_configs"),
        patch.object(ecflow_rt.setup, "validate", return_value=config),
        patch.object(ecflow_rt, "YAMLConfig") as yamlconfig,
        patch.object(ecflow_rt.uwecflow, "realize") as realize,
    ):
        ecflow_rt.render_suite(Path("/u/user.yaml"), "ursa", tmp_path, [utc(2026, 9, 13, 0)])
    yamlconfig.return_value.dump.assert_not_called()
    realize.assert_called_once()


# sync_window


def _suite(names):
    suite = Mock()
    nodes = []
    for name in names:
        node = Mock()
        node.name.return_value = name
        nodes.append(node)
    suite.nodes = nodes
    return suite


def test_ecflow_rt_sync_window_loads_and_begins_when_absent(tmp_path, utc):
    client = Mock()
    client.get_defs.return_value = None  # no defs on server yet
    with patch("ecflow.Client", return_value=client):
        ecflow_rt.sync_window("host", 20, tmp_path, [utc(2026, 9, 13, 0)], begin=True)
    client.enable_ssl.assert_called_once()
    client.replace.assert_called_once_with("/rtaigfs", str(tmp_path / "suite.def"), True, True)  # noqa: FBT003
    client.begin_suite.assert_called_once_with("rtaigfs", True)  # noqa: FBT003
    client.checkpt.assert_called_once()


def test_ecflow_rt_sync_window_loads_without_begin(tmp_path, utc):
    client = Mock()
    defs = Mock()
    defs.find_suite.return_value = None
    client.get_defs.return_value = defs
    with patch("ecflow.Client", return_value=client):
        ecflow_rt.sync_window("host", 20, tmp_path, [utc(2026, 9, 13, 0)], begin=False)
    client.enable_ssl.assert_called_once()
    client.replace.assert_called_once()
    client.begin_suite.assert_not_called()


def test_ecflow_rt_sync_window_adds_and_deletes(tmp_path, utc):
    client = Mock()
    defs = Mock()
    # Server has 00Z (keep), 18Z (aged out), plus a non-cycle node (ignored by the filter).
    defs.find_suite.return_value = _suite(
        ["cycle_20260913T000000", "cycle_20260912T180000", "misc"]
    )
    client.get_defs.return_value = defs
    cycles = [utc(2026, 9, 13, 6), utc(2026, 9, 13, 0)]  # want 06Z (new) + 00Z (keep)
    with patch("ecflow.Client", return_value=client):
        ecflow_rt.sync_window("host", 20, tmp_path, cycles)
    suite_def = str(tmp_path / "suite.def")
    client.replace.assert_called_once_with("/rtaigfs/cycle_20260913T060000", suite_def, True, True)  # noqa: FBT003
    client.delete.assert_called_once_with("/rtaigfs/cycle_20260912T180000", True)  # noqa: FBT003
    client.begin_suite.assert_not_called()
    client.checkpt.assert_called_once()


def test_ecflow_rt_sync_window_noop_when_matching(tmp_path, utc):
    client = Mock()
    defs = Mock()
    defs.find_suite.return_value = _suite(["cycle_20260913T000000"])
    client.get_defs.return_value = defs
    with patch("ecflow.Client", return_value=client):
        ecflow_rt.sync_window("host", 20, tmp_path, [utc(2026, 9, 13, 0)])
    client.replace.assert_not_called()
    client.delete.assert_not_called()
    client.checkpt.assert_called_once()


# default_port / wait_until_running


def test_ecflow_rt_default_port():
    with patch.object(ecflow_rt.os, "getuid", return_value=4242):
        assert ecflow_rt.default_port() == 4242 + ecflow_rt.PORT_BASE


def test_ecflow_rt_wait_until_running_reachable_first_try():
    client = Mock()
    with patch("ecflow.Client", return_value=client), patch.object(ecflow_rt, "sleep") as sleep:
        ecflow_rt.wait_until_running("host", 20)
    client.enable_ssl.assert_called_once()
    client.ping.assert_called_once()
    client.restart_server.assert_called_once()
    sleep.assert_not_called()


def test_ecflow_rt_wait_until_running_retries_then_succeeds():
    client = Mock()
    client.ping.side_effect = [RuntimeError("not up"), None]
    with patch("ecflow.Client", return_value=client), patch.object(ecflow_rt, "sleep") as sleep:
        ecflow_rt.wait_until_running("host", 20, attempts=5, delay=0.0)
    assert client.ping.call_count == 2
    sleep.assert_called_once_with(0.0)
    client.restart_server.assert_called_once()


def test_ecflow_rt_wait_until_running_gives_up():
    client = Mock()
    client.ping.side_effect = RuntimeError("never up")
    with (
        patch("ecflow.Client", return_value=client),
        patch.object(ecflow_rt, "sleep"),
        raises(RuntimeError, match="did not become reachable"),
    ):
        ecflow_rt.wait_until_running("host", 20, attempts=3)
    client.restart_server.assert_not_called()


# prune_cycle_dirs


def test_ecflow_rt_prune_cycle_dirs_keeps_newest(tmp_path):
    for name in ["2026091300", "2026091306", "2026091312", "2026091318", "2026091400"]:
        (tmp_path / name).mkdir()
    (tmp_path / "ecf").mkdir()  # non-cycle dir must be ignored
    (tmp_path / "aigfs.yaml").touch()  # non-dir must be ignored
    ecflow_rt.prune_cycle_dirs(tmp_path, keep=3)
    remaining = sorted(p.name for p in tmp_path.iterdir() if p.is_dir() and p.name.isdigit())
    assert remaining == ["2026091312", "2026091318", "2026091400"]
    assert (tmp_path / "ecf").is_dir()


def test_ecflow_rt_prune_cycle_dirs_noop_when_under_limit(tmp_path):
    for name in ["2026091300", "2026091306"]:
        (tmp_path / name).mkdir()
    ecflow_rt.prune_cycle_dirs(tmp_path, keep=12)
    remaining = sorted(p.name for p in tmp_path.iterdir() if p.is_dir())
    assert remaining == ["2026091300", "2026091306"]


def test_ecflow_rt_prune_cycle_dirs_keep_zero_removes_all(tmp_path):
    for name in ["2026091300", "2026091306"]:
        (tmp_path / name).mkdir()
    ecflow_rt.prune_cycle_dirs(tmp_path, keep=0)
    assert [p.name for p in tmp_path.iterdir() if p.is_dir() and p.name.isdigit()] == []


def test_ecflow_rt_prune_cycle_dirs_missing_rundir(tmp_path):
    ecflow_rt.prune_cycle_dirs(tmp_path / "nope", keep=3)  # must not raise


# ensure_server


def test_ecflow_rt_ensure_server():
    with patch.object(ecflow_rt.subprocess, "run") as run:
        ecflow_rt.ensure_server(Path("/i"), "uecflow01", Path("/r"), 20, "ursa")
    run.assert_called_once_with(
        [
            "ssh",
            "-o",
            "BatchMode=yes",
            "uecflow01",
            "/i/bin/ensure-server",
            "--rundir",
            "/r",
            "--config",
            str(Path("/r") / STR.aigfs_yaml),
            "--port",
            "20",
            "--platform",
            "ursa",
        ],
        check=True,
    )


# drive


def _drive_args(**overrides):
    defaults = {
        "config": "/c/user.yaml",
        "install": "/i",
        "ecflow_host": "uecflow01",
        "port": None,
        "platform": "ursa",
        "render_only": False,
    }
    defaults.update(overrides)
    return Mock(**defaults)


def _drive_config(user):
    config = Mock()
    config.app.rundir = "/run"
    config.app.cycle_freq = timedelta(hours=6)
    config.user = user
    return config


def test_ecflow_rt_drive_no_cycles_returns_early(utc):
    config = _drive_config({})
    with (
        patch.object(ecflow_rt.setup, "compose_configs"),
        patch.object(ecflow_rt.setup, "validate", return_value=config),
        patch.object(ecflow_rt, "deduce_cycles", return_value=[utc(2026, 9, 13, 0)]),
        patch.object(ecflow_rt, "gated_cycles", return_value=[]),
        patch.object(ecflow_rt, "render_suite") as render,
        patch.object(ecflow_rt, "prune_cycle_dirs") as prune,
    ):
        ecflow_rt.drive(_drive_args())
    render.assert_not_called()
    prune.assert_not_called()


def test_ecflow_rt_drive_full_step_default_port(utc):
    config = _drive_config({"active_cycles": 2, "window_cycles": 5})
    cyc = [utc(2026, 9, 13, 0)]
    with (
        patch.object(ecflow_rt.setup, "compose_configs"),
        patch.object(ecflow_rt.setup, "validate", return_value=config),
        patch.object(ecflow_rt, "deduce_cycles", return_value=cyc) as deduce,
        patch.object(ecflow_rt, "gated_cycles", return_value=cyc),
        patch.object(ecflow_rt, "default_port", return_value=1999) as default_port,
        patch.object(ecflow_rt, "render_suite") as render,
        patch.object(ecflow_rt, "ensure_server") as ensure,
        patch.object(ecflow_rt, "wait_until_running") as wait,
        patch.object(ecflow_rt, "sync_window") as sync,
        patch.object(ecflow_rt, "prune_cycle_dirs") as prune,
    ):
        ecflow_rt.drive(_drive_args())
    assert deduce.call_args.args[1:] == (timedelta(hours=6), 2)
    default_port.assert_called_once()
    render.assert_called_once_with(Path("/c/user.yaml"), "ursa", Path("/run"), cyc)
    ensure.assert_called_once_with(Path("/i"), "uecflow01", Path("/run"), 1999, "ursa")
    wait.assert_called_once_with("uecflow01", 1999)
    sync.assert_called_once_with("uecflow01", 1999, Path("/run"), cyc)
    prune.assert_called_once_with(Path("/run"), 5)


def test_ecflow_rt_drive_explicit_port(utc):
    config = _drive_config({})
    cyc = [utc(2026, 9, 13, 0)]
    with (
        patch.object(ecflow_rt.setup, "compose_configs"),
        patch.object(ecflow_rt.setup, "validate", return_value=config),
        patch.object(ecflow_rt, "deduce_cycles", return_value=cyc),
        patch.object(ecflow_rt, "gated_cycles", return_value=cyc),
        patch.object(ecflow_rt, "default_port") as default_port,
        patch.object(ecflow_rt, "render_suite"),
        patch.object(ecflow_rt, "ensure_server") as ensure,
        patch.object(ecflow_rt, "wait_until_running") as wait,
        patch.object(ecflow_rt, "sync_window") as sync,
        patch.object(ecflow_rt, "prune_cycle_dirs"),
    ):
        ecflow_rt.drive(_drive_args(port=31415))
    default_port.assert_not_called()
    ensure.assert_called_once_with(Path("/i"), "uecflow01", Path("/run"), 31415, "ursa")
    wait.assert_called_once_with("uecflow01", 31415)
    sync.assert_called_once_with("uecflow01", 31415, Path("/run"), cyc)


def test_ecflow_rt_drive_render_only(utc):
    config = _drive_config(None)  # None -> defaults via "config.user or {}"
    cyc = [utc(2026, 9, 13, 0)]
    with (
        patch.object(ecflow_rt.setup, "compose_configs"),
        patch.object(ecflow_rt.setup, "validate", return_value=config),
        patch.object(ecflow_rt, "deduce_cycles", return_value=cyc),
        patch.object(ecflow_rt, "gated_cycles", return_value=cyc),
        patch.object(ecflow_rt, "render_suite") as render,
        patch.object(ecflow_rt, "ensure_server") as ensure,
        patch.object(ecflow_rt, "wait_until_running") as wait,
        patch.object(ecflow_rt, "sync_window") as sync,
        patch.object(ecflow_rt, "prune_cycle_dirs") as prune,
    ):
        ecflow_rt.drive(_drive_args(render_only=True))
    render.assert_called_once()
    ensure.assert_not_called()
    wait.assert_not_called()
    sync.assert_not_called()
    prune.assert_not_called()


# parse_args / main


def test_ecflow_rt_parse_args_defaults():
    ns = ecflow_rt.parse_args(["--config", "c", "--install", "i", "--ecflow-host", "h"])
    assert ns.platform == "ursa"
    assert ns.port is None
    assert not ns.render_only
    assert not ns.verbose


def test_ecflow_rt_parse_args_flags():
    ns = ecflow_rt.parse_args(
        [
            "--config",
            "c",
            "--install",
            "i",
            "--ecflow-host",
            "h",
            "--port",
            "20",
            "--platform",
            "wcoss2",
            "--render-only",
            "--verbose",
        ]
    )
    assert ns.platform == "wcoss2"
    assert ns.port == 20
    assert ns.render_only
    assert ns.verbose


def test_ecflow_rt_main_success():
    with (
        patch.object(ecflow_rt, "parse_args") as parse_args,
        patch.object(ecflow_rt, "use_uwtools_logger") as logger,
        patch.object(ecflow_rt, "drive") as drive,
    ):
        parse_args.return_value = Mock(verbose=True)
        ecflow_rt.main()
    logger.assert_called_once_with(verbose=True)
    drive.assert_called_once_with(parse_args.return_value)


def test_ecflow_rt_main_failure_exits():
    with (
        patch.object(ecflow_rt, "parse_args", return_value=Mock(verbose=False)),
        patch.object(ecflow_rt, "use_uwtools_logger"),
        patch.object(ecflow_rt, "drive", side_effect=RuntimeError("boom")),
        raises(SystemExit) as excinfo,
    ):
        ecflow_rt.main()
    assert excinfo.value.code == 1
