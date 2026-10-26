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

### 3b. Run and monitor with `uw rocoto iterate`

Use `uwtools` to drive the workflow: `uw rocoto iterate` repeatedly runs
`rocotorun` until the requested task (and everything it depends on) reaches a
terminal state, printing `rocotostat` output on each pass. This replaces
hand-rolled `while ...; rocotorun; sleep ...; done` loops.

Both `uw` (from the AIGFS env) and `rocotorun`/`rocotostat` (from the system
module) must be on `PATH`, so activate the env **and** load the module:

```bash
module load rocoto
cd /scratch3/NCEPDEV/global/Anna.Smoot/uw-aigfs/demo-rocoto
```

Iterating the final post task drives the whole `prep -> forecast -> post` chain,
because iterate resolves dependencies automatically (`post_024` depends on
`forecast`, which depends on `prep`):

```bash
uw rocoto iterate \
  --cycle 2026-09-13T00 \
  --workflow rocoto.xml \
  --database rocoto.db \
  --task post_024 \
  --rate 60
```

`rocoto.db` is created on the first pass. The command returns once `post_024`
succeeds. To populate the remaining leadtimes (prep and forecast are already
done, so these finish quickly):

```bash
for f in 000 006 012 018; do
  uw rocoto iterate --cycle 2026-09-13T00 -w rocoto.xml -d rocoto.db --task post_$f --rate 30
done
```

Check overall status at any time:

```bash
rocotostat -w rocoto.xml -d rocoto.db
```

Per-task logs land in `<rundir>/logs/`; the overall workflow log is
`<rundir>/logs/workflow.log`.

> Lower-level alternative: run `rocotorun -w rocoto.xml -d rocoto.db` yourself
> every minute or two and watch `rocotostat`; `uw rocoto iterate` simply automates
> that loop. See the
> [uwtools Rocoto tool docs](https://uwtools.readthedocs.io/en/2.20.0/sections/user_guide/cli/tools/rocoto.html).

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

### 4c. Load and begin the suite

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
```

### 4d. Monitor with the ecFlow UI (`ecflow_ui`)

The ecFlow UI is the recommended way to watch and drive the suite. It shows the
suite tree with live task colors (queued / submitted / active / complete /
aborted), per-task output and logs, and manual controls.

1. Connect to `uecflow01` with X forwarding enabled (`ssh -Y uecflow01`, or use
   FastX / VNC), activate the env, and launch the UI:

   ```bash
   source $CLONE/bin/activate-ursa
   ecflow_ui &
   ```

2. Register the demo server (**Servers > Manage Servers... > Add**) using the
   values from `server.json`:

   | Field    | Value                                   |
   |----------|-----------------------------------------|
   | Name     | any label, e.g. `aigfs-demo`            |
   | Host     | value of `ECF_HOST` (e.g. `uecflow01`)  |
   | Port     | value of `ECF_PORT`                     |
   | Protocol | **TCP/IP with SSL** (since `ECF_SSL=1`) |

3. Expand the `retro` suite and watch tasks advance
   `prep -> forecast -> post_fXXX`. Right-click a task for **Info**, **Output**,
   **Manual**, and control actions (requeue, execute, suspend, etc.).

Prefer the terminal? You can still poll the state directly:

```bash
ecflow_client --get_state=/retro
```

### 4e. Shut down

Halt the suite and terminate the server from a client shell (or press **Ctrl-C**
in the shell running `uw ecflow server`):

```bash
ecflow_client --halt=yes
ecflow_client --terminate=yes
```

See [§6 Tear down](#6-tear-down-clean-slate-before-the-next-run) for full cleanup
that also removes run directories.

---

## 5. Expected output

Each demo produces a per-cycle directory under its run directory. The ecFlow
layout (verified by the run below) looks like:

```
<rundir>/
|-- aigfs.yaml
|-- suite.def            # ecFlow demo (rocoto.xml for the Rocoto demo)
|-- server.json          # ecFlow demo (written by `uw ecflow server`)
|-- ecf/                 # ecFlow demo: generated .ecf scripts, job output, server log
`-- 2026091300/
    |-- prep/            # aigfs.t00z.ic.nc (+ staged GFS GRIB under data/)
    |-- forecast/        # aigfs.t00z.{sfc,pres}.f{000,006,012,018,024}.grib2(.idx)
    |-- post_000/        # aigfs.t00z.{sfc,pres}.f000.grib2.idx
    |-- post_006/
    |-- post_012/
    |-- post_018/
    `-- post_024/
```

The Rocoto demo instead writes `rocoto.xml` (+ `rocoto.db` after the first
`uw rocoto iterate` / `rocotorun`) and per-task logs under `<rundir>/logs/`.

### Confirming success

This branch does not write `.done` sentinel files; completion is signaled by the
workflow engine plus the presence of the output files.

**ecFlow** -- the whole suite reports `complete` (no `aborted`/`queued` nodes):

```bash
ecflow_client --get_state=/retro | grep -E 'suite|task' 
# e.g. "suite retro ... state:complete", every task "state:complete"
```

**Rocoto** -- every task shows `SUCCEEDED`:

```bash
rocotostat -w rocoto.xml -d rocoto.db
```

**Output files** -- a successful cycle produces, in `<cycle>/forecast/`, the
GRIB2 forecast fields for each leadtime, with `.idx` files written by the post
stage:

```bash
ls <rundir>/2026091300/forecast/aigfs.t00z.*.f*.grib2*
```

You should see `sfc` and `pres` files for f000, f006, f012, f018, and f024, each
with a matching `.idx`.

---

## 6. Tear down (clean slate before the next run)

**This matters.** The AIGFS drivers treat a stage as already finished when its
output files exist -- `iotaa` checks `path.is_file()` for the ICs netCDF, the
forecast GRIB2 files, and the post `.idx` files. Rocoto separately records task
state in `rocoto.db`. So if you re-run a demo on top of a previous run directory,
stages are **silently skipped** and the workflow appears to "succeed" instantly,
hiding real errors. Always start each demo from an empty run directory.

### ecFlow

1. In a client shell with `ECF_*` exported, halt and terminate the server (or
   press **Ctrl-C** in the shell running `uw ecflow server`):

   ```bash
   ecflow_client --halt=yes
   ecflow_client --terminate=yes
   ```

2. Confirm no ecFlow server is left running on `uecflow01` -- a leftover server
   keeps its port and an old loaded suite:

   ```bash
   ssh uecflow01 'pgrep -a -u $USER ecflow_server || echo "no ecflow_server running"'
   ```

   Stop any straggler by PID: `ssh uecflow01 'kill <PID>'`.

3. Remove the run directory:

   ```bash
   rm -rf $CLONE/demo-ecflow
   ```

### Rocoto

Rocoto has no long-running server, so just remove the run directory (this also
deletes `rocoto.db`, which otherwise remembers task states):

```bash
rm -rf $CLONE/demo-rocoto
```

### Everything at once

```bash
rm -rf $CLONE/demo-ecflow $CLONE/demo-rocoto
ssh uecflow01 'pgrep -a -u $USER ecflow_server || echo "no ecflow_server running"'
```

After teardown, re-running `setup` (steps 3 / 4a) regenerates a fresh run
directory so every stage executes for real.
