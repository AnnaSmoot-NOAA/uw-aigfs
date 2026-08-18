from __future__ import annotations

from datetime import datetime, timedelta  # noqa: TC003
from pathlib import Path  # noqa: TC003

from pydantic import BaseModel, model_validator


class App(BaseModel):
    cycle_freq: timedelta
    first_cycle: datetime
    last_cycle: datetime
    platform: str
    rundir: Path

    @model_validator(mode="after")
    def first_and_last_cycle(self) -> App:
        if self.last_cycle < self.first_cycle:
            msg = "last_cycle cannot precede first_cycle"
            raise ValueError(msg)
        return self


class Config(BaseModel):
    app: App


def validate(config: dict[str, object]) -> Config:
    return Config.model_validate(config)
