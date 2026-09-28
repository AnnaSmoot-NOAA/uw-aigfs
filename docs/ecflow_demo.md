# uw-aigfs ecFlow Demo (Ursa)

Author: Anna Smoot
Purpose: demonstrate the `uw-aigfs` workflow orchestrated by **ecFlow** — as a
precursor to the Rocoto-based realtime AIGFS runs in
`/scratch4/BMC/gsd-fv3-dev/role.rtaigfs/rtaigfs/app/cycles`.

> **Working clone (world-readable, on Ursa):**
> `/scratch3/NCEPDEV/global/Anna.Smoot/uw-aigfs`
>
> **Working run directories from the demos below:**
> - Single-cycle: `/scratch3/NCEPDEV/global/Anna.Smoot/uw-aigfs/demo-single`
> - Multi-cycle (4 cycles):  `/scratch3/NCEPDEV/global/Anna.Smoot/uw-aigfs/demo-multi`
> - Reference (already completed): `/scratch3/NCEPDEV/global/Anna.Smoot/uw-aigfs/demo`

---

## 1. What the demo does

Per `docs/user_guide.md`, one AIGFS cycle runs three stages via `uwtools`
drivers on Ursa's Slurm partitions:

| Stage    | Slurm partition | Purpose                                              |
|----------|-----------------|------------------------------------------------------|
| prep     | `u1-service`    | Pull GFS 0.25° GRIB2, extract vars, write netCDF ICs |
| forecast | `u1-compute`    | Run GraphCast inference (weights in `app.modeldir`)  |
| post     | `u1-service`    | Write GRIB2 `.idx` files and deliver                 |

ecFlow expresses the same DAG the Rocoto realtime workflow does
(`prep → forecast → post_fXXX`) using a suite defined in `suite.def` with
one family per cycle — see `etc/workflow/ecflow.yaml`.

Reference: [User Guide § Run with ecFlow](user_guide.md#run-with-ecflow).

---

## 2. Prerequisites (one-time)

Log in to **Ursa**, then:

```bash
# Clone (or point at Anna's clone; everything below assumes CLONE=<clone dir>)
git clone https://github.com/NOAA-GSL/uw-aigfs.git
cd uw-aigfs
export CLONE=$PWD

# Install the local conda env (a few GB; do NOT run in $HOME)
make env
```

Once installed, source the environment in every new shell you use for the
demo:

```bash
source $CLONE/bin/activate-ursa
```

The Ursa platform config used here is `etc/platform/ursa.yaml`:

- `app.modeldir: /scratch3/BMC/gsd-fv3/aigfs_input/aigfs-v1.1/model` (GraphCast weights + stats)
- `user.gfs_data:` NOAA public S3 bucket (`https://noaa-gfs-bdp-pds.s3.amazonaws.com`)
- Partitions: `compute=u1-compute`, `task/netaccess=u1-service`

No other data staging is required.

---

## 3. User configs used in this demo

Both are already checked out into the clone root and pre-populated with a
cycle range known to have GFS data available. Copy them and adjust
`rundir:` and `account:` for your own runs.

### Single cycle — `user.single.yaml`

```yaml
app:
  cycle_freq: !timedelta 6
  first_cycle: !datetime 2026-09-13T00:00:00
  last_cycle: !datetime 2026-09-13T00:00:00
  platform:
    scheduler:
      account: fv3-cpu
  rundir: /scratch3/NCEPDEV/global/Anna.Smoot/uw-aigfs/demo-single
```

### Multi-cycle (4 cycles, 6 h apart) — `user.multi.yaml`

```yaml
app:
  cycle_freq: !timedelta 6
  first_cycle: !datetime 2026-09-13T00:00:00
  last_cycle: !datetime 2026-09-13T18:00:00
  platform:
    scheduler:
      account: fv3-cpu
  rundir: /scratch3/NCEPDEV/global/Anna.Smoot/uw-aigfs/demo-multi
```

---

## 4. Run the single-cycle demo

All commands below assume you are on Ursa with the env activated.

### 4a. Generate `aigfs.yaml`, `suite.def`, and `ecf/`

```bash
cd $CLONE
setup --platform ursa --workflow ecflow user.single.yaml
```

This composes `etc/base.yaml` + `etc/workflow/ecflow.yaml` +
`etc/platform/ursa.yaml` + your user config and writes:

```
$rundir/aigfs.yaml     # fully realized config
$rundir/suite.def      # ecFlow suite definition
$rundir/ecf/           # generated .ecf task scripts
```

### 4b. Start the ecFlow server on `uecflow01`

The ecFlow server must run on Ursa's dedicated ecFlow node, **not** a
front end (`ufeNN`).

```bash
ssh uecflow01
source $CLONE/bin/activate-ursa
cd /scratch3/NCEPDEV/global/Anna.Smoot/uw-aigfs/demo-single     # your rundir
uw ecflow server --config-file aigfs.yaml --report >server.json
```

Leave that shell attached — the server writes stderr there. The
`server.json` file records the `ECF_HOST`/`ECF_PORT`/`ECF_SSL`/`ECF_HOME`
the client shell needs.

### 4c. Load, begin, monitor

Open a **second** shell (still on `uecflow01`; can ssh in fresh):

```bash
source $CLONE/bin/activate-ursa
cd /scratch3/NCEPDEV/global/Anna.Smoot/uw-aigfs/demo-single

# Export ECF_* from server.json into this shell.
eval "$(jq -r 'to_entries | .[] | "export \(.key)=\(.value)"' server.json)"

# Sanity check the exports.
env | sort | grep ^ECF_

# Move server from halted -> running, load and start the suite.
ecflow_client --restart
ecflow_client --load=suite.def
ecflow_client --begin=retro

# Watch progress.
ecflow_client --get_state=/retro
```

Task logs land in each cycle's per-task directory (e.g.
`2026091300/prep/`, `.../forecast/`, `.../post_000/`). Success sentinels:

