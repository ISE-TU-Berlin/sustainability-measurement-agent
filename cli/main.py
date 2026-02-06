import sys
import os
import logging
import click

import sma
from sma import ReportIO, SMASession
from sma.log import initialize_logging

from sma import SustainabilityMeasurementAgent
from sma import Config, SMAObserver

logLevel = os.getenv("LOGLEVEL", "INFO").upper()
# already initialized through the module when importing SMA, so we'll redefine with rich logging
initialize_logging(logLevel, logger_class="rich.logging.RichHandler")
logging.basicConfig(format="%(name)s: %(message)s")
log = logging.getLogger("sma.main")


@click.group()
def cli():
    pass

@cli.command()
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
@click.option('--cli-trigger', is_flag=True, help="Provides a basic manual trigger waiting for user input.")
def run(config_file: str, probe: str, cli_trigger: bool):
    """Run the Sustainability Measurement Agent with a given configuration file.

      You can use e.g. examples/minimal.yaml

      To set log level, use the LOGLEVEL environment variable, e.g.:
      LOGLEVEL=DEBUG python main_fancy.py examples/minimal.yaml
      """

    log.debug("Loading configuration...")
    config = Config.from_file(config_file)

    log.debug("Creating Agent...")
    sma = SustainabilityMeasurementAgent(config, meta=SMASession(name="TestSession"))

    
    log.debug("Loading Modules...")
    log.debug(config.modules)


        # workload_controller = WorkloadController()
        # sma.register_sma_observer(workload_controller)

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




    log.debug("Starting SMA run...")
    # sma.setup(SMASession(
    #     name="TestSession"
    # ))

    def wait_for_trigger():
        input("Press Enter to end the run...")
        return

    with sma.start_session() as session:
        if cli_trigger:
            sma.run(wait_for_trigger)
        else:
            sma.run()
        # sma.teardown() ## automatically called at the end of with block

    log.info("Sustainability Measurement Agent finished.")


def _fetch(cnf: sma.Config, report_location: str, overwrite: bool):
    report = ReportIO.load_from_location(report_location, cnf)
    log.debug("Loaded report")
    sma = SustainabilityMeasurementAgent(cnf)
    log.debug("Created SMA Argent")

    sma.observe_once(report.metadata, overwrite)

@cli.command(short_help="""Attempts to fetches measurements again using the provided configuration file.""")
@click.argument('config_file', type=click.Path(exists=True), )
@click.argument('report_location', type=click.Path(exists=True))
@click.option("--overwrite", is_flag=True, help="Overwrite existing measurements")
def fetch(config_file: str, report_location: str, overwrite: bool):
    """
    fetch config_file report_location

    config_file: path to the configuration file
    report_location: path to the report location
    """
    cnf = Config.from_file(config_file)
    log.debug("Loaded configuration...")

    _fetch(cnf, report_location, overwrite)

@cli.command(short_help="""Attempts to fetches all measurements created with a config again using the provided configuration file.""")
@click.argument('config_file', type=click.Path(exists=True), )
@click.option("--overwrite", is_flag=True, help="Overwrite existing measurements")
def fetchall(config_file: str,  overwrite: bool):
    cnf = Config.from_file(config_file)
    log.debug("Loaded configuration...")
    reports = ReportIO.load_from_config(cnf)

    for report in reports:
        log.info(f"Fetching report {report.run_data.runHash}...")
        _fetch(cnf, report.location, overwrite)


@cli.command(help="Lists all reports for a given configuration file.")
@click.argument('config_file', type=click.Path(exists=True))
def list(config_file: str):
    """
    list
        config_file: path to the configuration file
    """
    cnf = Config.from_file(config_file)
    log.debug("Loaded configuration...")
    reports = ReportIO.load_from_config(cnf)

    for report in reports:
        print(report.run_data.runHash, report.location)

if __name__ == '__main__':
    cli()