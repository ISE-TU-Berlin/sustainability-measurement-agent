"""Snapshot SMA module: dump the Prometheus TSDB blocks that cover a session (or a
run), gzipped. A snapshot preserves Prometheus' state for later use even if the SMA
config did not specify a metric to be collected or Prometheus is no longer running.

    modules:
      snapshot:
        module: snapshot
        config:
          enabled: true
          on: session            # session (default, one dump per session) | run (one per report)
          # location and filename are string.Template's over the same context as
          # report.location: ${session} and the session extras, and for on: run also
          # ${startTime} ${endTime} ${runHash} ${status} ...; ${time} is the UTC time
          # the snapshot was taken. location must be relative, like report.location.
          location: reports/tsdb # on: run defaults to the report's own directory
          filename: prometheus-snapshot-session-${session}-${time}.tar.gz   # default for on: session
          # filename: prometheus-snapshot-run-${startTime}_${runHash}.tar.gz  # default for on: run
          margin_s: 300          # keep blocks overlapping [start - margin, end + margin]
          namespace: monitoring
          pod: prometheus-kube-prometheus-stack-prometheus-0
          container: prometheus
          kube_context: null     # ambient KUBECONFIG/current-context when null

Needs Prometheus started with --web.enable-admin-api (kube-prometheus-stack:
prometheusSpec.enableAdminAPI: true).

Granularity is a TSDB block (2 h fresh, up to 10 % of retention once compacted),
so a 60 s run still carries the block(s) around it.
"""
import datetime
import gzip
import json
import logging
import os
import re
import shutil
import subprocess
import time
from dataclasses import dataclass
from string import Template
from typing import Any, Optional

from sma.model import SMAObserver
from sma.report import ReportIO

log = logging.getLogger(__name__)

SNAPSHOT_API = "http://localhost:9090/api/v1/admin/tsdb/snapshot"
SNAPSHOT_DIR = "/prometheus/snapshots"
DEFAULT_FILENAME = {"session": "prometheus-snapshot-session-${session}-${time}.tar.gz",
                    "run": "prometheus-snapshot-run-${startTime}_${runHash}.tar.gz"}
# one line per block: "<dir>\t<meta.json>"
LIST_BLOCKS = ('cd "$1" && for d in */; do [ -d "$d" ] || continue; '
               'printf "%s\\t" "${d%/}"; tr -d "\\n" < "$d/meta.json"; echo; done')


@dataclass
class SnapshotConfig:
    enabled: bool = True
    on: str = "session"
    location: Optional[str] = None
    filename: Optional[str] = None
    margin_s: int = 300
    namespace: str = "monitoring"
    pod: str = "prometheus-kube-prometheus-stack-prometheus-0"
    container: str = "prometheus"
    kube_context: Optional[str] = None

    @staticmethod
    def from_dict(d: dict) -> "SnapshotConfig":
        unknown = set(d) - set(SnapshotConfig.__dataclass_fields__)
        if unknown:
            raise ValueError(f"snapshot config: unknown keys {sorted(unknown)}")
        c = SnapshotConfig(**d)
        if c.on not in ("session", "run"):
            raise ValueError(f"snapshot config: on={c.on!r} must be 'session' or 'run'")
        if c.location is None and c.on == "session":
            c.location = "reports/tsdb"
        if c.filename is None:
            c.filename = DEFAULT_FILENAME[c.on]
        if c.location is not None:
            ReportIO._validate_location(c.location)
        return c


def _safe(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", name).strip("_") or "unnamed"


class SnapshotSmaModule(SMAObserver):
    def __init__(self, config: dict):
        self.config = SnapshotConfig.from_dict(dict(config or {}))
        self.session: Any = None            # SMASession, learned from the first report
        self.session_start: float = time.time()

    # ── kubectl plumbing ───────────────────────────────────────────────────
    def _exec(self, *cmd: str) -> list:
        base = ["kubectl"]
        if self.config.kube_context:
            base += ["--context", self.config.kube_context]
        return base + ["-n", self.config.namespace, "exec", self.config.pod,
                       "-c", self.config.container, "--", *cmd]

    def _blocks(self, name: str, start: float, end: float) -> list:
        """Block dirs of snapshot `name` overlapping [start - margin, end + margin] (epoch s)."""
        out = subprocess.check_output(self._exec("sh", "-c", LIST_BLOCKS, "sh", f"{SNAPSHOT_DIR}/{name}"), text=True)
        lo, hi = (start - self.config.margin_s) * 1000, (end + self.config.margin_s) * 1000
        keep, seen = [], 0
        for line in out.splitlines():
            if "\t" not in line:
                continue
            block, meta = line.split("\t", 1)
            seen += 1
            m = json.loads(meta)
            if m["maxTime"] >= lo and m["minTime"] <= hi:
                keep.append(block)
        if not keep:
            raise RuntimeError(f"snapshot {name}: none of {seen} blocks overlap "
                               f"{datetime.datetime.fromtimestamp(start)}..{datetime.datetime.fromtimestamp(end)}")
        log.info("snapshot %s: keeping %d of %d blocks", name, len(keep), seen)
        return keep

    def take(self, path: str, start: float, end: float) -> str:
        """POST the snapshot, stream the window's blocks out through gzip, delete it on the pod."""
        out = subprocess.check_output(self._exec("wget", "-qO-", "--post-data=", SNAPSHOT_API), text=True)
        name = json.loads(out)["data"]["name"]
        part = path + ".part"   # a dropped exec must not leave a truncated .tar.gz at the final path
        try:
            members = [f"{name}/{b}" for b in self._blocks(name, start, end)]
            os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
            tar = subprocess.Popen(self._exec("tar", "-C", SNAPSHOT_DIR, "-cf", "-", *members), stdout=subprocess.PIPE)
            assert tar.stdout is not None
            with gzip.open(part, "wb", compresslevel=6) as gz:
                shutil.copyfileobj(tar.stdout, gz, 1 << 20)
            if tar.wait() != 0:
                raise RuntimeError(f"tar of snapshot {name} failed with {tar.returncode}")
            os.replace(part, path)
        finally:
            if os.path.exists(part):
                os.unlink(part)
            subprocess.check_call(self._exec("rm", "-rf", f"{SNAPSHOT_DIR}/{name}"))
        log.info("TSDB snapshot %s -> %s (%d bytes)", name, path, os.path.getsize(path))
        return path

    def _path(self, context: dict, location: str) -> str:
        context = dict(context, time=datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ"))
        safe = {k: _safe(str(v)) for k, v in context.items()}   # a filename is one path component
        assert self.config.filename is not None   # from_dict fills it
        directory = Template(location).safe_substitute(context)
        ReportIO._validate_location(directory)    # substituted values must not escape either
        return os.path.join(directory, Template(self.config.filename).safe_substitute(safe))

    # ── hooks ──────────────────────────────────────────────────────────────
    def onSessionStart(self) -> None:
        self.session_start = time.time()

    def onReport(self, report: Any = None) -> None:
        self.session = report.metadata.session
        if self.config.enabled and self.config.on == "run":
            run = report.metadata.run
            self.take(self._path(report.metadata.to_dict({}), self.config.location or report.location),
                      run.startTime.timestamp(), run.endTime.timestamp())

    def onSessionEnd(self) -> None:
        if not (self.config.enabled and self.config.on == "session"):
            return
        context = self.session.to_dict({}) if self.session else {"session": "unnamed"}
        assert self.config.location is not None   # from_dict fills it for on: session
        self.take(self._path(context, self.config.location), self.session_start, time.time())