| File                                | Meaning                     |
|-------------------------------------|-----------------------------|
| `<cycle>/prep/runscript.aigfs_ics.done` | prep stage completed        |
| `<cycle>/forecast/aigfs.done`       | forecast stage completed    |
| `<cycle>/post_fff/runscript.aigfs_post.done` | post stage for leadtime fff |

Forecast GRIB2 output lives in `<cycle>/forecast/`:
`aigfs.t<HH>z.{sfc,pres}.f<fff>.grib2` (+ `.idx` copied to same dir by post).

### 4d. Optional: ecFlow GUI (`ecflow_ui`)

From a shell on `uecflow01` with X forwarding enabled and the env
activated:

```bash
ecflow_ui
```

Then add a server using the values in `server.json`:

- Host: value of `ECF_HOST`
- Port: value of `ECF_PORT`
- Protocol: **TCP/IP with SSL** (since `ECF_SSL=1`)

### 4e. Shut down when done

In the client shell, halt/exit the suite as desired. To stop the server,
return to the shell running `uw ecflow server` and press **Ctrl-C**.

---

## 5. Run the multi-cycle demo

Identical to §4 except:

- Use `user.multi.yaml` (4 cycles: 2026-09-13T00, 06, 12, 18).
- Use a distinct `rundir` (already set to `.../demo-multi`).

```bash
cd $CLONE
setup --platform ursa --workflow ecflow user.multi.yaml
# then repeat §4b–§4e in that rundir
```

The ecFlow suite generated for a range of cycles uses a `repeat_datetime`
family (see `etc/workflow/ecflow.yaml`), so ecFlow marches the family
through each cycle in turn — no additional configuration is needed for
multi-cycle vs single-cycle runs.

### Re-loading a modified suite on the same running server

If you re-run `setup` (e.g. to change cycles), swap the loaded suite
without restarting the server:

```bash
ecflow_client --halt=yes
ecflow_client --delete=force /retro
ecflow_client --restart
ecflow_client --load=suite.def
ecflow_client --begin=retro
```

---

## 6. Reference: completed demo output (2 cycles)

