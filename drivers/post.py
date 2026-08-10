import logging
from functools import cached_property
from pathlib import Path
from shutil import copy

from iotaa import Asset, Node, collection, external, task
from uwtools.api.driver import DriverCycleLeadtimeBased
from uwtools.utils.processing import run_shell_cmd


class AIGFSPost(DriverCycleLeadtimeBased):
    # Public tasks

    @collection
    def delivery(self):
        """
        GRIB index files copied to destination.
        """
        yield "Delivered GRIB indexes"
        d = self._deliver_to
        if isinstance(d, Path):
            yield [self._idx_delivered(path) for path in self._delivered2idx]
        else:
            yield d

    @collection
    def provisioned_rundir(self):
        """
        Run directory provisioned with all required content.
        """
        yield self.taskname("provisioned run directory")
        required = [self.runscript()]
        yield required

    @collection
    def indexes(self):
        """
        GRIB index files.
        """
        yield "GRIB indexes"
        yield [self._idx(path) for path in self._idx2grib]

    # Private tasks

    @external
    def _gribfile(self, path: Path):
        yield f"GRIB file {path}"
        yield Asset(path, path.is_file)

    @task
    def _idx(self, path: Path):
        taskname = f"GRIB index {path}"
        yield taskname
        yield Asset(path, path.is_file)
        req = self._gribfile(self._idx2grib[path])
        yield req
        path.parent.mkdir(parents=True, exist_ok=True)
        cmd = f"wgrib2 -s {req.ref} >{path}.tmp && mv {path}.tmp {path}"
        run_shell_cmd(cmd, cwd=path.parent, taskname=taskname)

    @task
    def _idx_delivered(self, path: Path):
        taskname = f"Delivered GRIB index {path}"
        yield taskname
        yield Asset(path, path.is_file)
        req = self._idx(self._delivered2idx[path])
        yield req
        path.parent.mkdir(parents=True, exist_ok=True)
        copy(req.ref, path)
        logging.info("%s: Copied %s -> %s", taskname, req.ref, path)

    @external
    def _valid_driver_config(self, reason: str):
        yield reason
        yield Asset(None, lambda: False)

    # Public helper methods

    @classmethod
    def driver_name(cls) -> str:
        """
        Returns the name of this driver.
        """
        return "aigfs_post"

    @property
    def output(self) -> dict[str, Path] | dict[str, list[Path]]:
        """
        Returns a description of the file(s) created when this component runs.
        """
        return {"idx": [Path(x) for x in self._idx2grib]}

    # Private helper methods

    @cached_property
    def _deliver_to(self) -> Path | Node:
        key = "deliver_to"
        if key in self.config:
            return Path(self.config[key])
        reason = f"Definition of '{key}' in 'delivery' task config block"
        return self._valid_driver_config(reason)

    @cached_property
    def _delivered2idx(self) -> dict[Path, Path]:
        """
        A mapping from delivered GRIB index paths to generated GRIB index paths.
        """
        d = self._deliver_to
        assert isinstance(d, Path)
        srcs = self._idx2grib.keys()
        dsts = [d / x.name for x in srcs]
        return dict(zip(dsts, srcs, strict=True))

    @cached_property
    def _idx2grib(self) -> dict[Path, Path]:
        """
        A mapping from generated GRIB index paths to their source GRIB files.
        """
        srcs = [Path(x) for x in self.config["inputfiles"]]
        dsts = [Path(self.config["outputdir"], f"{x.name}.idx") for x in srcs]
        return dict(zip(dsts, srcs, strict=True))
