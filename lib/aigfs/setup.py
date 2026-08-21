"""
Support for setting up AIGFS runtime assets.
"""

import argparse
import logging
import sys
from pathlib import Path
from tempfile import NamedTemporaryFile

from uwtools.api import rocoto
from uwtools.api.config import YAMLConfig, compose_to_dict
from uwtools.api.logging import use_uwtools_logger

from aigfs.validation import validate

_HOMEDIR = Path(__file__).parent.parent.parent.resolve()
_ETCDIR = _HOMEDIR / "etc"
_PLATFORMDIR = _ETCDIR / "platform"


def compose_configs(platform: str, user_config_files: list[Path]) -> dict:
    """
    Compose and realize base, platform, and user configs.
    """
    with NamedTemporaryFile(delete=True) as tmp:
        reserved = Path(tmp.name)
        YAMLConfig({"app": {"home": str(_HOMEDIR), "platform": {"name": platform}}}).dump(reserved)
        configs: list[str | Path] = [
            _ETCDIR / "base.yaml",
            _ETCDIR / "workflow" / "rocoto" / "base.yaml",
            _PLATFORMDIR / f"{platform}.yaml",
            *user_config_files,
            reserved,
        ]
        return compose_to_dict(configs, realize=True)


def main() -> None:
    """
    Stage the AIGFS config and workflow manager artifacts in the run directory.
    """
    use_uwtools_logger()
    args = parse_args()
    config = compose_configs(args.platform, args.user_config_files)
    validate({"app": config["app"]})
    set_up_rundir(config)


def parse_args() -> argparse.Namespace:
    """
    Parse command-line arguments.
    """
    platforms = [x.with_suffix("").name for x in _PLATFORMDIR.glob("*.yaml")]
    parser = argparse.ArgumentParser(description="Configure AIGFS.")
    parser.add_argument(
        "platform",
        choices=platforms,
        help="one of: %s" % ", ".join(platforms),
        metavar="PLATFORM",
        type=str,
    )
    parser.add_argument(
        "user_config_files",
        help="path to user config file",
        metavar="PATH",
        nargs="+",
        type=Path,
    )
    return parser.parse_args()


def set_up_rundir(config: dict) -> None:
    """
    Create and populate the run directory.
    """
    rundir = Path(config["app"]["rundir"])
    logging.info("AIGFS will be set up here: %s", rundir)
    rundir.mkdir(parents=True, exist_ok=True)
    final = rundir / "aigfs.yaml"
    YAMLConfig(config).dump(final)
    if not rocoto.realize(YAMLConfig(config), rundir / "rocoto.xml"):
        logging.error("Invalid Rocoto XML")
        sys.exit(1)


if __name__ == "__main__":
    main()  # pragma: no cover
