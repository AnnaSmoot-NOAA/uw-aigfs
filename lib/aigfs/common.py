"""
Shared logic.
"""

from functools import cache
from pathlib import Path

HOMEDIR = Path(__file__).parent.parent.parent.resolve()
ETCDIR = HOMEDIR / "etc"
PLATFORMDIR = ETCDIR / "platform"


@cache
def platforms() -> list[str]:
    return sorted(x.with_suffix("").name for x in PLATFORMDIR.glob("*.yaml"))
