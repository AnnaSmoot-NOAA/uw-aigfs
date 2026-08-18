"""
Reusable tasks for the AIGFS drivers.
"""

from collections.abc import Iterator
from pathlib import Path

from iotaa import Asset, external


@external
def file(path: Path | str) -> Iterator:
    """
    An existing file.

    :param path: Path to the file.
    """
    path = Path(path)
    yield "File %s" % (path)
    yield Asset(path, path.is_file)
