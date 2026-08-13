from __future__ import annotations

from datetime import datetime, timedelta  # noqa: TC003
from pathlib import Path  # noqa: TC003

from pydantic import BaseModel, model_validator


class Config(BaseModel):
    user: User


class User(BaseModel):
    cycle_freq: timedelta
    experiment_dir: Path
    first_cycle: datetime
    last_cycle: datetime
    platform: str

    @model_validator(mode="after")
    def first_and_last_cycle(self) -> User:
        if self.last_cycle < self.first_cycle:
            msg = "last_cycle cannot precede first_cycle"
            raise ValueError(msg)
        return self


def validate(config: dict[str, object]) -> Config:
    return Config.model_validate(config)
