from pathlib import Path
from unittest.mock import Mock, patch

from pytest import mark, raises
from uwtools.api.config import YAMLConfig

from aigfs import setup


@mark.parametrize("workflow", ["rocoto", "ecflow"])
def test_setup_compose_configs(tmp_path, workflow):
    platform = "ursa"
    user_config_files = [Path("/path/to/a.yaml")]
    with (
        patch.object(setup, "compose_to_dict") as compose_to_dict,
        patch.object(setup, "NamedTemporaryFile") as NamedTemporaryFile,
    ):
        compose_to_dict.return_value = {"app": {"rundir": "/some/path"}}
        reserved_path = tmp_path / "reserved.yaml"
        tmp = Mock()
        tmp.name = str(reserved_path)
        NamedTemporaryFile().__enter__.return_value = tmp
        result = setup.compose_configs(platform, user_config_files, workflow=workflow)
    assert result == {"app": {"rundir": "/some/path"}}
    compose_to_dict.assert_called_once_with(
        [
            setup.ETCDIR / "base.yaml",
            setup.ETCDIR / "workflow" / workflow / "base.yaml",
            setup.PLATFORMDIR / "ursa.yaml",
            Path("/path/to/a.yaml"),
            reserved_path,
        ],
        realize=True,
    )
    expected = {"app": {"home": str(setup.HOMEDIR), "platform": {"name": "ursa"}}}
    assert YAMLConfig(reserved_path) == expected


def test_setup_compose_configs_ecflow(tmp_path):
    platform = "ursa"
    user_config_files = [Path("/path/to/a.yaml")]
    with (
        patch.object(setup, "compose_to_dict") as compose_to_dict,
        patch.object(setup, "NamedTemporaryFile") as NamedTemporaryFile,
    ):
        compose_to_dict.return_value = {"app": {"rundir": "/some/path"}}
        reserved_path = tmp_path / "reserved.yaml"
        tmp = Mock()
        tmp.name = str(reserved_path)
        NamedTemporaryFile().__enter__.return_value = tmp
        setup.compose_configs(platform, user_config_files, workflow="ecflow")
    compose_to_dict.assert_called_once_with(
        [
            setup.ETCDIR / "base.yaml",
            setup.ETCDIR / "workflow" / "ecflow" / "base.yaml",
            setup.PLATFORMDIR / "ursa.yaml",
            Path("/path/to/a.yaml"),
            reserved_path,
        ],
        realize=True,
    )


def test_setup_main():
    with (
        patch.object(setup, "compose_configs") as compose_configs,
        patch.object(setup, "parse_args") as parse_args,
        patch.object(setup, "set_up_rundir") as set_up_rundir,
        patch.object(setup, "validate") as validate,
    ):
        args = Mock(platform="ursa", workflow="rocoto", user_config_files=[Path("/path/to/a.yaml")])
        parse_args.return_value = args
        compose_configs.return_value = {"app": {"key": "val"}}
        setup.main()
        parse_args.assert_called_once_with()
        compose_configs.assert_called_once_with("ursa", [Path("/path/to/a.yaml")], "rocoto")
        config = {"app": {"key": "val"}}
        validate.assert_called_once_with(config)
        set_up_rundir.assert_called_once_with(config, "rocoto")


def test_setup_parse_args():
    with (
        patch.object(setup, "platforms", return_value=["ursa"]),
        patch("sys.argv", ["prog", "ursa", "/path/to/a.yaml", "/path/to/b.yaml"]),
    ):
        result = setup.parse_args()
    assert result.platform == "ursa"
    assert result.workflow == "rocoto"
    assert result.user_config_files == [Path("/path/to/a.yaml"), Path("/path/to/b.yaml")]


def test_setup_parse_args_workflow_ecflow():
    with (
        patch.object(setup, "platforms", return_value=["ursa"]),
        patch("sys.argv", ["prog", "ursa", "/path/to/a.yaml", "--workflow", "ecflow"]),
    ):
        result = setup.parse_args()
    assert result.workflow == "ecflow"


def test_setup_parse_args_ecflow():
    with (
        patch.object(setup, "platforms", return_value=["ursa"]),
        patch("sys.argv", ["prog", "--workflow", "ecflow", "ursa", "/path/to/a.yaml"]),
    ):
        result = setup.parse_args()
    assert result.workflow == "ecflow"
    assert result.platform == "ursa"


def test_setup_set_up_rundir(logcap, tmp_path):
    rundir = tmp_path / "rundir"
    config: dict = {"app": {"rundir": str(rundir)}}
    with (
        patch.object(setup, "YAMLConfig") as YAMLConfig,
        patch.object(setup, "rocoto") as rocoto,
    ):
        rocoto.realize.return_value = True
        setup.set_up_rundir(config, "rocoto")
    assert rundir.is_dir()
    YAMLConfig.return_value.dump.assert_called_once_with(rundir / "aigfs.yaml")
    rocoto.realize.assert_called_once_with(YAMLConfig(config), rundir / "rocoto.xml")
    assert f"AIGFS will be set up here: {rundir}" in logcap.text


def test_setup_set_up_rundir_invalid_xml(logcap, tmp_path):
    rundir = tmp_path / "rundir"
    config: dict = {"app": {"rundir": str(rundir)}}
    with (
        patch.object(setup, "YAMLConfig"),
        patch.object(setup, "rocoto") as rocoto,
    ):
        rocoto.realize.return_value = False
        with raises(SystemExit):
            setup.set_up_rundir(config, "rocoto")
    assert "Invalid Rocoto XML" in logcap.text


def test_setup_set_up_rundir_ecflow(logcap, tmp_path):
    rundir = tmp_path / "rundir"
    config: dict = {"app": {"rundir": str(rundir)}}
    with (
        patch.object(setup, "YAMLConfig") as YAMLConfig,
        patch.object(setup, "ecflow") as ecflow,
    ):
        setup.set_up_rundir(config, "ecflow")
    assert rundir.is_dir()
    assert YAMLConfig.call_args_list[0].args[0] == config
    assert YAMLConfig.call_args_list[1].args[0] == config
    YAMLConfig.return_value.dump.assert_called_once_with(rundir / "aigfs.yaml")
    ecflow.realize.assert_called_once_with(
        YAMLConfig(config), rundir, scripts_path=rundir / "ecf"
    )
    assert f"AIGFS will be set up here: {rundir}" in logcap.text


