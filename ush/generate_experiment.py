#!/usr/bin/env python3

import argparse
import logging
import os
import sys
from pathlib import Path

from uwtools.api import rocoto
from uwtools.api.config import YAMLConfig, compose, realize
from uwtools.api.logging import use_uwtools_logger

APP_HOME = Path(__file__).parent.parent.resolve()
sys.path.append(str(APP_HOME))

from ush.validation import Config, validate  # noqa: E402


def generate_experiment_files(
    experiment_config: YAMLConfig,
    experiment_file: Path,
    wflow_manager: str = "rocoto",
) -> None:
    """
    Generate the workflow manager artifacts and the experiment YAML.
    """
    workflow_config = APP_HOME / "parm" / "wflow" / wflow_manager / "aigfs_base.yaml"
    realize(
        input_config=workflow_config,
        output_file=experiment_file,
        update_config=experiment_config,
    )
    rocoto_xml = experiment_file.parent / "rocoto.xml"
    rocoto_valid = rocoto.realize(config=experiment_file, output_file=rocoto_xml)
    if not rocoto_valid:
        logging.error("Invalid Rocoto XML")
        sys.exit(1)


def main() -> None:
    """
    Stage the workflow manager artifacts and experiment YAML in the experiment directory.
    """
    use_uwtools_logger()
    user_config_files = parse_args()
    experiment_config = prepare_configs(user_config_files)
    validated = validate(experiment_config.as_dict())
    _, experiment_file = setup_experiment_directory(validated)
    generate_experiment_files(experiment_config, experiment_file)


def parse_args() -> list[Path]:
    """
    Parse command-line arguments.
    """
    parser = argparse.ArgumentParser(description="Configure an experiment from user config files.")
    parser.add_argument(
        "user_config_files",
        help="paths to the user config files",
        metavar="PATH",
        nargs="+",
        type=Path,
    )
    return parser.parse_args().user_config_files


def prepare_configs(user_config_files: list[Path]) -> YAMLConfig:
    """
    Combine base, user, and platform configs into one experiment config.
    """
    # Set up the experiment.
    user_config = compose(configs=user_config_files, output_file=os.devnull)
    machine = user_config["user"]["platform"]

    default_config = APP_HOME / "ush" / "default_config.yaml"
    platform_config = APP_HOME / "parm" / "machines" / f"{machine}.yaml"

    # Make sure user_config is last to override any settings from supplementals.
    experiment_config = compose(
        configs=[default_config, platform_config, *user_config_files],
        realize=True,
        output_file=os.devnull,
    )
    experiment_config.update_from({"user": {"app_home": str(APP_HOME)}})

    return experiment_config


def setup_experiment_directory(validated: Config) -> tuple[Path, Path]:
    """
    Create the experiment directory and write experiment.yaml.
    """
    experiment_dir = validated.user.experiment_dir
    logging.info("Experiment will be set up here: %s", experiment_dir)
    experiment_dir.mkdir(parents=True, exist_ok=True)
    experiment_file = experiment_dir / "experiment.yaml"
    return experiment_dir, experiment_file


if __name__ == "__main__":
    main()  # pragma: no cover
