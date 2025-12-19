""" 
Purpose: Provides utility functions.
Functionality: Contains helper functions for time conversion, file manipulation, and environment variable management.
Connection: Utility functions are used across different modules for common tasks.

 """

import re
import string
from datetime import datetime
from datetime import timezone

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



def get_identifiers_of_template(template: string.Template) -> list[str]:
        ids = []
        for mo in template.pattern.finditer(template.template):
            named = mo.group('named') or mo.group('braced')
            if named is not None and named not in ids:
                # add a named group only the first time it appears
                ids.append(named)
            elif (named is None
                and mo.group('invalid') is None
                and mo.group('escaped') is None):
                # If all the groups are None, there must be
                # another group we're not expecting
                raise ValueError('Unrecognized named group in pattern',
                    template.pattern)
        return ids
