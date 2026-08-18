"""
Support for validating AIGFS configurations.
"""

from datetime import datetime, timedelta
from pathlib import Path

from pydantic import BaseModel, model_validator


class App(BaseModel):
    """
    Model for the `app:` block.
    """

    cycle_freq: timedelta
    first_cycle: datetime
    last_cycle: datetime
    platform: str
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


def validate(config: dict[str, object]) -> Config:
    """
    Validate a config.
    """
    return Config.model_validate(config)
