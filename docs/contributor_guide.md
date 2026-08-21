# Contributor Guide

[← Back to Index](index.md)

Welcome to the ***uw-aigfs*** Contributor Guide. Please familiarize yourself with and follow the procedures in the sections below before submitting changes.

> **Note:** Before starting work on a new feature, bug fix, or other change, please open an [Issue](https://github.com/NOAA-GSL/uw-aigfs/issues) to propose your change and solicit feedback from other developers. This helps avoid duplicate efforts or wasted work.

## Table of Contents

- [Developer Setup](#developer-setup)
- [Code Quality](#code-quality)
  - [Formatting and Linting](#formatting-and-linting)
  - [Unit Tests](#unit-tests)
- [Fork and PR Model](#fork-and-pr-model)
  - [Overview](#overview)
  - [Specifics for uw-aigfs](#specifics-for-uw-aigfs)
  - [Merging](#merging)
  - [Need Help?](#need-help)
- [Repository Structure](#repository-structure)
- [Deploying Realtime AIGFS on Ursa](#deploying-realtime-aigfs-on-ursa)

---

## Developer Setup

> **Note:** The installation of conda environments is only meant for systems other than WCOSS2.

***uw-aigfs*** installs and manages its own conda installation in the `conda/` subdirectory of the repository root. To set up a development environment, run:

```bash
make devenv
```

This installs [Miniforge](https://github.com/conda-forge/miniforge) into `conda/`, creates the `aigfs` conda environment from `environment.yml`, and then installs additional developer tools (linters, formatters, test runners) listed in `devpkgs`.

After the initial installation, activate the environment in a fresh shell with:

```bash
source bin/activate-<platform>
```

where `<platform>` is `ursa` or `wcoss2` (see the [User Guide](user_guide.md#installing) for details).

> **Note on disk space:** The conda installation requires several gigabytes of disk space. Clone `uw-aigfs` to a location with a sufficiently large disk quota — not your HPC home directory.

---

## Code Quality

Several `make` targets are available in an activated `aigfs` development environment:

| Target | Description |
|---|---|
| `make docs` | Build HTML API docs with [pdoc](https://pdoc.dev/) into `docs/api/` |
| `make format` | Format Python code with [ruff](https://docs.astral.sh/ruff/) |
| `make lint` | Lint Python code with [ruff](https://docs.astral.sh/ruff/) |
| `make test` | Run the linter and unit tests (`lint` + `unittest`) |
| `make unittest` | Run unit tests and report coverage with [pytest](https://docs.pytest.org/) |

Configuration for `ruff` and `pytest` is provided by `pyproject.toml` in the repository root.

A useful development idiom is:

```bash
make format && make test
```

This formats the code, then runs the linter and unit tests. The order is intentional:

- **`format`** catches certain syntax errors that would cause other tools to fail (and could change line numbers in their reports).
- **`lint`** provides a fast first check for obvious errors and anti-patterns.
- **`unittest`** runs higher-level semantic-correctness checks once syntax is clean.

All checks are run by CI against every pull request. Ensure your code is formatted and tests pass locally before opening a PR, and when updating code during the PR process.

### API Documentation

API documentation for the `drivers/` package is generated automatically by [pdoc](https://pdoc.dev/) from the docstrings in the source code. To build it locally (requires the `devenv`):

```bash
make docs
```

Output is written to `docs/api/` (excluded from version control). Open `docs/api/index.html` in a browser to preview the API documentation prior to the PR process.

The docs workflow (`.github/workflows/docs.yaml`) rebuilds and publishes the API docs to GitHub Pages automatically on every push to `main`.

### Formatting and Linting

`ruff` is configured with a line length of 100 characters and a broad rule set (see `pyproject.toml` for the full list of enabled and disabled rules). To check and auto-fix formatting:

```bash
make format
```

To check for lint errors without fixing:

```bash
make lint
```

### Unit Tests

### Unit Tests

Unit tests are colocated with the modules they test. Run them with coverage reporting:

```bash
make unittest
```

Tests are run with [pytest](https://docs.pytest.org/) and coverage is reported via [coverage.py](https://coverage.readthedocs.io/). All pull requests must have passing tests. Repository code must maintain 100% test coverage.

---

## Fork and PR Model

### Overview

Contributions to `uw-aigfs` are made via a [Fork](https://docs.github.com/en/pull-requests/collaborating-with-pull-requests/working-with-forks/about-forks) and [Pull Request (PR)](https://docs.github.com/en/pull-requests/collaborating-with-pull-requests/proposing-changes-to-your-work-with-pull-requests/about-pull-requests) model. The general steps are:

1. [Fork](https://docs.github.com/en/get-started/exploring-projects-on-github/contributing-to-a-project#forking-a-repository) the [uw-aigfs repository](https://github.com/NOAA-GSL/uw-aigfs) into your personal GitHub account.
2. [Clone](https://docs.github.com/en/get-started/exploring-projects-on-github/contributing-to-a-project) your fork onto your development system.
3. [Create an Issue](https://github.com/NOAA-GSL/uw-aigfs/issues/new) to discuss your proposed change before starting work.
4. [Create a branch](https://docs.github.com/en/get-started/exploring-projects-on-github/contributing-to-a-project#creating-a-branch-to-work-on) in your clone for your changes.
5. [Make, commit, and push changes](https://docs.github.com/en/get-started/exploring-projects-on-github/contributing-to-a-project#making-and-pushing-changes) in your clone to your fork. Refer to the [Developer Setup](#developer-setup) section for formatting and testing instructions.
6. [Create a pull request](https://docs.github.com/en/get-started/exploring-projects-on-github/contributing-to-a-project#making-a-pull-request) to merge your changes into the main repository.

For future contributions, either delete and recreate your fork, or configure the official `uw-aigfs` repository as a [remote](https://docs.github.com/en/pull-requests/collaborating-with-pull-requests/working-with-forks/configuring-a-remote-repository-for-a-fork) and [sync upstream changes](https://docs.github.com/en/pull-requests/collaborating-with-pull-requests/working-with-forks/syncing-a-fork) to stay up-to-date.

### Specifics for uw-aigfs

When creating your PR, please follow these guidelines:

- Target base repository `NOAA-GSL/uw-aigfs` and base branch `main`.
- Complete the PR description template. Provide an informative summary of your contribution and mark the appropriate checklist items.
- Initially open your PR as a [draft pull request](https://docs.github.com/en/pull-requests/collaborating-with-pull-requests/proposing-changes-to-your-work-with-pull-requests/about-pull-requests#draft-pull-requests).
- Visit the _Files changed_ tab and add inline comments on lines you think reviewers will benefit from. Proactively answering anticipated questions saves review time.
- Once your draft is marked up, click _Ready for review_ on the _Conversation_ tab.

A default set of reviewers will be added automatically. You may add others if appropriate. Respond to reviewer comments as needed, pushing additional commits to your branch. Your PR will update automatically.

### Merging

Your PR is ready to merge when:

1. It has been approved by a required number of `uw-aigfs` core-developer reviewers.
2. All required CI checks have passed.

These criteria and their current statuses are shown at the bottom of the PR's _Conversation_ tab. CI checks take some time to run — please be patient.

If you have write access to the repository, you may merge your PR yourself once the above conditions are met. Otherwise, a core developer will merge it for you.

### Need Help?

Use the _Conversation_ tab of your PR to ask for help with any difficulties you encounter during the contribution process.

---

## Repository Structure

```
├── bin                            # Automation tools
│   ├── activate-<platform>        # Source to activate AIGFS environment for <platform>
│   ├── post                       # Post-processing script
│   ├── run                        # Support for Makefile targets
│   └── setup                      # Executable wrapper for aigfs.setup module
├── conda                          # Managed conda installation (created by make [dev]env)
├── docs                           # User and contributor documentation
├── etc                            # Configuration files, etc.
│   ├── ansible                    # Ansible deployment assets
│   ├── app                        # AIGFS configuration files
│   ├── env                        # Conda environment definitions
│   │   ├── devpkgs.yaml           # Developer packages
│   │   └── environment.yaml       # Core AIGFS environment definition
│   ├── modulefiles                # System modules
│   ├── platform                   # Per-platform YAML overrides
│   ├── wgrib2.yaml                # Variable, and levels to extract from GFS GRIB2
│   └── workflow                   # Workflow files
│       ├── ecflow                 # ecFlow workflow support
│       └── rocoto                 # Rocoto workflow support
├── lib                            # Python library code
│   └── aigfs                      # The AIGFS python package
│       ├── conftest.py            # Unit-tests fixtures
│       ├── drivers                # AIGFS component drivers
│       │   ├── *.jsonschema       # Config schema
│       │   ├── *.py               # AIGFS component driver
│       │   ├── *_test.py          # Unit tests
│       │   └── utils              # Shared driver utilities
│       │       ├── grib2writer.py # GRIB2 writing support
│       │       └── tasks.py       # Shared driver tasks
│       ├── setup.py               # Logic for preparing AIGFS assets
│       └── validation.py          # Config validation
├── Makefile                       # Provides automation targets
├── pyproject.toml                 # Code-quality tool configuration
└── README.md                      # Top-level documentation
```

### Key Concepts

**Drivers** (`drivers/`) implement [uwtools](https://uwtools.readthedocs.io/en/main/) driver classes using the [iotaa](https://github.com/maddenp/iotaa) task framework. Each driver exposes tasks (Python methods decorated with `@task`, `@collection`, or `@external`) that declare their inputs and outputs as `Asset` objects. The `uw execute` command (called from ***Rocoto*** job scripts) resolves and runs these tasks.

**Configuration** follows the ***uwtools*** YAML model. `etc/base.yaml` is the baseline; it is merged with the platform YAML and any user-provided YAMLs by `bin/setup` using `uwtools.api.config.compose`. The resulting `aigfs.yaml` is the single source of truth at runtime.

**Workflow** is managed by [Rocoto](https://github.com/NOAA-GSL/rocoto). The `etc/workflow/rocoto/base.yaml` template is realized by ***uwtools*** to produce `rocoto.xml`. Task dependencies (prep → forecast → post) are expressed in that template.

When adding a new workflow stage, you will typically need to:

1. Add a new driver class in `lib/aigfs/drivers/`.
2. Add corresponding configuration blocks in `etc/base.yaml`.
3. Add a new task or metatask entry in `etc/workflow/rocoto/base.yaml`.
4. Add unit tests alongside the modules they test.
5. Update this documentation.

## Deploying Realtime AIGFS on Ursa

As user `role.rtaigfs`, `cd` to the appropriate scratch workspace, then:

```
$ git clone https://github.com/NOAA-GSL/uw-aigfs.git rtaigfs
$ cd rtaigfs/
$ make env
$ make deploy playbook=rtaigfs-ursa
```

If these commands complete successfully, an `rtaigfs/` subdirectory should have been created and populated with assets necessary for execution of realtime AIGFS runs:

```
rtaigfs/
├── bin              # Executables
├── model            # AIGFS model files
├── rtaigfs          # Root of yyyymmdd/hh cycle run directories
├── rtaigfs.log      # Log file from latest run
├── rtaigfs.log.last # Log file from previous run (created after first run)
└── rtaigfs.yaml     # Parameterized configuration
```

Additionally, `crontab -l` should show entries for running AIGFS and for emailing a daily production report.

After deployment, *no manual changes* should be made to the contents of the git clone or any of its subdirectories or files. All updates should be performed via the following recipe:

1. Update the `uw-aigfs` git repo via PR.
2. Unload the `role.rtaigfs` crontab: `crontab -r`.
3. Update the git clone on Ursa: `git pull`.
4. If the conda installation must be updated: `rm -rf conda && make env`.
5. Update the deployment: `make deploy playbook=rtaigfs-ursa`.

The structure of a `yyyymmdd/hh` cycle run directory is as follows:

```
├── yyyymmddhh       # Cycle run root directory
│   ├── forecast     # Run directory for forecast task
│   ├── post_*       # Run directory for post task (one per leadtime)
│   └── prep         # Run directory for prep step
├── aigfs.yaml       # Fully realized AIGFS config 
├── logs             # Rocoto logs
│   ├── <task>.log   # Task log (one per task execution)
│   └── workflow.log # Rocoto general log
├── rocoto.db        # Rocoto sqlite3 database
├── rocoto_lock.db   # Rocoto database lockfile
└── rocoto.xml       # Rocoto workflow document
```

Per-task run directories have structure and content specific to each task, but since each task is executed via a `uwtools` driver, several common files can be expected:

```
├── runscript.<driver>      # Executable driver runscript
├── runscript.<driver>.done # A sentinel file created if driver executed successfully
└── runscript.<driver>.out  # Driver execution output
```

Values for `<driver>` are `aigfs_ics`, `aigfs_inference`, and `aigfs_post`.

[← Back to Index](index.md)
