"""
Support for validating AIGFS configurations.
"""

import logging
import sys
from datetime import datetime, timedelta
from pathlib import Path
from pprint import pformat

from pydantic import BaseModel, ValidationError, model_validator

# Validation classes


class Partition(BaseModel):
    """
    Model for the `app.platform.partition:` block.
    """

    compute: str | None = None
    netaccess: str | None = None
    task: str | None = None


class Platform(BaseModel):
    """
    Model for the `app.platform:` block.
    """

    name: str
    partition: Partition | None = None


class App(BaseModel):
    """
    Model for the `app:` block.
    """

    cycle_freq: timedelta
    first_cycle: datetime
    home: Path
    last_cycle: datetime
    modeldir: Path
    platform: Platform
    rundir: Path

    @model_validator(mode="after")
    def first_and_last_cycle(self) -> "App":
        if self.last_cycle < self.first_cycle:
            msg = "last_cycle cannot precede first_cycle"
            raise ValueError(msg)
        return self


class Config(BaseModel):
    """
    Model for the overall AIGFS config.
    """

    app: App


# Public functions


def validate(config: dict[str, object]) -> Config:
    """
    Validate a config.
    """
    try:
        return Config.model_validate(config)
    except ValidationError as e:
        logging.error("Config validation failed:")
        lines = pformat(e.errors()).split("\n")
        for line in lines:
            logging.error(line)
        sys.exit(1)
