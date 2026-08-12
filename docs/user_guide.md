# User Guide

[← Back to Index](index.md)

Welcome to the ***uw-aigfs*** User Guide. This guide describes how to set up your environment, configure an experiment, and run the AIGFS workflow using the ***Rocoto*** workflow manager.

> **⚠️ Work in Progress**
> This project is currently under active development and may undergo significant breaking changes without notice.

## Table of Contents

- [Overview](#overview)
- [Prerequisites](#prerequisites)
- [Getting Started](#getting-started)
- [Setting Up the Environment](#setting-up-the-environment)
- [Configuring an Experiment](#configuring-an-experiment)
  - [Default Configuration](#default-configuration)
  - [User Config YAML](#user-config-yaml)
- [Generating the Experiment](#generating-the-experiment)
- [Running the Workflow](#running-the-workflow)
- [Workflow Stages](#workflow-stages)
  - [Prep: Initial Conditions Generation](#prep-initial-conditions-generation)
  - [Forecast: GraphCast Inference](#forecast-graphcast-inference)
  - [Post-Processing](#post-processing)

---

## Overview

***uw-aigfs*** drives an AI-based medium-range global forecast using the [GraphCast](https://github.com/noaa-emc/graphcast) model, orchestrated via [uwtools](https://uwtools.readthedocs.io/en/main/) and the [Rocoto](https://github.com/christopherwharrop/rocoto) workflow manager. The workflow consists of three sequential stages per forecast cycle:

1. **Prep** — Extract variables from GFS GRIB2 files and produce a netCDF initial-conditions file for ***GraphCast***.
2. **Forecast** — Run ***GraphCast*** inference to produce GRIB2 output files at each forecast lead time.
3. **Post** — Generate GRIB2 index files and deliver them to the forecast output directory.

---

## Prerequisites

Before using ***uw-aigfs***, ensure the following are available on your system:

| Requirement | Notes |
|---|---|
| Supported platform | Ursa or WCOSS2 |
| Pre-trained ***GraphCast*** model weights | See your platform config for the expected path |
| GFS GRIB2 input data | 0.25° analysis and short-range forecast files |
| `wgrib2` | Must be loadable as a module or available in `PATH` |
| Git | For cloning the repository |
| `curl` | Used by the setup script to install Miniforge |

> **Note on disk space:** The conda environment installation requires several gigabytes of disk space. Consider cloning `uw-aigfs` to a location with a sufficiently large disk quota, rather than your HPC home directory.

---

## Getting Started

Clone the repository:

```bash
git clone https://github.com/NOAA-GSL/uw-aigfs.git
cd uw-aigfs
```

---

## Setting Up the Environment

***uw-aigfs*** installs and manages its own conda installation in the `conda/` subdirectory of the repository root. To build the environment, run:

```bash
make env
```

This installs [Miniforge](https://github.com/conda-forge/miniforge) and creates the `aigfs` conda environment defined by `environment.yml`.

For an environment that also includes developer tools (linters, test frameworks, etc.), use instead:

```bash
make devenv
```

Once the environment is built, activate it for a given platform by sourcing the module loader from the repository root:

```bash
source load_wflow_modules.sh <platform>
```

Supported values for `<platform>`:

| Platform | Description |
|---|---|
| `ursa` | Activates the locally installed conda `aigfs` environment |
| `wcoss2` | Loads the `wflow_wcoss` module from `modulefiles/` |

> **Tip:** This `source` command must be run each time you open a new shell. The platform-specific environment it activates is also the one used by the workflow jobs at runtime.

---

## Configuring an Experiment

### Default Configuration

`ush/default_config.yaml` contains the baseline settings for all workflow stages. It is organized into top-level blocks that correspond to the workflow stages and follow the [uwtools YAML](https://uwtools.readthedocs.io/en/main/sections/user_guide/yaml/components/index.html) conventions:

| Block | Purpose |
|---|---|
| `user` | Cycle dates, platform, experiment directory, and GFS data path |
| `timevars` | ***Jinja2*** template variables for date/time formatting used throughout the config |
| `prep` | ICS generation: GFS file staging and ***wgrib2*** variable extraction |
| `forecast` | ***GraphCast*** model inference: model weights, normalization stats, and forecast parameters |
| `post` | Post-processing: GRIB2 index generation and file delivery |

The `platform` block supplies scheduler and account settings. A machine-specific YAML in `parm/machine/` (e.g., `parm/machine/ursa.yaml`) is automatically merged based on the value of `user.platform`.

### User Config YAML

You can override any default values by providing one or more user YAML files. These files must follow the same block structure as `default_config.yaml`, and later files take precedence over earlier ones.

**Minimal required configuration:**

```yaml
user:
  experiment_dir: /path/to/your/experiment/directory
  gfs_data: /path/to/gfs/data
  platform: ursa
  first_cycle: !datetime 2025-10-21T00
  last_cycle: !datetime 2025-10-21T00
platform:
  account: your_hpc_account
```

> The `user.experiment_dir` and `user.gfs_data` paths must be set in your user config — they have no default values.

**Adjusting forecast length and frequency:**

```yaml
forecast:
  aigfs_inference:
    forecast_length: 240   # hours; default is 120
    forecast_freq: 6       # output frequency in hours; default is 6
```

**Changing the pretrained model path:**

```yaml
platform:
  pretrained_model_path: /path/to/your/graphcast/weights
```

The `pretrained_model_path` directory is expected to contain:

```
fix/
  params/     # model weight .npz file
  stats/      # diffs_stddev_by_level.nc, mean_by_level.nc, stddev_by_level.nc
  tables/     # JSON metadata files for GRIB2 output
```

---

## Generating the Experiment

With the environment activated (see [Setting Up the Environment](#setting-up-the-environment)), run the experiment generator from the repository root:

```bash
python ush/generate_experiment.py [additional.yaml ...] user.yaml
```

Multiple YAML files may be provided; later files take precedence over earlier ones. The generator automatically merges `ush/default_config.yaml` and the appropriate machine YAML (`parm/machine/<platform>.yaml`) before applying your user configs.

The following files are written to `user.experiment_dir`:

| File | Contents |
|---|---|
| `experiment.yaml` | Fully realized experiment configuration |
| `rocoto.xml` | ***Rocoto*** workflow definition, ready to run |

If the experiment directory does not exist, it will be created. The generator validates the `user` section of the config with [Pydantic](https://docs.pydantic.dev/) and exits with an error if required fields are missing or invalid.

---

## Running the Workflow

On RDHPCS platforms, ***Rocoto*** is available via system module. Run the following command to load it into your environment:

```bash
module load rocoto
```

From your experiment directory, run:

```bash
rocotorun -w rocoto.xml -d rocoto.db
```

The `rocoto.db` file will not exist until `rocotorun` is run the first time. Re-run this command periodically to advance the workflow as jobs complete. To check the status of all tasks:

```bash
rocotostat -w rocoto.xml -d rocoto.db
```

Individual task logs are written to `<experiment_dir>/log/`. An overall workflow log is written to `<experiment_dir>/workflow.log`.

The ***uwtools*** package provides a tool to help iterate through the entire workflow: `uw rocoto iterate`. See the [uwtools Rocoto tool documentation](https://uwtools.readthedocs.io/en/main/sections/user_guide/cli/tools/rocoto.html#cli-rocoto-iterate-examples) for details.

---

## Workflow Stages

### Prep: Initial Conditions Generation

The `task_prep` ***Rocoto*** task runs `drivers/generate_ics.py` (driver class `AIGFSICs`). It:

1. Hard-links GFS GRIB2 files from `user.gfs_data` into the cycle's `prep/data/` subdirectory. The files required are:
   - Two timesteps from the previous two cycles (for temporal interpolation)
   - The analysis and short-range forecast from the current cycle
2. Runs `wgrib2` commands (defined by `parm/wgrib2_data.yaml`) to extract meteorological variables at the required pressure levels into individual netCDF files.
3. Merges the extracted netCDF files into a single initial-conditions file:

   ```
   <experiment_dir>/<YYYYMMDDHH>/prep/aigfs.t<HH>z.ic.nc
   ```

   Variables are renamed and units are converted to match ***GraphCast***'s expectations (e.g., geopotential is converted from m to m²/s² by multiplying by 9.80665; total precipitation is converted from kg/m² to m by dividing by 1000).

### Forecast: GraphCast Inference

The `task_forecast` ***Rocoto*** task runs `drivers/run_graphcast.py` (driver class `AIGFSInference`). It depends on `task_prep` completing successfully. The task:

1. Loads the initial-conditions netCDF file produced by the prep step.
2. Loads the pre-trained ***GraphCast*** model weights (`.npz`) from `platform.pretrained_model_path`.
3. Loads the normalization statistics (`diffs_stddev_by_level.nc`, `mean_by_level.nc`, `stddev_by_level.nc`).
4. Runs autoregressive ***GraphCast*** inference for `forecast.aigfs_inference.forecast_length` hours at `forecast.aigfs_inference.forecast_freq`-hour intervals.
5. Writes GRIB2 output files to:

   ```
   <experiment_dir>/<YYYYMMDDHH>/forecast/aigfs.t<HH>z.sfc.f<FFF>.grib2
   <experiment_dir>/<YYYYMMDDHH>/forecast/aigfs.t<HH>z.pres.f<FFF>.grib2
   ```

   where `<FFF>` is the three-digit forecast hour. A sentinel file `aigfs.done` is created when the run is complete.

The forecast job requires significant memory (default: 150 GB) due to the size of the ***GraphCast*** model.

### Post-Processing

The `metatask_post` ***Rocoto*** metatask fans out into one `task_post_<FFF>` job per forecast lead time. Each post job runs `drivers/post.py` (driver class `AIGFSPost`). It:

1. Waits for the corresponding GRIB2 surface and pressure-level files to exist in the forecast directory (or for `task_forecast` to complete, whichever happens first).
2. Generates a `wgrib2` inventory index (`.idx`) file for each GRIB2 file.
3. Copies the index files to the delivery directory (`post.aigfs_post.deliver_to`; defaults to the forecast run directory).

Output index files are written to:

```
<experiment_dir>/<YYYYMMDDHH>/post_<FFF>/aigfs.t<HH>z.sfc.f<FFF>.grib2.idx
<experiment_dir>/<YYYYMMDDHH>/post_<FFF>/aigfs.t<HH>z.pres.f<FFF>.grib2.idx
```

[← Back to Index](index.md)
