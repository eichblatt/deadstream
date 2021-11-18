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
import codecs
import csv
import datetime
import difflib
import json
import logging
import math
import os
import random
import re
import requests
import tempfile
import time
from threading import Event, Lock, Thread

from operator import methodcaller
from mpv import MPV
from tenacity import retry
from tenacity.stop import stop_after_delay
from typing import Callable, Optional

import pkg_resources
from timemachine import config

logging.basicConfig(format='%(asctime)s.%(msecs)03d %(levelname)s: %(name)s %(message)s', level=logging.INFO, datefmt='%Y-%m-%d %H:%M:%S')
logger = logging.getLogger(__name__)
ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
BIN_DIR = os.path.join(os.path.dirname(ROOT_DIR), 'bin')

logger.level = logging.DEBUG

@retry(stop=stop_after_delay(30))
def retry_call(callable: Callable, *args, **kwargs):
    """Retry a call."""
    return callable(*args, **kwargs)


def memoize(f):
    memo = {}

    def helper(x):
        if x not in memo:
            memo[x] = f(x)
        return memo[x]
    return helper


@memoize
def to_date(datestring): return datetime.datetime.strptime(datestring, '%Y-%m-%d')


def to_year(datestring):
    if type(datestring) == list:      # handle one bad case on 2009.01.10
        datestring = datestring[0]
    return to_date(datestring[:10]).year


def to_decade(datestring):
    if type(datestring) == list:      # handle one bad case on 2009.01.10
        datestring = datestring[0]
    return 10*divmod(to_date(datestring[:10]).year, 10)[0]


class TapeDownloader():
    """Synchronous Phish Tape Downloader"""
    def __init__(self, url="https://phish.in"):
        self.url = url
        self.api = f"{self.url}/api/v1/shows"
        self.parms = {'sort_attr':'date',
                'sort_dir':'asc','per_page':'300'}
        self.headers = {'Accept':'application/json',
                'Authorization':'Bearer 8003bcd8c378844cfb69aad8b0981309f289e232fb417df560f7192edd295f1d49226ef6883902e59b465991d0869c77'}

    def store_phish_metadata(self, iddir, tapes, period_func=to_decade):
        # Store the tapes json data into files by period
        n_tapes_added = 0
        os.makedirs(iddir, exist_ok=True)
        periods = sorted(list(set([period_func(t['date']) for t in tapes])))


        for period in periods:
            orig_tapes = []
            outpath = os.path.join(iddir, f'ids_{period}.json')
            if os.path.exists(outpath):
                orig_tapes = json.load(open(outpath, 'r'))
            tapes_from_period = [t for t in tapes if period_func(t['date']) == period]
            new_ids = [x['id'] for x in tapes_from_period]
            period_tapes = [x for x in orig_tapes if not x['id'] in new_ids] + tapes_from_period
            n_period_tapes_added = len(period_tapes) - len(orig_tapes)
            n_tapes_added = n_tapes_added + n_period_tapes_added
            if n_period_tapes_added > 0:      # NOTE This condition prevents updates for _everything_ unless there are new tapes.
                logger.info(f"Writing {len(period_tapes)} tapes to {outpath}")
                try:
                    tmpfile = tempfile.mkstemp('.json')[1]
                    json.dump(period_tapes, open(tmpfile, 'w'))
                    os.rename(tmpfile, outpath)
                    logger.debug(f"renamed {tmpfile} to {outpath}")
                except Exception:
                    logger.debug(f"removing {tmpfile}")
                    os.remove(tmpfile)
        logger.info(f'added {n_tapes_added} tapes by period')
        return n_tapes_added
 

    def extract_show_data(self, json_resp):
        shows = []
        fields = ['id','date','duration','incomplete','sbd','venue_name'] 
        for show in json_resp['data']:
            tmp_dict = {k:show[k] for k in fields}
            tmp_dict['venue_location'] = show['venue']['location']
            shows.append(tmp_dict)
        return shows

    def get_all_shows(self, iddir, min_addeddate=None):
        """Get a list of all shows
        Write all tapes to a folder by time period
        """
        current_rows = 0
        n_tapes_added = 0
        n_tapes_total = 0
        tapes = []

        min_date = '1900-01-01'
        max_date = datetime.datetime.now().date().strftime('%Y-%m-%d')

        page_no = 1
        r = self.get_page(page_no)
        json_resp = r.json()
        total = json_resp['total_entries']
        total_pages = json_resp['total_pages']
        logger.debug(f"total rows {total} on {total_pages} pages")
        current_page = json_resp['page']

        shows = self.extract_show_data(json_resp)
        self.store_phish_metadata(iddir,shows)
        #self.store_by_period(iddir, tapes, period_func=to_year)
        while current_page < total_pages:
            r = self.get_page(current_page+1)
            json_resp = r.json()
            shows = self.extract_show_data(json_resp)
            self.store_phish_metadata(iddir,shows)
            current_page = json_resp['page']

    def get_page(self, page_no):
        """Get one page of shows information.
        Returns a list of dictionaries of tape information
        """
        parms = self.parms.copy()
        parms['page'] = page_no
        r = requests.get(self.api, headers=self.headers,params=parms)
        logger.debug(f"url is {r.url}")
        if r.status_code != 200:
            logger.error(f"Error {r.status_code} collecting data")
            raise Exception(
                'Download', 'Error {} collection'.format(r.status_code))
        return r


