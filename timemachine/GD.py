#!/usr/bin/python3
"""
    Grateful Dead Time Machine -- copyright 2021 Steve Eichblatt

    This program is free software: you can redistribute it and/or modify
    it under the terms of the GNU General Public License as published by
    the Free Software Foundation, either version 3 of the License, or
    (at your option) any later version.
    This program is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
    GNU General Public License for more details.

    You should have received a copy of the GNU General Public License
    along with this program.  If not, see <https://www.gnu.org/licenses/>.
"""
import datetime
import logging
import os
import time


# from timemachine.mpv import MPV
try:
    from mpv import MPV
except:
    pass
from tenacity import retry
from tenacity.stop import stop_after_delay, stop_after_attempt
from tenacity.wait import wait_random
from tenacity.retry import retry_if_result
from typing import Callable, Optional

logging.basicConfig(
    format="%(asctime)s.%(msecs)03d %(levelname)s: %(name)s %(message)s",
    level=logging.INFO,
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)
ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
BIN_DIR = os.path.join(os.path.dirname(ROOT_DIR), "bin")


@retry(stop=stop_after_delay(30))
def retry_call(callable: Callable, *args, **kwargs):
    """Retry a call."""
    return callable(*args, **kwargs)


def return_last_value(retry_state):
    """ return the result of the last call made in a tenacity retry """
    return retry_state.outcome.result()


@retry(
    stop=stop_after_attempt(7),
    wait=wait_random(min=1, max=2),
    retry=retry_if_result(lambda x: not x),
    retry_error_callback=return_last_value,
)
def retry_until_true(callable: Callable, *args, **kwargs):
    return callable(*args, **kwargs)


def memoize(f):
    memo = {}

    def helper(x):
        if x not in memo:
            memo[x] = f(x)
        return memo[x]

    return helper


# @memoize
def to_date(datestring):
    return datetime.datetime.fromisoformat(datestring)


def to_year(datestring):
    if type(datestring) == list:  # handle one bad case on 2009.01.10
        datestring = datestring[0]
    return to_date(datestring[:10]).year


def to_decade(datestring):
    if type(datestring) == list:  # handle one bad case on 2009.01.10
        datestring = datestring[0]
    return 10 * divmod(to_date(datestring[:10]).year, 10)[0]
