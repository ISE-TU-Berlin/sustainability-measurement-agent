import sys
import os
import logging
from rich.logging import RichHandler
from sma.log import initialize_logging

from sma import SustainabilityMeasurementAgent
from sma import Config, SMAObserver
from sma.model import SMASession



# fany cli stuff, not in Pipfile yet to keep dependcies minimal
import click

logLevel = os.getenv("LOGLEVEL", "INFO").upper()
# already initialized through the module when importing SMA, so we'll redefine with rich logging
initialize_logging(logLevel, logger_class="rich.logging.RichHandler")
logging.basicConfig(format="%(name)s: %(message)s")
log = logging.getLogger("sma.main")  


@click.command()
@click.argument('config_file', type=click.Path(exists=True))
def run_with_config(config_file: str):
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

    def wait_for_user() -> None:
        input("Hit Enter to to Stop Measuring...")

    log.debug("Starting SMA run...")
    sma.setup(SMASession(
        name="TestSession"
    ))
    sma.run(wait_for_user)
    sma.teardown()

    log.info("Sustainability Measurement Agent finished.")
    report_location = config.report.location
    if report_location:
        log.info(f"Report written to {report_location}")



if __name__ == '__main__':
    run_with_config()


