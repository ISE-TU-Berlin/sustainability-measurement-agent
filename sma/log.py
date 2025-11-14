"""
Purpose: Configures logging for the application.
Functionality: Initializes and configures logging settings based on provided log level and optional log file.
Connection: Used by main.py to set up logging.

Logging configuration for oxn"""
import logging
import socket
import logging.config

HOSTNAME = socket.gethostname()


def initialize_logging(loglevel, logfile=None):
    loglevel = loglevel.upper()

    LOGGING_CONFIG = {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "default": {
                "format": f"[%(asctime)s] {HOSTNAME}/%(levelname)s/%(name)s: %(message)s",
            },
            "plain": {
                "format": "%(message)s",
            },
        },
        "handlers": {
            "console": {
                "class": "logging.StreamHandler",
                "formatter": "default",
            },
        },
        "loggers": {
            "oxn": {
                "handlers": ["console"],
                "level": loglevel,
                "propagate": False,
            },
        },
        "root": {"level": loglevel, "handlers": ["console"]},
    }
    if logfile:
        LOGGING_CONFIG["handlers"]["file"] = {
            "class": "logging.FileHandler",
            "filename": logfile,
            "formatter": "default",
        }
        LOGGING_CONFIG["root"]["handlers"] = ["file"]
        LOGGING_CONFIG["loggers"]["sma"]["handlers"] = ["file"]

    logging.config.dictConfig(LOGGING_CONFIG)
