import os
from logging import getLogger

from sma import SMAObserver
from sma.prometheus import Prometheus
from .collector import PrometheusEnvironmentCollector
from .io import _serialize_environment

logger = getLogger("sma.PrometheusenvironmentexporterSmaModule")

class PrometheusenvironmentexporterSmaModule(SMAObserver):
    def __init__(self, config: dict):
        self.config = config
        self.collector = PrometheusEnvironmentCollector(Prometheus(self.config["prometheus"]))

    def onReport(self, report=None) -> None:
        if report:
            run = report.run_data
            environment = self.collector.observe_environment(run)
            basepath = report.location
            env_path = os.path.join(basepath, "environment")
            _serialize_environment(environment, env_path)
        else:
            logger.warning("No report available to export environment data from.")



