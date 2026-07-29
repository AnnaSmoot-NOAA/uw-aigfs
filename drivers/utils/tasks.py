"""
Reusable tasks for the AIGFS drivers.
"""

from pathlib import Path

from iotaa import Asset, external


@external
def file(path: Path | str):
    """
    An existing file.

    :param path: Path to the file.
    """
    path = Path(path)
    yield "File %s" % (path)
    yield Asset(path, path.is_file)
