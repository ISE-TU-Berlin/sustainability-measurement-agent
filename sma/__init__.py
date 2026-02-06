__version__ = "0.2.1" #TODO: need to somehow sync with pyproject.toml...

from sma.config import Config
from sma.sma import SustainabilityMeasurementAgent, SMAObserver
from sma.report import Report, ReportIO
from sma.model import  *
from sma.log import initialize_logging

initialize_logging("ERROR")