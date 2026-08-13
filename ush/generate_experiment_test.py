from datetime import timedelta
from pathlib import Path
from unittest.mock import Mock, patch

from pytest import raises

from . import generate_experiment
from .validation import Config, User


def test_ush_generate_experiment_generate_experiment_files(tmp_path):
    config = tmp_path / "experiment.yaml"
    experiment_config = Mock()
    with (
        patch.object(generate_experiment.config, "realize") as realize,
        patch.object(generate_experiment, "rocoto") as rocoto,
    ):
        rocoto.realize.return_value = True
        generate_experiment.generate_experiment_files(experiment_config, config)
    realize.assert_called_once_with(
        input_config=generate_experiment.APP_HOME / "parm" / "wflow" / "rocoto" / "aigfs_base.yaml",
        output_file=config,
        update_config=experiment_config,
    )
    rocoto.realize.assert_called_once_with(config=config, output_file=tmp_path / "rocoto.xml")


def test_ush_generate_experiment_generate_experiment_files_invalid_xml(logcap, tmp_path):
    config = tmp_path / "experiment.yaml"
    with (
        patch.object(generate_experiment.config, "realize"),
        patch.object(generate_experiment, "rocoto") as rocoto,
    ):
        rocoto.realize.return_value = False
        with raises(SystemExit):
            generate_experiment.generate_experiment_files(Mock(), config)
    assert "Invalid Rocoto XML" in logcap.text


def test_ush_generate_experiment_main():
    with (
        patch.object(generate_experiment, "generate_experiment_files") as generate_experiment_files,
        patch.object(generate_experiment, "parse_args") as parse_args,
        patch.object(generate_experiment, "prepare_configs") as prepare_configs,
        patch.object(generate_experiment, "set_up_experiment_directory") as s_u_e_d,
        patch.object(generate_experiment, "validate") as validate,
    ):
        s_u_e_d.return_value = (Mock(), Mock())
        generate_experiment.main()
        parse_args.assert_called_once_with()
        prepare_configs.assert_called_once_with(parse_args())
        validate.assert_called_once_with(prepare_configs().as_dict())
        s_u_e_d.assert_called_once_with(validate())
        generate_experiment_files.assert_called_once_with(prepare_configs(), s_u_e_d()[1])


def test_ush_generate_experiment_parse_args():
    with patch("sys.argv", ["prog", "/path/to/a.yaml", "/path/to/b.yaml"]):
        result = generate_experiment.parse_args()
    assert result == [Path("/path/to/a.yaml"), Path("/path/to/b.yaml")]


def test_ush_generate_experiment_prepare_configs(tmp_path):
    user_config_files = [tmp_path / "a.yaml"]
    mock_experiment_config = Mock()
    with patch.object(generate_experiment, "compose") as compose:
        compose.side_effect = [{"user": {"platform": "testmachine"}}, mock_experiment_config]
        result = generate_experiment.prepare_configs(user_config_files)
    assert result is mock_experiment_config
    mock_experiment_config.update_from.assert_called_once_with(
        {"user": {"app_home": str(generate_experiment.APP_HOME)}}
    )
    # First call: Compose user configs.
    # Second call: Compose with default, platform, and user configs.
    assert compose.call_count == 2
    second_call = compose.call_args_list[1]
    parmdir = generate_experiment.APP_HOME / "parm"
    assert second_call[1]["configs"] == [
        parmdir / "default_config.yaml",
        parmdir / "machines" / "testmachine.yaml",
        *user_config_files,
    ]
    assert second_call[1]["realize"] is True


def test_ush_generate_experiment_set_up_experiment_directory(logcap, tmp_path, utc):
    experiment_dir = tmp_path / "myexp"
    validated = Config(
        user=User(
            cycle_freq=timedelta(hours=6),
            experiment_dir=experiment_dir,
            first_cycle=utc(2025, 10, 1, 18),
            last_cycle=utc(2025, 10, 2, 18),
            platform="ursa",
        )
    )
    result_dir, result_file = generate_experiment.set_up_experiment_directory(validated)
    assert result_dir == experiment_dir
    assert result_dir.is_dir()
    assert result_file == experiment_dir / "experiment.yaml"
    assert f"Experiment will be set up here: {result_dir}" in logcap.text
