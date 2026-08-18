from datetime import timedelta
from pathlib import Path
from unittest.mock import Mock, patch

from pytest import raises

from aigfs import setup
from aigfs.validation import App, Config


def test_ush_setup_generate_configs(tmp_path):
    path = tmp_path / "aigfs.yaml"
    update_config = Mock()
    with (
        patch.object(setup, "realize_config") as realize_config,
        patch.object(setup, "realize_rocoto") as realize_rocoto,
    ):
        realize_rocoto.return_value = True
        setup.generate_configs(update_config=update_config, aigfs_config=path)
    realize_config.assert_called_once_with(
        input_config=setup.APP_HOME / "etc" / "workflow" / "rocoto" / "base.yaml",
        output_file=path,
        update_config=update_config,
    )
    realize_rocoto.assert_called_once_with(config=path, output_file=tmp_path / "rocoto.xml")


def test_ush_setup_generate_configs_invalid_xml(logcap, tmp_path):
    path = tmp_path / "aigfs.yaml"
    with (
        patch.object(setup, "realize_config"),
        patch.object(setup, "realize_rocoto") as realize_rocoto,
    ):
        realize_rocoto.return_value = False
        with raises(SystemExit):
            setup.generate_configs(update_config=Mock(), aigfs_config=path)
    assert "Invalid Rocoto XML" in logcap.text


def test_ush_setup_main():
    with (
        patch.object(setup, "generate_configs") as generate_configs,
        patch.object(setup, "parse_args") as parse_args,
        patch.object(setup, "prepare_configs") as prepare_configs,
        patch.object(setup, "set_up_rundir") as set_up_rundir,
        patch.object(setup, "validate") as validate,
    ):
        set_up_rundir.return_value = (Mock(), Mock())
        setup.main()
        parse_args.assert_called_once_with()
        prepare_configs.assert_called_once_with(parse_args())
        validate.assert_called_once_with(prepare_configs().as_dict())
        set_up_rundir.assert_called_once_with(validate())
        generate_configs.assert_called_once_with(prepare_configs(), set_up_rundir()[1])


def test_ush_setup_parse_args():
    with patch("sys.argv", ["prog", "/path/to/a.yaml", "/path/to/b.yaml"]):
        result = setup.parse_args()
    assert result == [Path("/path/to/a.yaml"), Path("/path/to/b.yaml")]


def test_ush_setup_prepare_configs(tmp_path):
    user_config_files = [tmp_path / "a.yaml"]
    mock_update_config = Mock()
    with patch.object(setup, "compose") as compose:
        compose.side_effect = [{"app": {"platform": "test"}}, mock_update_config]
        result = setup.prepare_configs(user_config_files)
    assert result is mock_update_config
    mock_update_config.update_from.assert_called_once_with({"app": {"home": str(setup.APP_HOME)}})
    # First call: Compose user configs.
    # Second call: Compose with default, platform, and user configs.
    assert compose.call_count == 2
    second_call = compose.call_args_list[1]
    etcdir = setup.APP_HOME / "etc"
    assert second_call[1]["configs"] == [
        etcdir / "base.yaml",
        etcdir / "platform" / "test.yaml",
        *user_config_files,
    ]
    assert second_call[1]["realize"] is True


def test_ush_setup_set_up_rundir(logcap, tmp_path, utc):
    rundir = tmp_path / "myexp"
    validated = Config(
        app=App(
            cycle_freq=timedelta(hours=6),
            rundir=rundir,
            first_cycle=utc(2025, 10, 1, 18),
            last_cycle=utc(2025, 10, 2, 18),
            platform="ursa",
        )
    )
    result_dir, result_file = setup.set_up_rundir(validated)
    assert result_dir == rundir
    assert result_dir.is_dir()
    assert result_file == rundir / "aigfs.yaml"
    assert f"AIGFS will be set up here: {result_dir}" in logcap.text
