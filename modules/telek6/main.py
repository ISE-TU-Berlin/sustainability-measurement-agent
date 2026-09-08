"""Telek6 SMA module: drives a long-lived telek6 pod as the treatment.

    modules:
      telek6:
        module: telek6
        config:
          url: http://localhost:30124   # the telek6 Service; derived when port_forward is set
          timeout_s: 900                # per-run cap on the server side, overridable per call
          poll_interval_s: 1
          # Deployment options, as in telelocust. deploy: true applies the bundled
          # telek6.yaml, a string is a path to your own manifest; both get the patches
          # below. apply is idempotent, so a long-lived pod survives sessions;
          # undeploy: true deletes it at teardown.
          deploy: false
          namespace: telek6
          image: null                   # default: the manifest's pinned ghcr.io/tawalaya/telek6 tag
          imagePullSecrets: null        # e.g. myregistrykey
          nodeSelector: null            # e.g. ["kubernetes.io/arch=amd64", "node-role.kubernetes.io/control-plane="]
          deploy_timeout_s: 300
          undeploy: false
          # Networking options, as in telelocust: disabled (use url) | proxy (kubectl
          # port-forward to localhost:5124) | nodeport (nodeIP + the Service's nodePort)
          port_forward: disabled
          nodeIP: null                  # nodeport only; default: the host of the kubeconfig server
          kube_context: null            # ambient KUBECONFIG/current-context when null
    observation:
      mode: module
      module_trigger: telek6

`trigger(cancel, script_path=..., files={name: path}, env={}, args=[],
timeout_s=None, download_dir=None)` starts the run, waits, stops it on cancel,
and downloads the run directory into `download_dir` (a temp dir when not given;
onReport then moves it under the report). Generic over what the script does:
the plan is just a file, the summary is whatever k6 prints. Returned meta:
token, k6_status (complete|failed|cancelled|timeout), exit_code, started_at,
finished_at, run_dir, files.
"""
import logging
import os
import shutil
import subprocess
import tempfile
import threading
import time
from dataclasses import dataclass
from enum import Enum, auto
from importlib import resources
from typing import Any, Dict, List, Optional, Union
from urllib.parse import urlparse

import requests
import yaml

from modules.telek6.client import Telek6Client
from sma.model import SMAObserver, Triggerable

log = logging.getLogger(__name__)

BUNDLED_MANIFEST = resources.files("modules").joinpath("telek6/telek6.yaml")
CONTAINER_PORT = 5124
LOCAL_PORT = 5124


class Telek6Forwarding(Enum):
    DISABLED = auto()
    PROXY = auto()
    NODEPORT = auto()


@dataclass
class Telek6Config:
    url: Optional[str] = None
    timeout_s: Optional[int] = 900
    poll_interval_s: float = 1.0

    # deployment options
    deploy: Union[bool, str] = False   # true: bundled manifest; str: path to a manifest
    namespace: str = "telek6"
    image: Optional[str] = None
    imagePullSecrets: Optional[str] = None
    nodeSelector: Optional[List[str]] = None
    deploy_timeout_s: int = 300
    undeploy: bool = False

    # networking options
    port_forward: Telek6Forwarding = Telek6Forwarding.DISABLED
    nodeIP: Optional[str] = None
    kube_context: Optional[str] = None

    @staticmethod
    def from_dict(d: dict) -> "Telek6Config":
        unknown = set(d) - set(Telek6Config.__dataclass_fields__)
        if unknown:
            raise ValueError(f"telek6 config: unknown keys {sorted(unknown)}")
        pf = d.get("port_forward", Telek6Forwarding.DISABLED)
        if isinstance(pf, bool):
            pf = Telek6Forwarding.PROXY if pf else Telek6Forwarding.DISABLED
        elif isinstance(pf, str):
            pf = Telek6Forwarding[pf.upper()]
        d["port_forward"] = pf
        c = Telek6Config(**d)
        if pf == Telek6Forwarding.DISABLED and not c.url:
            raise ValueError("telek6 config: url is required unless port_forward is set")
        if isinstance(c.deploy, str) and not os.path.isfile(c.deploy):
            raise ValueError(f"telek6 config: deploy manifest {c.deploy} does not exist")
        return c


