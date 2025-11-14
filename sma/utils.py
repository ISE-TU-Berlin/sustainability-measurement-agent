""" 
Purpose: Provides utility functions.
Functionality: Contains helper functions for time conversion, file manipulation, and environment variable management.
Connection: Utility functions are used across different modules for common tasks.

 """

import os
import re
from typing import Callable
from datetime import datetime
from datetime import timezone

import functools

import yaml


SECONDS_MAP = {
    "us": 1 / 10 ** 6,
    "ms": 1 / 10 ** 3,
    "s": 1,
    "m": 60,
    "h": 3600,
    "d": 86400,
}
"""Map used to convert time strings to seconds"""

time_string_format_regex = r"(\d+)(us|ms|s|m|h|d)"


def validate_time_string(time_string):
    """
    Validate that a time string has units

    """
    return bool(re.match(time_string_format_regex, time_string))


def time_string_to_seconds(time_string) -> float:
    """Convert a time string with units to a float"""
    matches = re.findall(time_string_format_regex, time_string)
    seconds = 0.0
    for match in matches:
        value_part = match[0]
        unit_part = match[1]
        seconds += float(value_part) * SECONDS_MAP[unit_part]
    return seconds


def to_milliseconds(seconds):
    """Convert seconds to milliseconds"""
    return seconds * 10 ** 3


def to_microseconds(seconds):
    """Convert seconds to microseconds"""
    return seconds * 10 ** 6


def utc_timestamp() -> float:
    """Get the current time in """
    return datetime.now(timezone.utc).timestamp()


def humanize_utc_timestamp(timestamp):
    """Return a human-readable version of a timestamp"""
    return datetime.utcfromtimestamp(timestamp)


def add_env_variable(compose_file_path, service_name, variable_name, variable_value):
    """Add an environment variable with a given value to a service in a Docker Compose file"""
    with open(compose_file_path, "r") as file:
        compose_dict = yaml.safe_load(file)

    if service_name not in compose_dict["services"]:
        raise ValueError(f"Service {service_name} not found in Docker Compose file")

    if "environment" not in compose_dict["services"][service_name]:
        compose_dict["services"][service_name]["environment"] = []

    environment = compose_dict["services"][service_name]["environment"]
    exists = False
    if isinstance(environment, list):
        for idx, env_var in enumerate(environment):
            if env_var.startswith(f"{variable_name}="):
                environment[idx] = f"{variable_name}={variable_value}"
                exists = True
        if not exists:
            environment.append(f"{variable_name}={variable_value}")
    else:
        raise ValueError("Environment field for %s is not a list" % service_name)

    with open(compose_file_path, "w") as file:
        yaml.safe_dump(compose_dict, file)


def remove_env_variable(compose_file_path, service_name, variable_name, variable_value):
    """Remove an environment variable from a service in a Docker Compose file"""
    with open(compose_file_path, "r") as file:
        compose_dict = yaml.safe_load(file)

    if service_name not in compose_dict["services"]:
        raise ValueError(f"Service {service_name} not found in Docker Compose file")

    if "environment" in compose_dict["services"][service_name]:
        idx = compose_dict["services"][service_name]["environment"].index(f"{variable_name}={variable_value}")
        compose_dict["services"][service_name]["environment"].remove(idx)

    with open(compose_file_path, "w") as file:
        yaml.safe_dump(compose_dict, file)
