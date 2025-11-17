__version__ = "0.1.0"

from sma.config import Config
from sma.sma import SustainabilityMeasurementAgent, SMAObserver

from sma.log import initialize_logging

initialize_logging("ERROR")