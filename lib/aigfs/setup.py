"""
Support for setting up AIGFS runtime assets.
"""

import argparse
import logging
import os
import sys
from pathlib import Path
from typing import cast

from uwtools.api.config import YAMLConfig, compose
from uwtools.api.config import realize as realize_config
from uwtools.api.logging import use_uwtools_logger
from uwtools.api.rocoto import realize as realize_rocoto

from aigfs.validation import Config, validate

_APP_HOME = Path(__file__).parent.parent.parent.resolve()


def generate_configs(update_config: YAMLConfig, aigfs_config: Path, engine: str = "rocoto") -> None:
    """
    Generate the AIGFS config and workflow manager artifacts.
    """
    workflow_config = _APP_HOME / "etc" / "workflow" / engine / "base.yaml"
    realize_config(
        input_config=workflow_config, output_file=aigfs_config, update_config=update_config
    )
    rocoto_xml = aigfs_config.parent / "rocoto.xml"
    rocoto_valid = realize_rocoto(config=aigfs_config, output_file=rocoto_xml)
    if not rocoto_valid:
        logging.error("Invalid Rocoto XML")
        sys.exit(1)


def main() -> None:
    """
    Stage the AIGFS config and workflow manager artifacts in the run directory.
    """
    use_uwtools_logger()
    user_config_files = parse_args()
    update_config = prepare_configs(user_config_files)
    validated = validate(update_config.as_dict())
    _, aigfs_config = set_up_rundir(validated)
    generate_configs(update_config, aigfs_config)


def parse_args() -> list[Path]:
    """
    Parse command-line arguments.
    """
    parser = argparse.ArgumentParser(description="Configure AIGFS from user config files.")
    parser.add_argument(
        "user_config_files",
        help="paths to the user config files",
        metavar="PATH",
        nargs="+",
        type=Path,
    )
    return cast(list[Path], parser.parse_args().user_config_files)


def prepare_configs(user_config_files: list[Path]) -> YAMLConfig:
    """
    Compose base, user, and platform configs.
    """
    user_config = compose(configs=cast(list[str | Path], user_config_files), output_file=os.devnull)
    platform = user_config["app"]["platform"]
    base_config = _APP_HOME / "etc" / "base.yaml"
    platform_config = _APP_HOME / "etc" / "platform" / f"{platform}.yaml"
    # Make sure user_config is last to override any settings from supplementals.
    update_config = compose(
        configs=[base_config, platform_config, *user_config_files],
        realize=True,
        output_file=os.devnull,
    )
    update_config.update_from({"app": {"home": str(_APP_HOME)}})
    return cast(YAMLConfig, update_config)


def set_up_rundir(validated: Config) -> tuple[Path, Path]:
    """
    Create the run directory and write aigfs.yaml.
    """
    rundir = validated.app.rundir
    logging.info("AIGFS will be set up here: %s", rundir)
    rundir.mkdir(parents=True, exist_ok=True)
    aigfs_config = rundir / "aigfs.yaml"
    return rundir, aigfs_config


if __name__ == "__main__":
    main()  # pragma: no cover
