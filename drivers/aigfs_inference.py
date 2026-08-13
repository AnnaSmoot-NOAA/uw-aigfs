"""
A driver for AIGFS inference.
"""

import dataclasses
import logging
from datetime import timedelta
from functools import partial
from pathlib import Path

import haiku as hk
import jax
import numpy as np
import pandas as pd
import xarray as xr
from graphcast import (  # type: ignore[import-untyped]
    autoregressive,
    casting,
    checkpoint,
    data_utils,
    graphcast,
    normalization,
    rollout,
)
from iotaa import Asset, collection, task
from uwtools.drivers.driver import DriverCycleBased

from .utils.grib2writer import Grib2Writer
from .utils.tasks import file

jax.config.update("jax_platforms", "cpu")


class AIGFSInference(DriverCycleBased):
    # Public tasks

    @task
    def initial_conditions(self):
        """
        Initial conditions.
        """
        taskname = "initial conditions"
        yield taskname
        ds = xr.Dataset()
        yield Asset(ds, lambda: bool(ds))
        req = file(self.config["ics_path"])
        yield req
        fcst_length = self.config["forecast_length"]
        fcst_freq = self.config["forecast_freq"]
        src = xr.load_dataset(req.ref)
        fcst_steps = fcst_length // fcst_freq
        src = _adjust_time(src, fcst_steps, taskname)
        ds.update(src)
        ds.attrs.update(src.attrs)

    @task
    def inputs_targets_forcings(self):
        """
        Inputs, targets, and forcings.
        """
        yield "inputs, targets, and forcings"
        datasets: list[xr.Dataset] = []
        yield Asset(datasets, lambda: bool(datasets))
        reqs = {
            "ics": self.initial_conditions(),
            "weights": self.model_weights(),
        }
        yield reqs
        freq = self.config["forecast_freq"]
        length = self.config["forecast_length"]
        datasets.extend(
            data_utils.extract_inputs_targets_forcings(
                reqs["ics"].ref,
                target_lead_times=slice(f"{freq}h", f"{length}h"),
                **dataclasses.asdict(reqs["weights"].ref[0].task_config),
            )
        )

    @task
    def normalization_stats(self):
        """
        Normalization stats.
        """
        yield "normalization stats"
        datasets: list[xr.Dataset] = []
        yield Asset(datasets, lambda: bool(datasets))
        diffs_stddev_path = self.config["diffs_stddev_path"]
        mean_path = self.config["mean_path"]
        stddev_path = self.config["stddev_path"]
        paths = (diffs_stddev_path, mean_path, stddev_path)
        yield [file(p) for p in paths]
        datasets.extend([xr.load_dataset(p) for p in paths])

    @task
    def model_weights(self):
        """
        Load the pre-trained model weights.
        """
        yield "model weights"
        weights: list[graphcast.CheckPoint] = []
        yield Asset(weights, lambda: bool(weights))
        req = file(self.config["model_weights_path"])
        yield req
        with req.ref.open("rb") as f:
            weights.append(checkpoint.load(f, graphcast.CheckPoint))

    @task
    def predictions(self):
        """
        Predictions.
        """
        yield "predictions"
        path = self.rundir / "aigfs.done"
        yield Asset(path, path.is_file)
        ics = self.initial_conditions()
        itfs = self.inputs_targets_forcings()
        model_weights = self.model_weights()
        norm_stats = self.normalization_stats()
        yield [ics, itfs, model_weights, norm_stats]
        ds = _clean_ics(ics.ref)
        converter = Grib2Writer(
            start_date=pd.to_datetime(ds.datetime.to_numpy()[0][-1]),
            case_name="aigfs",
            json_path=Path(self.config["json_path"]),
        )
        inputs, targets, forcings = itfs.ref
        diffs_stddev, mean, stddev = norm_stats.ref
        with_configs = partial(
            run_forward.apply,
            model_config=model_weights.ref[0].model_config,
            task_config=model_weights.ref[0].task_config,
            diffs_stddev=diffs_stddev,
            mean=mean,
            stddev=stddev,
        )
        with_params = partial(jax.jit(with_configs), params=model_weights.ref[0].params, state={})
        model = self.drop_state(with_params)
        self.rundir.mkdir(parents=True, exist_ok=True)
        converter.save_grib2(ds, self.rundir)
        rollout.chunked_prediction(
            self.rundir,
            converter,
            model,
            rng=jax.random.PRNGKey(0),
            inputs=inputs,
            targets_template=targets * np.nan,
            forcings=forcings,
        )
        path.touch()

    @collection
    def provisioned_rundir(self):
        """
        Run directory provisioned with all required content.
        """
        yield self.taskname("provisioned run directory")
        yield [self.runscript()]

    # Public helper methods

    @classmethod
    def driver_name(cls) -> str:
        """
        Returns the name of this driver.
        """
        return "aigfs_inference"

    @staticmethod
    def drop_state(fn):
        return lambda **kw: fn(**kw)[0]


# Public functions


def construct_wrapped_graphcast(model_config, task_config, diffs_stddev, mean, stddev):
    """
    Constructs and wraps the GraphCast Predictor.
    """
    # Deeper one-step predictor.
    predictor = graphcast.GraphCast(model_config, task_config)
    # Modify inputs/outputs to `graphcast.GraphCast` to handle conversion to
    # from/to float32 to/from BFloat16.
    predictor = casting.Bfloat16Cast(predictor)
    # Modify inputs/outputs to `casting.Bfloat16Cast` so the casting to/from
    # BFloat16 happens after applying normalization to the inputs/targets.
    predictor = normalization.InputsAndResiduals(
        predictor, diffs_stddev_by_level=diffs_stddev, mean_by_level=mean, stddev_by_level=stddev
    )
    # Wraps everything so the one-step model can produce trajectories.
    return autoregressive.Predictor(predictor, gradient_checkpointing=True)


@hk.transform_with_state
def run_forward(
    model_config, task_config, inputs, targets_template, forcings, diffs_stddev, mean, stddev
):  # pragma: no cover -- this is just a wrapper, there's nothing really to test
    predictor = construct_wrapped_graphcast(model_config, task_config, diffs_stddev, mean, stddev)
    return predictor(inputs, targets_template=targets_template, forcings=forcings)


# Private functions


def _adjust_time(ds: xr.Dataset, fcst_steps: int, taskname: str) -> xr.Dataset:
    if (fcst_steps + 2 - len(ds["time"])) > 0:
        logging.info("%s: Updating dataset to account for forecast length.", taskname)
        new_times = np.asarray([timedelta(hours=6) * f for f in range(fcst_steps + 2)]).astype(
            "timedelta64"
        )
        starttime = ds["datetime"][0][0].astype("datetime64[s]")
        new_datetimes = starttime.to_numpy() + new_times
        ds = ds.reindex(time=np.asarray(new_times).astype("timedelta64"))
        ds["datetime"][0] = new_datetimes
    return ds


def _clean_ics(ds):
    ds = ds.drop_vars(["geopotential_at_surface", "land_sea_mask", "total_precipitation_6hr"])
    for var in ds.data_vars:
        if "long_name" in ds[var].attrs:
            del ds[var].attrs["long_name"]
    ds = ds.isel(time=slice(1, 2))
    ds["time"] = ds["time"] - pd.Timedelta(hours=6)
    return ds
