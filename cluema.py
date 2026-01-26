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
from sma.model import SMASession

from telelocust.client import TeleLocustClient

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

    class SimpleLogger(SMAObserver):
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

        def onTeardown(self) -> None:
            log.info("SMA teardown completed.")

    sma.register_sma_observer(SimpleLogger())

    log.debug("Connecting to services...")
    sma.connect()

    if probe != 'none':
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

    def workload_blocking() -> None:
        SUT_URL = "http://teastore-webui"
        tele = TeleLocustClient(SUT_URL)
        tele.start_test_run(users=10, spawn_rate=2, run_time=f"30s", locustfile_path='locustfile.py')
        log.info(f'Started test run with token: {tele.token}')  
        while True:
            status = tele.get_run_status()
            log.info(f'Run status: {status}')
            if status['status'] != 'running':
                break
            time.sleep(1)
        log.info(f"Test run finished. {tele.get_run_status()}")
        tele.download_run_data("")



    log.debug("Starting SMA run...")
    sma.setup(SMASession(
        name="TestSession"
    ))
    sma.run(workload_blocking)
    sma.teardown()

    log.info("Sustainability Measurement Agent finished.")



if __name__ == '__main__':
    run_with_config()
