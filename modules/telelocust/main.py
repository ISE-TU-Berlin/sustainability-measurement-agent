from  dataclasses import dataclass
import logging
import threading
import time
import zipfile
from enum import Enum, auto
from typing import Optional, Dict, Any

import requests
import urllib3

from modules.telelocust.client import TeleLocustClient
from sma import config
from sma.model import SMAObserver, Triggerable
from sma.report import Report
import subprocess
import os
from importlib import resources

DEPLOYMENT_YAML_PATH = resources.files("modules").joinpath(
    "telelocust/telelocust-deployment.yaml"
)

LOCAL_PORT = 5123

logging.basicConfig(level=logging.DEBUG)
log = logging.getLogger(__name__)

class TelelocustForwarding(Enum):
    DISABLED = auto(),
    PROXY = auto(),
    NODEPORT = auto()

@dataclass
class TelelocustConfig:
    sut_url: str
    locustfile : str

    # workload options
    users : Optional[int] = 10
    spawn_rate : Optional[int] = 2
    run_time : Optional[str] = "30s"

    # deployment options
    namespace: str = "locust"
    deploy : Optional[bool] = False
    telelocust_url : Optional[str] = f"http://localhost:{LOCAL_PORT}"
    port_forward : Optional[TelelocustForwarding] = TelelocustForwarding.DISABLED


    def validate(self) -> bool:
        assert len(self.sut_url) > 0, "SUT URL must be specified."
        assert len(self.namespace) > 0, "Namespace must be specified."
        assert os.path.isfile(self.locustfile), f"Locustfile {self.locustfile} does not exist."

        return True

    @staticmethod
    def from_dict(config: dict) -> "TelelocustConfig":
        config["port_forward"] = TelelocustForwarding[config.get("port_forward", "DISABLED").upper()]
        # Fix backward compatibility
        if "ramp" in config and "spawn_rate" not in config:
            config["spawn_rate"] = config["ramp"]
            log.warning("The 'ramp' option is deprecated. Please use 'spawn_rate' instead.")
        return TelelocustConfig(**config)

    def __getitem__(self, key):
        return getattr(self, key)

    def get(self, key, default=None):
        return getattr(self, key, default)

    @staticmethod
    def mergeWithArgs(config: "TelelocustConfig", kwargs: dict) -> "TelelocustConfig":
        """
            allow kwargs to override config values
        """
        config_dict = config.__dict__.copy()
        for key in config_dict.keys():
            if key in kwargs:
                config_dict[key] = kwargs[key]
        return TelelocustConfig(**config_dict)



