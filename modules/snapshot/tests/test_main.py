"""Self-check with a fake kubectl on PATH: the module's four exec calls, the block filter, the gzip."""
import datetime
import os
import stat
import sys
import tarfile
import tempfile
from types import SimpleNamespace as NS

# two blocks on the fake pod: OLD is 1970, NEW spans 2001..2096 - only NEW overlaps any window we test
FAKE = r'''#!/bin/sh
echo "$@" >> "$FAKE_LOG"
case "$*" in
  *wget*)  echo '{"status":"success","data":{"name":"20260907T100000Z-abc"}}' ;;
  *"sh -c"*) printf '01OLD\t{"minTime":0,"maxTime":1000}\n01NEW\t{"minTime":1000000000000,"maxTime":4000000000000}\n' ;;
  *"tar -C"*) d=$(mktemp -d); n=20260907T100000Z-abc; mkdir -p "$d/$n/01OLD" "$d/$n/01NEW"
    echo old > "$d/$n/01OLD/chunks"; echo new > "$d/$n/01NEW/chunks"
    members=""; take=0; for a in "$@"; do [ "$take" = 1 ] && members="$members $a"; [ "$a" = "-" ] && take=1; done
    tar -C "$d" -cf - $members ;;
  *"rm -rf"*) : ;;
esac
'''


def main() -> int:
    work = tempfile.mkdtemp()
    fake_dir = os.path.join(work, "bin"); os.makedirs(fake_dir)
    fake = os.path.join(fake_dir, "kubectl")
    open(fake, "w").write(FAKE); os.chmod(fake, stat.S_IRWXU)
    os.environ["PATH"] = fake_dir + os.pathsep + os.environ["PATH"]
    log_path = os.environ["FAKE_LOG"] = os.path.join(work, "calls.log")
    calls = lambda: open(log_path).read()
    os.chdir(work)   # locations are relative, like report.location

    from modules.snapshot.main import SnapshotSmaModule, SnapshotConfig

    for bad in ({"on": "campaign"}, {"nope": 1}, {"location": "/abs"}, {"location": "../up"}):
        try:
            SnapshotConfig.from_dict(bad); raise AssertionError(bad)
        except ValueError:
            pass
    print("ok  config refuses unknown keys, on= values and absolute/.. locations")

    session = NS(name="verify/repobase/round0", to_dict=lambda kw: {"session": "verify/repobase/round0", "campaign_id": "verify"})
    run = NS(startTime=datetime.datetime(2026, 9, 7, 10, 0, 0), endTime=datetime.datetime(2026, 9, 7, 10, 3, 0), runHash="abcd1234")
    report = NS(location="run_1", metadata=NS(session=session, run=run,
                                              to_dict=lambda kw: {**session.to_dict({}), "startTime": "2026_09_07_10_00_00", "runHash": "abcd1234"}))

    mod = SnapshotSmaModule({"on": "session", "location": "tsdb", "kube_context": "kind-x"})
    mod.onSessionStart()
    mod.onReport(report)                       # on: session -> nothing yet
    assert not os.path.exists("tsdb")
    mod.onSessionEnd()
    files = os.listdir("tsdb")
    assert len(files) == 1 and files[0].startswith("prometheus-snapshot-session-verify_repobase_round0-") and files[0].endswith(".tar.gz"), files
    with tarfile.open(os.path.join("tsdb", files[0]), "r:gz") as tf:
        names = tf.getnames()
    assert "20260907T100000Z-abc/01NEW/chunks" in names and not any("01OLD" in n for n in names), names
    assert calls().count("--context kind-x -n monitoring exec prometheus-kube-prometheus-stack-prometheus-0 -c prometheus --") == 4, calls()
    assert "tar -C /prometheus/snapshots -cf - 20260907T100000Z-abc/01NEW\n" in calls(), calls()
    assert "rm -rf /prometheus/snapshots/20260907T100000Z-abc" in calls(), calls()
    print("ok  on: session -> one tarball named by session at onSessionEnd, only the overlapping block; snapshot removed from the pod")

    os.makedirs(report.location)
    mod2 = SnapshotSmaModule({"on": "run"})
    mod2.onReport(report)
    assert os.path.isfile(os.path.join(report.location, "prometheus-snapshot-run-2026_09_07_10_00_00_abcd1234.tar.gz"))
    mod2.onSessionEnd()
    assert len(os.listdir("tsdb")) == 1, "on: run must not also snapshot at session end"
    print("ok  on: run -> one tarball named by run inside the report dir")

    mod3 = SnapshotSmaModule({"on": "run", "location": "tsdb/${campaign_id}", "filename": "${session}_${runHash}.tgz"})
    mod3.onReport(report)
    assert os.path.isfile("tsdb/verify/verify_repobase_round0_abcd1234.tgz"), os.listdir("tsdb")
    print("ok  location/filename templates take the report context; filename values are sanitised")

    evil = SnapshotSmaModule({"on": "run", "location": "tsdb/${campaign_id}"})
    try:
        evil._path({"campaign_id": "../../escape"}, "tsdb/${campaign_id}"); raise AssertionError("traversal via substitution")
    except ValueError:
        pass
    print("ok  a substituted value cannot escape the report tree")

    far = SnapshotSmaModule({"on": "run", "margin_s": 0})
    report_1970 = NS(location="run_1", metadata=NS(session=session, to_dict=report.metadata.to_dict,
                     run=NS(startTime=datetime.datetime(1971, 1, 1), endTime=datetime.datetime(1971, 1, 2), runHash="x")))
    n_rm = calls().count("rm -rf")
    try:
        far.onReport(report_1970); raise AssertionError("no overlapping block must raise")
    except RuntimeError as exc:
        assert "none of 2 blocks" in str(exc), exc
    assert calls().count("rm -rf") == n_rm + 1, "snapshot must be removed from the pod even when nothing is kept"
    print("ok  a window no block covers raises instead of writing an empty tarball")

    off = SnapshotSmaModule({"enabled": False})
    n = calls().count("wget")
    off.onReport(report); off.onSessionEnd()
    assert calls().count("wget") == n, "disabled must not call kubectl"
    print("ok  enabled: false is a no-op")
    print("PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
