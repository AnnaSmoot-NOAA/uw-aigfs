from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import BaseModel, model_validator

if TYPE_CHECKING:
    from datetime import datetime, timedelta
    from pathlib import Path


class Config(BaseModel):
    user: User


class User(BaseModel):  # pragma: no cover
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


def validate(config: dict) -> Config:  # pragma: no cover
    return Config(**config)