An already-executed 2-cycle run is preserved at

`/scratch3/NCEPDEV/global/Anna.Smoot/uw-aigfs/demo`

with the layout below — useful for inspecting what a successful run
produces without re-executing anything:

```
demo/
├── aigfs.yaml
├── suite.def
├── server.json
├── ecf/
│   ├── retro/...            # ecFlow-generated .ecf scripts per cycle
│   ├── uecflow01.<PORT>.ecf.log
│   └── uecflow01.<PORT>.ecf.check
├── 2026091300/
│   ├── prep/                # ICs netCDF + wgrib2 staging
│   ├── forecast/            # aigfs.done + aigfs.t00z.{sfc,pres}.f{000,006}.grib2(.idx)
│   ├── post_000/
│   └── post_006/
└── 2026091306/
    └── (same layout)
```

The `demo/forecast/aigfs.done` and `post_fff/*.done` sentinels confirm
success end-to-end.

---

## 7. Relationship to the Rocoto realtime workflow

The Rocoto realtime runs deploy the same three drivers
(`aigfs.drivers.ics`, `aigfs.drivers.inference`, `aigfs.drivers.post`)
under `role.rtaigfs`:

```
/scratch4/BMC/gsd-fv3-dev/role.rtaigfs/rtaigfs/app/cycles
├── 20260923/
├── 20260924/
└── 20260925/
```

Each subdirectory there has the same per-cycle layout as this ecFlow
demo — the only difference is the workflow engine (Rocoto XML +
`rocoto.db` vs ecFlow `suite.def` + `.ecf` scripts). The drivers, GRIB2
outputs, and `.done` sentinels are identical. See the
[Contributor Guide § Deploying Realtime AIGFS on Ursa](contributor_guide.md#deploying-realtime-aigfs-on-ursa)
for the production deploy procedure.

---

## 8. Access to `/scratch4/BMC/gsd-fv3-dev/role.rtaigfs/rtaigfs/app/cycles`

Verified 2026-09-25:

```
drwxr-xr-x 5 role.rtaigfs gsd-fv3     .../app/cycles
drwxr-xr-x 5 role.rtaigfs gsd-fv3-dev .../app
drwxr-sr-x ... role.rtaigfs gsd-fv3-dev .../rtaigfs
```

`Anna.Smoot` groups: `rstprod sfs-cpu climate da stmp nems global naqfc fv3-cpu`

- **Read access:** ✅ world `r-x` is set on every ancestor and on
  `cycles/` itself, so I can list and read all cycle output.
- **Write access:** ❌ I am not the owner (`role.rtaigfs`) and not in
  `gsd-fv3` / `gsd-fv3-dev`, and mode is `0755` (no group write anyway).

### To obtain write access

Any one of the following will work; the first two are the standard
routes:

1. **Add my account to the required groups** — file an RDHPCS help
   ticket asking to add `Anna.Smoot` to both `gsd-fv3` and
   `gsd-fv3-dev`. Even after group membership is granted, the mode on
   `cycles/` (`0755`) blocks group write, so also request that the
   directory be re-modeed to `2775` (setgid + group write) so future
   sub-directories inherit `gsd-fv3` ownership.
2. **Grant a per-user ACL** — have someone with write on the tree
   (typically `role.rtaigfs` or an admin) run, e.g.:

   ```bash
   setfacl -R -m u:Anna.Smoot:rwX /scratch4/BMC/gsd-fv3-dev/role.rtaigfs/rtaigfs/app/cycles
   setfacl -R -d -m u:Anna.Smoot:rwX /scratch4/BMC/gsd-fv3-dev/role.rtaigfs/rtaigfs/app/cycles
   ```

   (The second command sets a default ACL so new cycle dirs also inherit
   the permission.)
3. **Run the realtime workflow under my own account** in a scratch
   directory I own, mirroring the `app/cycles` layout — appropriate for
   development but not for producing artifacts under the shared
   `role.rtaigfs` tree.

Until one of the above is in place, treat `cycles/` as read-only.
