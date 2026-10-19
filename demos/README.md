# uw-aigfs Single-Cycle Demos (Rocoto and ecFlow)

Two minimal, single-cycle demonstrations of the `uw-aigfs` workflow on **Ursa**,
one driven by **Rocoto** and one by **ecFlow**. Both run the exact same three
AIGFS stages (`prep -> forecast -> post`) for a single cycle; they differ only in
the workflow engine.

| Demo   | User config               | Run directory  | `setup --workflow` |
|--------|---------------------------|----------------|--------------------|
| Rocoto | [`user.rocoto.yaml`](user.rocoto.yaml) | `.../demo-rocoto` | `rocoto` |
| ecFlow | [`user.ecflow.yaml`](user.ecflow.yaml) | `.../demo-ecflow` | `ecflow` |

Both configs forecast a single cycle (`first_cycle == last_cycle`,
`2026-09-13T00:00:00`) known to have GFS data available. Copy a config and adjust
`rundir:`, `account:`, and the cycle datetimes for your own runs.

See the [User Guide](../docs/user_guide.md) for full reference material.

---

## 1. What each demo does

One AIGFS cycle runs three stages via `uwtools` drivers on Ursa's Slurm
partitions:

| Stage    | Driver                     | Slurm partition | Purpose                                              |
|----------|----------------------------|-----------------|------------------------------------------------------|
| prep     | `aigfs.drivers.ics`        | `u1-service`    | Pull GFS 0.25 deg GRIB2, extract vars, write netCDF ICs |
| forecast | `aigfs.drivers.inference`  | `u1-compute`    | Run GraphCast inference (weights in `app.modeldir`)  |
| post     | `aigfs.drivers.post`       | `u1-service`    | Write GRIB2 `.idx` files and deliver                 |

Both Rocoto and ecFlow express the same DAG (`prep -> forecast -> post_fXXX`); the
only difference is the orchestration engine.

---

## 2. One-time prerequisites

Log in to **Ursa**, then clone and install the local conda environment:

```bash
git clone https://github.com/NOAA-GSL/uw-aigfs.git
cd uw-aigfs
export CLONE=$PWD

# Install the local conda env (a few GB; do NOT run in $HOME).
make env
```

Source the environment in every new shell you use for a demo:

```bash
source $CLONE/bin/activate-ursa
```

The Ursa platform config ([`etc/platform/ursa.yaml`](../etc/platform/ursa.yaml))
supplies everything else:

- `app.modeldir: /scratch3/BMC/gsd-fv3/aigfs_input/aigfs-v1.1/model` (GraphCast weights + stats)
- `user.gfs_data:` NOAA public S3 bucket (`https://noaa-gfs-bdp-pds.s3.amazonaws.com`)
- Partitions: `compute=u1-compute`, `task/netaccess=u1-service`

No other data staging is required.

---

## 3. Rocoto demo (single cycle)

### 3a. Generate `aigfs.yaml` and `rocoto.xml`

```bash
cd $CLONE
setup --platform ursa --workflow rocoto demos/user.rocoto.yaml
```

This composes `etc/base.yaml` + `etc/workflow/rocoto.yaml` +
`etc/platform/ursa.yaml` + your user config and writes to the run directory:

| File         | Contents                     |
|--------------|------------------------------|
| `aigfs.yaml` | Fully realized configuration |
| `rocoto.xml` | Rocoto workflow definition   |

### 3b. Run and monitor

On RDHPCS platforms, Rocoto is available as a system module:

```bash
module load rocoto
cd /scratch3/NCEPDEV/global/Anna.Smoot/uw-aigfs/demo-rocoto
```

Advance the workflow (re-run periodically as jobs complete; `rocoto.db` is created
on the first run):

```bash
rocotorun -w rocoto.xml -d rocoto.db
```

Check task status:

```bash
rocotostat -w rocoto.xml -d rocoto.db
```

Per-task logs land in `<rundir>/logs/`; the overall workflow log is
`<rundir>/logs/workflow.log`.

> Tip: `uw rocoto iterate` can drive the whole workflow for you. See the
> [uwtools Rocoto tool docs](https://uwtools.readthedocs.io/en/2.21.0/sections/user_guide/cli/tools/rocoto.html#cli-rocoto-iterate-examples).

---

## 4. ecFlow demo (single cycle)

### 4a. Generate `aigfs.yaml`, `suite.def`, and `ecf/`

```bash
cd $CLONE
setup --platform ursa --workflow ecflow demos/user.ecflow.yaml
```

This writes to the run directory:

| File / Directory | Contents                                   |
|------------------|--------------------------------------------|
| `aigfs.yaml`     | Fully realized configuration               |
| `suite.def`      | ecFlow suite definition                    |
| `ecf/`           | Generated `.ecf` task scripts for all tasks |

### 4b. Start the ecFlow server on `uecflow01`

The ecFlow server must run on Ursa's dedicated ecFlow node, **not** a front end
(`ufeNN`).

```bash
ssh uecflow01
source $CLONE/bin/activate-ursa
cd /scratch3/NCEPDEV/global/Anna.Smoot/uw-aigfs/demo-ecflow
uw ecflow server --config-file aigfs.yaml --report >server.json
```

Leave that shell attached -- the server writes stderr there. `server.json`
records the `ECF_HOST`/`ECF_PORT`/`ECF_SSL`/`ECF_HOME` the client shell needs.

### 4c. Load, begin, and monitor

Open a **second** shell (still on `uecflow01`):

```bash
source $CLONE/bin/activate-ursa
cd /scratch3/NCEPDEV/global/Anna.Smoot/uw-aigfs/demo-ecflow

# Export ECF_* from server.json into this shell.
eval "$(jq -r 'to_entries | .[] | "export \(.key)=\(.value)"' server.json)"

# Optional: confirm the exports.
env | sort | grep ^ECF_

# Move server halted -> running, load and start the suite.
ecflow_client --restart
ecflow_client --load=suite.def
ecflow_client --begin=retro

# Watch progress.
ecflow_client --get_state=/retro
```

For human-friendly monitoring, launch the ecFlow GUI (`ecflow_ui`) with X
forwarding and add a server using the values in `server.json` (Protocol
**TCP/IP with SSL** when `ECF_SSL=1`).

### 4d. Shut down

In the client shell, halt/delete the suite as desired. To stop the server, return
to the shell running `uw ecflow server` and press **Ctrl-C**.

---

## 5. Expected output (both demos)

Each demo produces the same per-cycle layout under its run directory:

```
<rundir>/
|-- aigfs.yaml
|-- rocoto.xml            # Rocoto demo only
|-- suite.def            # ecFlow demo only
|-- ecf/                 # ecFlow demo only
|-- logs/                # task + workflow logs
`-- 2026091300/
    |-- prep/            # ICs netCDF + wgrib2 staging
    |-- forecast/        # aigfs.done + aigfs.t00z.{sfc,pres}.f{000..024}.grib2(.idx)
    |-- post_000/
    |-- post_006/
    |-- post_012/
    |-- post_018/
    `-- post_024/
```

Success sentinels:

| File                                          | Meaning                     |
|-----------------------------------------------|-----------------------------|
| `<cycle>/prep/runscript.aigfs_ics.done`       | prep stage completed        |
| `<cycle>/forecast/aigfs.done`                 | forecast stage completed    |
| `<cycle>/post_fff/runscript.aigfs_post.done`  | post stage for leadtime fff |

Forecast GRIB2 output lives in `<cycle>/forecast/`:
`aigfs.t<HH>z.{sfc,pres}.f<fff>.grib2` (`.idx` copied there by post).
