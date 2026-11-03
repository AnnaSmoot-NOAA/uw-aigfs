from datetime import datetime, timedelta

from pytest import mark

from aigfs import ecflow_rt

# deduce_cycles


def test_ecflow_rt_deduce_cycles_newest_first(utc):
    # 07:30 falls between the 06Z and 12Z 6-hourly boundaries, so the newest cycle is 06Z.
    cycles = ecflow_rt.deduce_cycles(utc(2026, 9, 13, 7, 30), timedelta(hours=6), 4)
    assert cycles == [
        utc(2026, 9, 13, 6),
        utc(2026, 9, 13, 0),
        utc(2026, 9, 12, 18),
        utc(2026, 9, 12, 12),
    ]


def test_ecflow_rt_deduce_cycles_on_boundary(utc):
    # Exactly on a boundary, that boundary is the newest cycle.
    cycles = ecflow_rt.deduce_cycles(utc(2026, 9, 13, 12), timedelta(hours=6), 2)
    assert cycles == [utc(2026, 9, 13, 12), utc(2026, 9, 13, 6)]


# gated_cycles


def test_ecflow_rt_gated_cycles_withholds_until_cutoff(utc):
    now = utc(2026, 9, 13, 7, 30)
    cycles = ecflow_rt.deduce_cycles(now, timedelta(hours=6), 4)
    gated = ecflow_rt.gated_cycles(cycles, now)
    # 06Z cutoff is 09:35 (> now) so it is withheld; 00Z cutoff is 03:35 (<= now) so it is included.
    assert utc(2026, 9, 13, 6) not in gated
    assert gated[0] == utc(2026, 9, 13, 0)
    assert len(gated) == 3


def test_ecflow_rt_gated_cycles_custom_offset(utc):
    now = utc(2026, 9, 13, 6, 0)
    cycles = [utc(2026, 9, 13, 0)]
    assert ecflow_rt.gated_cycles(cycles, now, timedelta(hours=3)) == cycles
    assert ecflow_rt.gated_cycles(cycles, now, timedelta(hours=7)) == []


# family_name


@mark.parametrize(
    ("args", "expected"),
    [
        ((2026, 9, 13, 0), "cycle_20260913T000000"),
        ((2026, 9, 13, 6), "cycle_20260913T060000"),
    ],
)
def test_ecflow_rt_family_name(args, expected, utc):
    assert ecflow_rt.family_name(utc(*args)) == expected


def test_ecflow_rt_family_name_naive_treated_as_utc():
    assert ecflow_rt.family_name(datetime(2026, 9, 13, 0)) == "cycle_20260913T000000"  # noqa: DTZ001


# prune_cycle_dirs


def test_ecflow_rt_prune_cycle_dirs_keeps_newest(tmp_path):
    names = ["2026091300", "2026091306", "2026091312", "2026091318", "2026091400"]
    for name in names:
        (tmp_path / name).mkdir()
    (tmp_path / "ecf").mkdir()  # non-cycle dir must be ignored
    (tmp_path / "aigfs.yaml").touch()
    ecflow_rt.prune_cycle_dirs(tmp_path, keep=3)
    remaining = sorted(p.name for p in tmp_path.iterdir() if p.is_dir() and p.name.isdigit())
    assert remaining == ["2026091312", "2026091318", "2026091400"]
    assert (tmp_path / "ecf").is_dir()


def test_ecflow_rt_prune_cycle_dirs_noop_when_under_limit(tmp_path):
    for name in ["2026091300", "2026091306"]:
        (tmp_path / name).mkdir()
    ecflow_rt.prune_cycle_dirs(tmp_path, keep=12)
    remaining = sorted(p.name for p in tmp_path.iterdir() if p.is_dir())
    assert remaining == ["2026091300", "2026091306"]


def test_ecflow_rt_prune_cycle_dirs_missing_rundir(tmp_path):
    ecflow_rt.prune_cycle_dirs(tmp_path / "nope", keep=3)  # must not raise
