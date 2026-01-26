import sys
import os
import logging
import click
import time


from unittest import runner
from rich.logging import RichHandler
from sma.log import initialize_logging

from sma import SustainabilityMeasurementAgent
from sma import Config, SMAObserver
from sma import Report
from sma.model import SMASession

from modules.telelocust.client import TeleLocustClient
import zipfile

logLevel = os.getenv("LOGLEVEL", "INFO").upper()
# already initialized through the module when importing SMA, so we'll redefine with rich logging
initialize_logging(logLevel, logger_class="rich.logging.RichHandler")
logging.basicConfig(format="%(name)s: %(message)s")
log = logging.getLogger("sma.main")


@click.command()
@click.argument('config_file', type=click.Path(exists=True))
@click.option('--probe', type=click.Choice(
    ['none', 'dry', 'warn', 'fail']),
    default='warn',
    help="""Check if measurements exists before running.
    'dry' will quit after probing,
    'warn' will log warnings (default),
    'fail' will abort execution if any meausurement is not present,
    'none' will skip probing."""
)
def run_with_config(config_file: str, probe: str):
    """Run the Sustainability Measurement Agent with a given configuration file.

      You can use e.g. examples/minimal.yaml

      To set log level, use the LOGLEVEL environment variable, e.g.:
      LOGLEVEL=DEBUG python main_fancy.py examples/minimal.yaml
      """

    log.debug("Loading configuration...")
    config = Config.from_file(config_file)

    log.debug("Creating Agent...")
    sma = SustainabilityMeasurementAgent(config)

    class WorkloadController(SMAObserver):

        def __init__(self):
            TELELOCUST_URL = "http://localhost:5123" # todo: from config
            self.telelocust_client = TeleLocustClient(TELELOCUST_URL)

        def run_workload(self):
            self.telelocust_client.start_test_run( # todo: load from config
                sut_host="http://teastore-webui",
                users=10,
                spawn_rate=2, 
                run_time=f"30s",
                locustfile_path=None
                )
            log.info(f'Started test run with token: {self.telelocust_client.token}')  
            while True:
                status = self.telelocust_client.get_run_status()
                log.info(f'Run status: {status}')
                if status['status'] != 'running':
                    break
                time.sleep(0.3)
            log.info(f"Test run finished. {self.telelocust_client.get_run_status()}")


        def onSetup(self) -> None:
            log.info("SMA setup started.")

        def onLeftStarted(self) -> None:
            log.info("Left window started.")

        def onStart(self) -> None:
            log.info("Observation started.")

        def onEnd(self) -> None:
            log.info("Observation ended.")

        def onRightFinished(self) -> None:
            log.info("Right window finished.")

        def onReport(self, report: Report) -> None:
            workload_zip_path = f"{report.location}/telelocust_run_data.zip"
            log.info(f"Downloading TeleLocust workload data to {workload_zip_path}...")
            self.telelocust_client.download_run_data(workload_zip_path)

            unzip_path = report.location + "/telelocust_data"
            log.info(f"Extracting TeleLocust data to {unzip_path}...")
            with zipfile.ZipFile(workload_zip_path, 'r') as zip_ref:
                zip_ref.extractall(unzip_path)
            log.info("TeleLocust data extracted successfully.")

        def onTeardown(self) -> None:
            log.info("SMA teardown completed.")

    workload_controller = WorkloadController()
    sma.register_sma_observer(workload_controller)

    log.debug("Connecting to services...")
    sma.connect()

    if probe != 'none': # todo: make probing a module?
        log.info("Probing measurements...")
        results = sma.probe()
        all_available = all(results.values())
        for name, available in results.items():
            if available:
                log.info(f"✅ {name} is available.")
            else:
                log.warning(f"⚠️ {name} is NOT available.")

        if probe == 'dry':
            log.info("Dry run complete. Exiting.")
            sys.exit(0)

        if not all_available:
            if probe == 'fail':
                log.error("Not all measurements are available. Aborting.")
                sys.exit(1)
            elif probe == 'warn':
                log.warning("Not all measurements are available. Continuing as per 'warn' setting.")

    def wait_for_user() -> None:
        input("Hit Enter to to Stop Measuring...")


    log.debug("Starting SMA run...")
    sma.setup(SMASession(
        name="TestSession"
    ))

    # todo: load via moduleconfig
    sma.run(workload_controller.run_workload)
    sma.teardown()

    log.info("Sustainability Measurement Agent finished.")



if __name__ == '__main__':
    run_with_config()