class TelelocustSmaModule(SMAObserver, Triggerable):
    """SMA Module that manages TeleLocust workload execution through REST and data retrieval."""

    def __init__(self, config: dict):
        self.config: TelelocustConfig = TelelocustConfig.from_dict(config)
        if not self.config.validate():
            raise ValueError("Invalid TeleLocust configuration.")
        log.debug(f"Loaded TeleLocust configuration: {self.config}")
        self.telelocust_client = None

        self.cancel : Optional[threading.Event]= None

        self.deployed = False


    def trigger(self, cancel: threading.Event, **kwargs) -> Optional[Dict[str, Any]]:
        self.cancel = cancel
        self.__run_workload(**kwargs)
        return None


    def onReport(self, report: Report) -> None:
        workload_zip_path = f"{report.location}/telelocust_run_data.zip"
        log.info(f"Downloading TeleLocust workload data to {workload_zip_path}...")
        self.telelocust_client.download_run_data(workload_zip_path)

        unzip_path = report.location + "/telelocust_data"
        log.info(f"Extracting TeleLocust data to {unzip_path}...")
        with zipfile.ZipFile(workload_zip_path, 'r') as zip_ref:
            zip_ref.extractall(unzip_path)
        log.info("TeleLocust data extracted successfully.")

    #TODO: idearly we swich to kubernetes API calls instead so that we don't depend on kubeclt
    #XXX: we should ask the user (in the config) which kube context we want to use ...
    def onSetup(self):
        if self.__deploy_enabled():
            log.info(subprocess.run("pwd", shell=False, capture_output=True, text=True).stdout)
            log.info("Deploying TeleLocust infrastructure...")
            subprocess.run(["kubectl", "create", "namespace", self.config.namespace], capture_output=True, text=True) # create namespace if not exists, ignore error if it already exists
            self.__kubectl(f"apply", DEPLOYMENT_YAML_PATH, namespace=self.config.namespace)
            time.sleep(1)  # Wait for deployment to stabilize
            log.info("TeleLocust infrastructure deployed.")
            _wait = subprocess.run(["kubectl", "-n", self.config.get("namespace"), "wait", "deploy/telelocust",
                                    "--for=condition=Available", "--timeout=600s"])
            self.deployed = True

        TELELOCUST_URL = None
        if self.__port_forward_enabled():
            #TODO: XXX: don't we aks which namespace to use in the config
            if log.level >= logging.DEBUG:
                log.debug(f"kubectl wait deploy/telelocust --for=condition=Available --timeout=600s returned {_wait.returncode}")
                log.debug(subprocess.run(["kubectl", "get", "pods", "-n", self.config.get("namespace")], capture_output=True, text=True).stdout)
            if self.config.port_forward == TelelocustForwarding.PROXY:
                self.kubectl_port_forward()
                TELELOCUST_URL = f"http://localhost:{LOCAL_PORT}"
            elif self.config.port_forward == TelelocustForwarding.NODEPORT:
                #TODO: it would be much better to do this with a porpper client
                assignedNodeport = subprocess.check_output(["kubectl","get","-n",self.config.namespace,"svc","telelocust","-o","jsonpath={.spec.ports[0].nodePort}"]).decode("utf-8").strip()
                # The assumption is that the IP of the control plane is the same as the IP we can use to access the cluster
                nodeIPString = subprocess.check_output(["kubectl","config","view","--minify","-o","jsonpath={.clusters[0].cluster.server}"]).decode("utf-8").strip()
                nodeIPUrl = urllib3.util.parse_url(nodeIPString)
                nodeIP = nodeIPUrl.host
                TELELOCUST_URL = f"http://{nodeIP}:{assignedNodeport}"
                if log.level >= logging.DEBUG:
                    log.debug(f"TeleLocust nodeport assigned: {assignedNodeport}")
                    log.debug(f"connecting to {TELELOCUST_URL} with {requests.get(TELELOCUST_URL+'/healthz').status_code}")
        else:
            TELELOCUST_URL = self.config.get("telelocust_url", f"http://localhost:{LOCAL_PORT}")

        assert TELELOCUST_URL is not None, "TeleLocust URL not found."
        assert urllib3.util.parse_url(TELELOCUST_URL).scheme == "http", "TeleLocust URL must be HTTP."
        log.info(f"TeleLocust URL: {TELELOCUST_URL}")
        self.telelocust_client = TeleLocustClient(TELELOCUST_URL)

        assert self.telelocust_client is not None, "TeleLocust client not initialized."

    def kubectl_port_forward(self):
        # Start port forwarding in the background
        self.port_forward_process = subprocess.Popen(
            ["kubectl", "port-forward", "deployment/telelocust", f"{LOCAL_PORT}:5123", "-n",
             self.config.get("namespace")],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        log.debug(
            f"Port forwarding process started with PID: {self.port_forward_process.pid}, {self.port_forward_process.stdout.readline()}")

        if self.port_forward_process.poll() is not None:
            raise RuntimeError("Port forwarding process terminated unexpectedly.")
        log.info("Port forwarding established.")

    def onTeardown(self):
        if self.__port_forward_enabled() and hasattr(self, 'port_forward_process'):
            log.info("Stopping port forwarding...")
            self.port_forward_process.terminate()

        if self.__deploy_enabled() and self.deployed:
            log.info("Tearing down TeleLocust infrastructure...")
            self.__kubectl(f"delete -n {self.config.namespace}", DEPLOYMENT_YAML_PATH, namespace=self.config.namespace)
            log.info("TeleLocust infrastructure torn down.")

    def __kubectl(self, command: str, file: str, namespace: str = None) -> str:
        cmdline = ["kubectl"] + command.split() + ["-f", file]
        if namespace:
            cmdline += ["-n", namespace]
        log.debug(f"Executing kubectl command: {cmdline}")
        result = subprocess.run(
            cmdline,
            capture_output=True,
            text=True,
            # shell=True,
        )
        log.debug(f"kubectl stdout: {result.stdout}")
        log.debug(f"kubectl stderr: {result.stderr}")
        if result.returncode != 0:
            raise RuntimeError(f"kubectl command failed: {result.stderr}")
        return result.stdout

    def __deploy_enabled(self) -> bool:
        return self.config.get("deploy", False)
    
    def __port_forward_enabled(self) -> bool:
        return self.config.get("port_forward", TelelocustForwarding.DISABLED) in (TelelocustForwarding.PROXY, TelelocustForwarding.NODEPORT)

    def __run_workload(self, **kwargs):
        
        run_config = TelelocustConfig.mergeWithArgs(self.config, kwargs)

        if run_config.sut_url is None:
            raise ValueError("No SUT URL specified. Please provide a SUT URL in the configuration.")

        if self.cancel is None:
            raise ValueError("No cancel event provided. Please provide a cancel event in the configuration.")

        self.telelocust_client.start_test_run(
            run_config.get("sut_url",None),
            users= run_config.get("users", 10),
            spawn_rate= run_config.get("spawn_rate", 2),
            run_time= run_config.get("run_time", "30s"),
            locustfile_path=run_config.get("locustfile") # todo: allow specifying locustfile URL as well
            )
        
        log.info(f'Started test run with token: {self.telelocust_client.token}')
        # todo: maybe we add a timeout here?
        final_status = self.telelocust_client.wait_for_run_completion(self.cancel, polling_interval_seconds=1, max_retries=3)

        if final_status is None:
            log.warning("Test run completion status is unknown due to polling or timeout errors.")
        else:
            log.info(f"Test run finished. {final_status}")