class Telek6SmaModule(SMAObserver, Triggerable):
    def __init__(self, config: dict):
        self.config = Telek6Config.from_dict(dict(config))
        self.client = Telek6Client(self.config.url or "")   # replaced in onSetup when the URL is derived
        self.manifest: Optional[str] = None                  # the patched manifest that was applied
        self.port_forward_process: Optional[subprocess.Popen] = None
        self._pending_dirs: list = []   # temp download dirs to move under the report

    # ── deployment (kubectl; a Kubernetes API client is the upgrade if kubectl is ever not on PATH)
    def _kubectl(self, *args: str, check: bool = True) -> str:
        cmd = ["kubectl"] + (["--context", self.config.kube_context] if self.config.kube_context else []) + list(args)
        log.debug("kubectl: %s", " ".join(cmd))
        p = subprocess.run(cmd, capture_output=True, text=True)
        if check and p.returncode != 0:
            raise RuntimeError(f"kubectl {' '.join(args)} failed ({p.returncode}): {p.stderr.strip()}")
        return p.stdout

    def prepare_manifest(self) -> str:
        """Load the bundled or configured manifest, apply the config's patches, write it to a temp file."""
        src = BUNDLED_MANIFEST if self.config.deploy is True else str(self.config.deploy)
        with open(str(src)) as fh:
            docs = list(yaml.safe_load_all(fh))
        for doc in docs:
            if doc.get("kind") != "Deployment":
                continue
            pod = doc["spec"]["template"]["spec"]
            if self.config.nodeSelector:
                pod["nodeSelector"] = dict(s.split("=", 1) for s in self.config.nodeSelector)
            if self.config.image:
                for c in pod["containers"]:
                    if c["name"] == "telek6":
                        c["image"] = self.config.image
            if self.config.imagePullSecrets:
                pod["imagePullSecrets"] = [{"name": self.config.imagePullSecrets}]
        with tempfile.NamedTemporaryFile("w", suffix=".yaml", prefix="telek6-", delete=False) as tmp:
            yaml.safe_dump_all(docs, tmp)
        log.debug("patched telek6 manifest written to %s", tmp.name)
        return tmp.name

    def deploy(self) -> None:
        assert self.config.deploy, "deploy() needs config.deploy"
        ns = self.config.namespace
        self._kubectl("create", "namespace", ns, check=False)   # exists already on the second session
        self.manifest = self.prepare_manifest()
        log.info("applying telek6 manifest %s to namespace %s", self.manifest, ns)
        self._kubectl("-n", ns, "apply", "-f", self.manifest)
        self._kubectl("-n", ns, "wait", "deployment/telek6",
                      "--for=condition=Available", f"--timeout={self.config.deploy_timeout_s}s")

    def undeploy(self) -> None:
        manifest = self.manifest or self.prepare_manifest()
        log.info("deleting telek6 manifest %s", manifest)
        self._kubectl("-n", self.config.namespace, "delete", "-f", manifest, "--ignore-not-found")

    # ── networking
    def nodeport_url(self) -> str:
        port = self._kubectl("-n", self.config.namespace, "get", "svc", "telek6",
                             "-o", "jsonpath={.spec.ports[0].nodePort}").strip()
        host = self.config.nodeIP
        if not host:
            log.warning("deriving the node IP from the kubeconfig server; set nodeIP if that is not a cluster node")
            server = self._kubectl("config", "view", "--minify", "-o", "jsonpath={.clusters[0].cluster.server}").strip()
            host = urlparse(server).hostname
        return f"http://{host}:{port}"

    def port_forward_url(self) -> str:
        cmd = ["kubectl"] + (["--context", self.config.kube_context] if self.config.kube_context else [])
        cmd += ["-n", self.config.namespace, "port-forward", "deployment/telek6", f"{LOCAL_PORT}:{CONTAINER_PORT}"]
        self.port_forward_process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        assert self.port_forward_process.stdout is not None
        first = self.port_forward_process.stdout.readline()   # "Forwarding from ..." once the tunnel is up
        if self.port_forward_process.poll() is not None:
            raise RuntimeError(f"kubectl port-forward exited: {first.strip()}")
        log.info("port-forward established: %s", first.strip())
        return f"http://localhost:{LOCAL_PORT}"

    # ── hooks
    def onSetup(self) -> None:
        if self.config.deploy:
            self.deploy()
        url = self.config.url
        if self.config.port_forward == Telek6Forwarding.PROXY:
            url = self.port_forward_url()
        elif self.config.port_forward == Telek6Forwarding.NODEPORT:
            url = self.nodeport_url()
        assert url, "telek6 URL not found"
        log.info("telek6 URL: %s", url)
        self.client = Telek6Client(url)
        for attempt in range(10):   # a just-deployed Service can lag its pod's readiness by a moment
            try:
                if self.client.health_check():
                    log.info("telek6 at %s is healthy", url)
                    return
            except requests.RequestException as exc:
                log.warning("telek6 health check %d/10 failed: %s", attempt + 1, exc)
            time.sleep(1)
        raise RuntimeError(f"telek6 at {url} is not healthy")

    def onTeardown(self) -> None:
        if self.port_forward_process is not None:
            self.port_forward_process.terminate()
        if self.config.deploy and self.config.undeploy:
            self.undeploy()

    def trigger(self, cancel: threading.Event, **kwargs) -> Dict[str, Any]:
        script_path = kwargs["script_path"]
        download_dir = kwargs.get("download_dir")
        temp = download_dir is None
        if temp:
            download_dir = tempfile.mkdtemp(prefix="telek6-")
        timeout_s = kwargs.get("timeout_s", self.config.timeout_s)
        t0 = time.time()
        token = self.client.start_run(script_path, files=kwargs.get("files"), env=kwargs.get("env"),
                                      args=kwargs.get("args"), timeout_s=timeout_s)
        log.info("telek6 run %s started (%.2fs after trigger)", token, time.time() - t0)
        final = self.client.wait(cancel, self.config.poll_interval_s)
        try:
            files = self.client.download(download_dir)
        except Exception as exc:  # partial data is still evidence; the status says what happened
            log.error("telek6 download of run %s failed: %s", token, exc)
            files = []
        st = self.client.status()   # re-fetch: the server sets stopped=timeout just after status=finished
        if final is None:
            status = "cancelled"
        elif st.get("stopped") == "timeout":
            status = "timeout"
        else:
            status = "complete" if st.get("exit_code") == 0 else "failed"
        if temp:
            self._pending_dirs.append(download_dir)
        return {"token": token, "k6_status": status, "exit_code": st.get("exit_code"),
                "started_at": st.get("started_at"), "finished_at": st.get("finished_at"),
                "run_dir": download_dir, "files": files}

    def onReport(self, report: Any = None) -> None:
        for d in self._pending_dirs:
            dest = os.path.join(report.location, "telek6", os.path.basename(d))
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            shutil.move(d, dest)
            log.info("telek6 run data moved to %s", dest)
        self._pending_dirs = []
