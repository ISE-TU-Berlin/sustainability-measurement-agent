import logging
import time
import zipfile
import kubernetes
import yaml

from modules.telelocust.client import TeleLocustClient
from sma.model import SMAObserver
from sma.report import Report
import subprocess

WORKLOAD_POLLING_FREQUENCY_SECONDS = 0.3
DEPLOYMENT_YAML_PATH = "modules/telelocust/telelocust-deployment.yml" # todo: will this work when installed as package?

logging.basicConfig(level=logging.DEBUG)
log = logging.getLogger(__name__)

class TelelocustSmaModule(SMAObserver):
    """SMA Module that manages TeleLocust workload execution through REST and data retrieval."""

    def __init__(self, config: dict):
        TELELOCUST_URL = config.get("telelocust_url", "http://localhost:5123")
        self.config = config
        self.telelocust_client = TeleLocustClient(TELELOCUST_URL)
        log.debug(f"TeleLocustSmaModule initialized with TeleLocust URL: {TELELOCUST_URL}")


    def trigger(self):
        self.__run_workload()


    def onReport(self, report: Report) -> None:
        workload_zip_path = f"{report.location}/telelocust_run_data.zip"
        log.info(f"Downloading TeleLocust workload data to {workload_zip_path}...")
        self.telelocust_client.download_run_data(workload_zip_path)

        unzip_path = report.location + "/telelocust_data"
        log.info(f"Extracting TeleLocust data to {unzip_path}...")
        with zipfile.ZipFile(workload_zip_path, 'r') as zip_ref:
            zip_ref.extractall(unzip_path)
        log.info("TeleLocust data extracted successfully.")

    def onSetup(self):
        if self.__deploy_enabled():
            log.info(subprocess.run("pwd", shell=True, capture_output=True, text=True).stdout)
            log.info("Deploying TeleLocust infrastructure...")
            self.__kubectl("apply", DEPLOYMENT_YAML_PATH)
            log.info("TeleLocust infrastructure deployed.")

    def onTeardown(self):
        if self.__deploy_enabled():
            log.info("Tearing down TeleLocust infrastructure...")
            self.__kubectl("delete", DEPLOYMENT_YAML_PATH)
            log.info("TeleLocust infrastructure torn down.")

    def __kubectl(self, command: str, file: str) -> str:
        result = subprocess.run(
            ["kubectl"] + command.split() + ["-f", file],
            capture_output=True,
            text=True,
            shell=True,
        )
        if result.returncode != 0:
            raise RuntimeError(f"kubectl command failed: {result.stderr}")
        return result.stdout

    def __deploy_enabled(self) -> bool:
        return self.config.get("deploy", False)

    def __run_workload(self):
        self.telelocust_client.start_test_run( 
            self.config.get("sut_host", "http://teastore-webui"),
            users=self.config.get("users", 10),
            spawn_rate=self.config.get("spawn_rate", 2), 
            run_time=self.config.get("run_time", "30s"),
            locustfile_path=None # todo: allow specifying locustfile URL as well
            )
        log.info(f'Started test run with token: {self.telelocust_client.token}')  
        while True:
            status = self.telelocust_client.get_run_status()
            log.info(f'Run status: {status}')
            if status['status'] != 'running':
                break
            time.sleep(0.3)
        log.info(f"Test run finished. {self.telelocust_client.get_run_status()}")

