import logging
import time
import zipfile
from typing import Optional, Dict, Any

from modules.telelocust.client import TeleLocustClient
from sma.model import SMAObserver, Triggerable
from sma.report import Report
import subprocess
import os
from importlib import resources

WORKLOAD_POLLING_FREQUENCY_SECONDS = 0.3
DEPLOYMENT_YAML_PATH = resources.files("modules").joinpath(
    "telelocust/telelocust-deployment.yaml"
)
LOCAL_PORT = 5123

logging.basicConfig(level=logging.DEBUG)
log = logging.getLogger(__name__)

class TelelocustSmaModule(SMAObserver, Triggerable):
    """SMA Module that manages TeleLocust workload execution through REST and data retrieval."""

    def __init__(self, config: dict):
        TELELOCUST_URL = config.get("telelocust_url", f"http://localhost:{LOCAL_PORT}")
        self.config = config
        self.telelocust_client = TeleLocustClient(TELELOCUST_URL)
        log.debug(f"TeleLocustSmaModule initialized with TeleLocust URL: {TELELOCUST_URL}")


    def trigger(self, kwargs) -> Optional[Dict[str, Any]]:
        self.__run_workload(kwargs)
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
            self.__kubectl("apply", DEPLOYMENT_YAML_PATH)
            time.sleep(1)  # Wait for deployment to stabilize
            log.info("TeleLocust infrastructure deployed.")

        if self.__port_forward_enabled():
            #TODO: XXX: don't we aks which namespace to use in the config
            log.info(f"Setting up port forwarding to TeleLocust on localhost:{LOCAL_PORT}...")
            # time.sleep(5)  # Give some time for pod to establish, todo: improve with proper check #XXX: yes!
            _wait = subprocess.run(["kubectl","-n","locust","wait", "deploy/telelocust", "--for=condition=Available", "--timeout=600s"])
            log.debug(f"kubectl wait deploy/telelocust --for=condition=Available --timeout=600s returned {_wait.returncode}")
            log.debug(subprocess.run(["kubectl", "get", "pods", "-n", "locust"], capture_output=True, text=True).stdout)
            # Start port forwarding in the background
            self.port_forward_process = subprocess.Popen(
                ["kubectl", "port-forward", "deployment/telelocust", f"{LOCAL_PORT}:5123", "-n", "locust"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            log.debug(f"Port forwarding process started with PID: {self.port_forward_process.pid}, {self.port_forward_process.stdout.readline()}") 
                    
            if self.port_forward_process.poll() is not None:
                raise RuntimeError("Port forwarding process terminated unexpectedly.")
            log.info("Port forwarding established.")


    def onTeardown(self):
        if self.__port_forward_enabled() and hasattr(self, 'port_forward_process'):
            log.info("Stopping port forwarding...")
            self.port_forward_process.terminate()

        if self.__deploy_enabled():
            log.info("Tearing down TeleLocust infrastructure...")
            self.__kubectl("delete", DEPLOYMENT_YAML_PATH)
            log.info("TeleLocust infrastructure torn down.")

    def __kubectl(self, command: str, file: str) -> str:
        cmdline = ["kubectl"] + command.split() + ["-f", file]
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
        return self.config.get("port_forward", False)

    def __run_workload(self, kwargs):
        def get_value(key, default=None):
            return kwargs.get(key, self.config.get(key, default))
        sut_url = get_value("sut_url", None)
        if sut_url is None:
            raise ValueError("No SUT URL specified. Please provide a SUT URL in the configuration.")
        self.telelocust_client.start_test_run(
            get_value("sut_url",None),
            users=get_value("users", 10),
            spawn_rate=get_value("spawn_rate", 2),
            run_time=get_value("run_time", "30s"),
            locustfile_path=self.config.get("locustfile") # todo: allow specifying locustfile URL as well
            )
        log.info(f'Started test run with token: {self.telelocust_client.token}')
        # todo: maybe we add a timeout here?
        while True:
            status = self.telelocust_client.get_run_status()
            log.info(f'Run status: {status}')
            if status['status'] != 'running':
                break
            time.sleep(WORKLOAD_POLLING_FREQUENCY_SECONDS)
        log.info(f"Test run finished. {self.telelocust_client.get_run_status()}")

