import logging
import sys
from sma import SustainabilityMeasurementAgent, Config, SMAObserver
from sma.model import SMASession
import os

from sma.log import initialize_logging

logLevel = os.getenv("LOGLEVEL", "INFO").upper()
initialize_logging(logLevel)

log = logging.getLogger("sma.main")  



log.debug("Loading configuration...")


if len(sys.argv) != 2:
    log.error("Usage: python sma.py <config-file>")
    sys.exit(1)

config = Config.from_file(sys.argv[1])

log.debug("Creating Agent...")
sma = SustainabilityMeasurementAgent(config)

class SimpleLogger(SMAObserver):
    def onSetup(self) -> None:
        log.info("SMA setup started.")

    def onLeft(self) -> None:
        log.info("Left window started.")

    def onStart(self) -> None:
        log.info("Observation started.")

    def onEnd(self) -> None:
        log.info("Observation ended.")

    def onRight(self) -> None:
        log.info("Right window started.")

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

