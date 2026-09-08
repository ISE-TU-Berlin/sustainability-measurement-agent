"""HTTP client for a telek6 server (https://github.com/tawalaya/telek6).

Allowing to start workloads driven by k6 scripts, similar behavior to telelocust.
"""
import base64
import io
import logging
import threading
import zipfile
from typing import Dict, List, Optional

import requests

REQUEST_TIMEOUT = 10
POLL_INTERVAL_S = 1
POLL_RETRIES = 5

log = logging.getLogger(__name__)


def _b64(path: str) -> str:
    with open(path, "rb") as fh:
        return base64.b64encode(fh.read()).decode("ascii")


class Telek6Client:
    def __init__(self, url: str):
        self.url = url.rstrip("/")
        self.token: Optional[str] = None

    def health_check(self) -> bool:
        r = requests.get(f"{self.url}/healthz", timeout=REQUEST_TIMEOUT)
        return r.status_code == 200

    def start_run(self, script_path: str, files: Optional[Dict[str, str]] = None,
                  env: Optional[Dict[str, str]] = None, args: Optional[List[str]] = None,
                  timeout_s: Optional[int] = None) -> str:
        body = {"script_base64": _b64(script_path),
                "files": {name: _b64(path) for name, path in (files or {}).items()},
                "env": env or {}, "args": args or [], "timeout_s": timeout_s}
        r = requests.post(f"{self.url}/runs/start", json=body, timeout=REQUEST_TIMEOUT)
        r.raise_for_status()
        token: str = r.json()["token"]
        self.token = token
        return token

    def status(self) -> dict:
        r = requests.get(f"{self.url}/runs/{self.token}", timeout=REQUEST_TIMEOUT)
        r.raise_for_status()
        return r.json()

    def stop(self) -> dict:
        r = requests.post(f"{self.url}/runs/{self.token}/stop", json={}, timeout=REQUEST_TIMEOUT + 15)
        r.raise_for_status()
        return r.json()

    def wait(self, cancel: threading.Event, poll_interval_s: float = POLL_INTERVAL_S) -> Optional[dict]:
        """Poll until finished or `cancel`; a few transient errors are retried, more raise.

        Returns the final status, or None when cancelled (the run was stopped).
        """
        retries = 0
        while not cancel.is_set():
            try:
                st = self.status()
                retries = 0
            except requests.RequestException as exc:
                retries += 1
                if retries > POLL_RETRIES:
                    try:   # best effort: never leave k6 loading the SUT behind an SMA that moved on
                        self.stop()
                    except requests.RequestException as stop_exc:
                        log.error("telek6 run %s could not be stopped: %s", self.token, stop_exc)
                    raise
                log.warning("telek6 poll failed (%d/%d): %s", retries, POLL_RETRIES, exc)
                cancel.wait(retries * poll_interval_s)
                continue
            if st["status"] != "running":
                return st
            cancel.wait(poll_interval_s)
        log.info("cancel set; stopping telek6 run %s", self.token)
        self.stop()
        return None

    def download(self, into_dir: str) -> List[str]:
        r = requests.get(f"{self.url}/runs/{self.token}/download", timeout=REQUEST_TIMEOUT * 6)
        r.raise_for_status()
        with zipfile.ZipFile(io.BytesIO(r.content)) as zf:
            zf.extractall(into_dir)
            return zf.namelist()
