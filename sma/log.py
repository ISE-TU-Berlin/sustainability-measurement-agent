"""
Licenced under GLPv3, originally developed for the OXN project (https://github.com/nymphbox/oxn).
"""
import logging
import logging.config
import socket

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
            "sma": {
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
