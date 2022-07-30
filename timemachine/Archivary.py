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
import abc
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
import string
import tempfile
import time
from threading import Event, Lock, Thread

from operator import methodcaller
from tenacity import retry
from tenacity.stop import stop_after_delay
from typing import Callable, Optional

import pkg_resources
from timemachine import config

logging.basicConfig(format='%(asctime)s.%(msecs)03d %(levelname)s: %(name)s %(message)s', level=logging.INFO, datefmt='%Y-%m-%d %H:%M:%S')
logger = logging.getLogger(__name__)
ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
BIN_DIR = os.path.join(os.path.dirname(ROOT_DIR), 'bin')


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


def flatten(lis):
    lis_flat = []
    for elem in lis:
        for subelem in elem:
            lis_flat.append(subelem)
    return lis_flat


# @memoize -- not needed with fromisoformat
def to_date(datestring): return datetime.datetime.fromisoformat(datestring)


def to_year(datestring):
    if type(datestring) == list:      # handle one bad case on 2009.01.10
        datestring = datestring[0]
    return to_date(datestring[:10]).year


def to_decade(datestring):
    if type(datestring) == list:      # handle one bad case on 2009.01.10
        datestring = datestring[0]
    return 10 * divmod(to_date(datestring[:10]).year, 10)[0]


class BaseTapeDownloader(abc.ABC):
    """Abstract base class for a tape downloader.

    Use one of the subclasses: IATapeDownloader or PhishinTapeDownloader.
    """

    def store_metadata(self, iddir, tapes, period_func=to_decade):
        # Store the tapes json data into files by period
        n_tapes_added = 0
        os.makedirs(iddir, exist_ok=True)
        periods = sorted(list(set([period_func(t['date']) for t in tapes])))
        logger.debug(f"storing metadata {periods}")

        for period in periods:
            orig_tapes = []
            outpath = os.path.join(iddir, f'ids_{period}.json')
            if os.path.exists(outpath):
                orig_tapes = json.load(open(outpath, 'r'))
            tapes_from_period = [t for t in tapes if period_func(t['date']) == period]
            new_ids = [x['identifier'] for x in tapes_from_period]
            period_tapes = [x for x in orig_tapes if not x['identifier'] in new_ids] + tapes_from_period
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

    @abc.abstractmethod
    def get_all_tapes(self, iddir, min_addeddate=None, date_range=None):
        """Get a list of all tapes."""
        pass


def remove_none(lis):
    return [a for a in lis if a is not None]


class Archivary():
    """ A collection of Archive objects """

    def __init__(self, dbpath=os.path.join(ROOT_DIR, 'metadata'), reload_ids=False, with_latest=False, collection_list=['GratefulDead'], date_range=None):
        # if 'rElOaD' in collection_list:
        #     self.reload_ids = True
        #     collection_list.remove('rElOaD')
        self.collection_list = collection_list
        self.archives = []
        phishin_archive = None
        ia_archive = None
        ia_collections = [x for x in self.collection_list if x != 'Phish']
        if 'Phish' in self.collection_list:
            try:
                phishin_archive = PhishinArchive(dbpath=dbpath, reload_ids=reload_ids, with_latest=with_latest)
            except Exception:
                pass
        if len(ia_collections) > 0:
            ia_archive = GDArchive(dbpath=dbpath, reload_ids=reload_ids, with_latest=with_latest, collection_list=ia_collections, date_range=date_range)
        self.archives = remove_none([ia_archive, phishin_archive])
        self.tape_dates = self.get_tape_dates()
        self.dates = sorted(self.tape_dates.keys())

    def year_list(self):
        t = [a.year_list() for a in self.archives]
        yl = sorted(set([item for sublist in t for item in sublist]))
        return yl

    def best_tape(self, date, resort=True):
        if date not in self.dates:
            logger.info(f"No Tape for date {date}")
            return None
        # if resort:
        #    bt = remove_none([a.best_tape(date, resort) for a in self.archives])
        # else:
        bt = self.tape_dates[date]
        return bt[0]

    def tape_at_time(self, then_time, default_start):
        tat = remove_none([a.tape_at_time(then_time, default_start) for a in self.archives])
        if len(tat) == 0:
            return None
        return tat[0]

    def tape_at_date(self, dt, which_tape=0):
        pass

    def tape_start_time(self, dt, default_start=datetime.time(19, 0)):
        tst = remove_none([a.tape_start_time(dt, default_start) for a in self.archives])
        if len(tst) == 0:
            return None
        return tst[0]

    def sort_across_collection(self, tapes):
        cdict = {}
        for c in self.collection_list:
            cdict[c] = []
        for t in tapes:
            for c in self.collection_list:
                if c in t.collection:
                    cdict[c].append(t)

        result = []
        max_n_collection = max([len(cdict[k]) for k in cdict])
        for i in range(max_n_collection):
            for k in cdict.keys():
                if len(cdict[k]) > i:
                    result.append(cdict[k][i])
        return result

    def get_tape_dates(self, sort_across=True):   # Archivary
        td = self.archives[0].tape_dates
        for a in self.archives[1:]:
            for date, tapes in a.tape_dates.items():
                if date in td.keys():
                    for t in tapes:
                        td[date].append(t)
                else:
                    td[date] = tapes
        if (not sort_across) or (len(self.archives) == 1):
            return td
        td = {date: self.sort_across_collection(tapes) for date, tapes in td.items()}
        return td

    # @memoize  # -- failed...maybe try this manually?
    def resort_tape_date(self, date):
        if date not in self.dates:
            logger.info(f"No Tape for date {date}")
            return None
        bt = [remove_none(a.resort_tape_date(date)) for a in self.archives]
        bt = flatten(bt)
        bt = list(dict.fromkeys(bt))
        bt = self.sort_across_collection(bt)
        return bt

    def load_archive(self, reload_ids, with_latest):
        logger.info("Loading Archivary")
        for a in self.archives:
            logger.info(f"Archivary loading {a.archive_type}")
            a.load_archive(reload_ids=reload_ids, with_latest=with_latest)
        logger.info(f"Archivary now contains {len(self.tape_dates)} tapes")

    def year_artists(self, start_year, end_year=None):
        for a in self.archives:
            tmp = a.year_artists(start_year, end_year)
            if tmp:
                return tmp


class BaseArchive(abc.ABC):
    """Abstract base class for an Archive.

    Use one of the subclasses: GDArchive or PhishinArchive
    Parameters:

        dbpath: Path to filesystem location where data are stored
        url: URL for the internet archive
        reload_ids: If True, force re-download of tape data
        with_latest: If True, query archive for recently added tapes, and append them.
        collection_list: A list of collections from archive.org
    """

    def __init__(self, url, dbpath=os.path.join(ROOT_DIR, 'metadata'), reload_ids=False, with_latest=False, collection_list=['GratefulDead'], date_range=None):
        self.archive_type = 'Base Archive'
        self.url = url
        self.dbpath = dbpath
        self.collection_list = collection_list
        self.tapes = []
        self.date_range = date_range
        self.collection_list = collection_list if isinstance(collection_list, (list, tuple)) else [collection_list]
        if len(self.collection_list) == 1:
            self.idpath = [os.path.join(self.dbpath, F'{collection_list[0]}_ids')]
            if self.collection_list[0] == 'Phish':
                self.idpath = self.idpath[0]
                self.downloader = PhishinTapeDownloader(url, collection_list=collection_list[0])
            else:
                self.downloader = IATapeDownloader(url, collection_list=collection_list[0])
        else:
            self.idpath = [os.path.join(self.dbpath, f'{x}_ids') for x in self.collection_list]
            # self.idpath = os.path.join(self.dbpath, 'etree_ids')
            self.downloader = IATapeDownloader(url)
        self.set_data = None

    def __str__(self):
        return self.__repr__()

    def __repr__(self):
        retstr = F"{self.collection_list} Archive with {len(self.tapes)} tapes on {len(self.dates)} dates from {self.dates[0]} to {self.dates[-1]} "
        return retstr

    def year_list(self):
        return sorted(set([to_date(x).year for x in self.dates]))

    def tape_at_date(self, dt, which_tape=0):
        then_date = dt.date()
        then = then_date.strftime('%Y-%m-%d')
        try:
            tape = self.tape_dates[then]
        except KeyError:
            return None
        return tape[which_tape]

    def tape_at_time(self, dt, default_start=datetime.time(19, 0)):
        tape = self.tape_at_date(dt)
        if not tape:
            return None
        tape_start = self.tape_start_time(dt, default_start)
        tape_end = tape_start + datetime.timedelta(hours=3)
        if (dt > tape_start) and dt < tape_end:
            return self.best_tape(dt.date())
        else:
            return None

    def tape_start_time(self, dt, default_start=datetime.time(19, 0)):
        tape = self.tape_at_date(dt)
        if not tape:
            return None
        tape_start_time = tape.set_data['start_time'] if tape.set_data else None
        if tape_start_time is None:
            tape_start_time = default_start
        tape_start = datetime.datetime.combine(dt.date(), tape_start_time)  # date + time
        return tape_start

    def get_tape_dates(self, sort_within=True):   # BaseArchive
        tape_dates = {}
        for tape in self.tapes:
            k = tape.date
            if k not in tape_dates.keys():
                tape_dates[k] = [tape]
            else:
                tape_dates[k].append(tape)
        # Now that we have all tape for a date, put them in the right order
        if not sort_within:
            self.tape_dates = tape_dates
        else:
            self.tape_dates = {}
            for k, v in tape_dates.items():
                self.tape_dates[k] = sorted(v, key=methodcaller('compute_score'), reverse=True)

        return self.tape_dates

    @abc.abstractmethod
    def load_archive(self, reload_ids, with_latest):
        pass

    @abc.abstractmethod
    def best_tape(self, date, resort=True):
        pass

    @abc.abstractmethod
    def year_artists(self, year):
        pass


class BaseTape(abc.ABC):
    def __init__(self, dbpath, raw_json, set_data=None):
        self.dbpath = dbpath

        """ NOTE This should be part of the player, not part of the tape or track, as it is now """
        if config.optd['PLAY_LOSSLESS']:
            self._playable_formats = ['Flac', 'Shorten', 'Ogg Vorbis', 'VBR MP3', 'MP3']
        else:
            self._playable_formats = ['Ogg Vorbis', 'VBR MP3', 'MP3']
        self._lossy_formats = ['Ogg Vorbis', 'VBR MP3', 'MP3']
        """ ----------------------------------------------------------------------------------- """

        self._breaks_added = False
        self.meta_loaded = False
        self.format = None
        self.collection = None
        self.artist = None
        self.meta_path = None
        self._tracks = []
        self._remove_from_archive = False

    def __str__(self):
        return self.__repr__()

    def __repr__(self):
        tag = "SBD" if self.stream_only() else "aud"
        retstr = '{} - {} - {:5.2f} - {}\n'.format(self.date, tag, self.compute_score(), self.identifier)
        return retstr

    def contains_sound(self):
        return len(list(set(self._playable_formats) & set(self.format))) > 0

    def tracklist(self):
        for i, t in enumerate(self._tracks):
            logger.info(i)

    def tracks(self):
        self.get_metadata()
        return self._tracks

    def track(self, n):
        if not self.meta_loaded:
            self.get_metadata()
        return self._tracks[n - 1]

    @abc.abstractmethod
    def stream_only(self):
        pass

    @abc.abstractmethod
    def compute_score(self):
        pass

    @abc.abstractmethod
    def venue(self, tracknum=0):
        pass


class BaseTrack:
    """ A Base track from a tape """

    def __init__(self, tdict, parent_id, break_track=False):
        self.parent_id = parent_id

    def __str__(self):
        return self.__repr__()

    def __repr__(self):
        retstr = 'track {}. {}'.format(self.track, self.title)
        return retstr

    @abc.abstractmethod
    def add_file(self, tdict, break_track=False):
        pass


class PhishinTapeDownloader(BaseTapeDownloader):
    """Synchronous Phishin Tape Downloader"""

    def __init__(self, url="https://phish.in", collection_list="Phish"):
        self.url = url
        self.api = f"{self.url}/api/v1/shows"
        try:
            self.apikey = open(os.path.join(os.getenv('HOME'), '.phishinkey'), 'r').read().rstrip()
        except Exception:
            self.apikey = None
        self.parms = {'sort_attr': 'date',
                      'sort_dir': 'desc', 'per_page': '300'}
        self.headers = {'Accept': 'application/json',
                        'Authorization': f'Bearer {self.apikey}'}

    def extract_show_data(self, json_resp):
        shows = []
        fields = ['id', 'date', 'duration', 'incomplete', 'sbd', 'venue_name']
        for show in json_resp['data']:
            tmp_dict = {k: show[k] for k in fields}
            tmp_dict['identifier'] = tmp_dict['id']
            tmp_dict['venue_location'] = show['venue']['location']
            shows.append(tmp_dict)
        return shows

    def get_all_tapes(self, iddir, min_addeddate=None, date_range=None):
        """Get a list of all Phish.in shows
        Write all tapes to a folder by time period
        """
        per_page = self.parms['per_page']

        # No need to update if we already have a show from today.
        if min_addeddate is not None:
            if to_date(min_addeddate) == datetime.datetime.today().date():
                return
            per_page = 50
        page_no = 1
        r = self.get_page(page_no, per_page)
        json_resp = r.json()
        total = json_resp['total_entries']
        total_pages = json_resp['total_pages']
        logger.debug(f"total rows {total} on {total_pages} pages")
        current_page = json_resp['page']

        shows = self.extract_show_data(json_resp)
        self.store_metadata(iddir, shows)

        # If min_addeddate is not None, then check that the earliest update on this page is after the latest show we already had.
        while (current_page < total_pages) if min_addeddate is None else (shows[-1]['date'] > min_addeddate):
            r = self.get_page(current_page + 1, per_page)
            json_resp = r.json()
            shows = self.extract_show_data(json_resp)
            self.store_metadata(iddir, shows)
            current_page = json_resp['page']
        return total

    def get_page(self, page_no, per_page=None):
        """Get one page of shows information.
        Returns a list of dictionaries of tape information
        """
        parms = self.parms.copy()
        parms['page'] = page_no
        if isinstance(per_page, int):
            parms['per_page'] = per_page
        r = requests.get(self.api, headers=self.headers, params=parms)
        logger.debug(f"url is {r.url}")
        if r.status_code != 200:
            logger.error(f"Error {r.status_code} collecting data")
            raise Exception(
                'Download', 'Error {} collection'.format(r.status_code))
        return r


class IATapeDownloader(BaseTapeDownloader):
    """Synchronous Grateful Dead Tape Downloader"""

    def __init__(self, url="https://archive.org", collection_list="etree"):
        self.url = url
        self.collection_list = collection_list
        self.api = f"{self.url}/services/search/v1/scrape"
        fields = ["identifier", "date", "avg_rating", "num_reviews",
                  "num_favorites", "stars", "downloads", "files_count",
                  "format", "collection", "source", "subject", "type", "addeddate"]
        sorts = ["date asc", "avg_rating desc",
                 "num_favorites desc", "downloads desc"]
        self.parms = {'debug': 'false',
                      'xvar': 'production',
                      'total_only': 'false',
                      'count': '10000',
                      'sorts': ",".join(sorts),
                      'fields': ",".join(fields)}

    def save_all_collection_names(self):
        """
             get a list of all collection names within archive.org's etree collection.
             This should leverage the _get_piece function
        """
        current_rows = 0
        parms = {'debug': 'false', 'xvar': 'production', 'total_only': 'false', 'count': '10000',
                 'fields': 'identifier, item_count,collection_size,downloads,num_favorites',
                 'q': 'collection:etree AND mediatype:collection'}
        r = requests.get(self.api, params=parms)
        logger.debug(f"url is {r.url}")
        if r.status_code != 200:
            logger.error(f"Error {r.status_code} collecting data")
            raise Exception(
                'Download', f'Error {r.status_code} collection')
            # ChunkedEncodingError:
        j = r.json()
        total = j['total']
        current_rows += j['count']
        if current_rows < total:
            logger.warning(f"Not all collection names were downloaded. Total:{total} downloaded:{current_rows}")
            # if/when we see this, we need to loop over downloads.

        collection_path = os.path.join(os.getenv('HOME'), '.etree_collection_names.json')
        try:
            tmpfile = tempfile.mkstemp('.json')[1]
            json.dump(j, open(tmpfile, 'w'))
            os.rename(tmpfile, collection_path)
        except Exception:
            logger.debug(f"removing {tmpfile}")
            os.remove(tmpfile)
        logger.info(f'saved {current_rows} collection names to {collection_path}')

    def get_all_tapes(self, iddir, min_addeddate=None, date_range=None, collection=None):
        """Get a list of all tapes.  Write all tapes to a folder by time period
        Args:
            iddir (str) : path where id's metadata will be written
            min_addeddate (str, optional): Only get data which was added after this date. Default None
            date_range ([list of 2 ints or strings]): start and end year. Only tapes within this range will be retrieved
        Returns:
            int : Number of tapes retrieved.
        """
        current_rows = 0
        n_tapes_added = 0
        n_tapes_total = 0
        tapes = []
        yearly_collections = ['etree', 'georgeblood']  # should this be in config?
        collection = collection if collection is not None else os.path.basename(iddir).replace('_ids', '')

        if not date_range:
            min_date = '1880-01-01'
            max_date = datetime.datetime.now().date().strftime('%Y-%m-%d')
        elif len(date_range) == 2:
            min_date = f'{date_range[0]}-01-01'
            max_date = f'{date_range[1]}-12-31'
        elif len(date_range) > 2:
            result_list = [self.get_all_tapes(iddir, min_addeddate, x) for x in date_range]
            return sum(result_list)
        elif len(date_range) == 1:
            min_date = f'{date_range[0]}-01-01'
            max_date = f'{date_range[0]}-12-31'

        r = self._get_piece(min_date, max_date, min_addeddate, collection=collection)
        j = r.json()
        total = j['total']
        logger.debug(f"total rows {total}")
        current_rows += j['count']
        tapes = j['items']

        period_func = to_year if os.path.basename(iddir).replace('_ids', '') in yearly_collections else to_decade
        logger.debug("Loading tapes")
        n_tapes_added = self.store_metadata(iddir, tapes, period_func=period_func)
        n_tapes_total = n_tapes_added

        while (current_rows < 1.25 * total) and n_tapes_added > 0:
            logger.debug("in while loop")
            min_date_field = tapes[-1]['date']
            min_date = min_date_field[:10]  # Should we subtract some days for overlap?
            r = self._get_piece(min_date, max_date, min_addeddate, collection=collection)
            j = r.json()
            current_rows += j['count']
            tapes = j['items']
            n_tapes_added = self.store_metadata(iddir, tapes, period_func=period_func)
            n_tapes_total = n_tapes_total + n_tapes_added
        return n_tapes_total

    def get_tapes(self, years):
        """Get a list of tapes.
            years: List of years to download tapes for
        Returns a list dictionaries of tape information
        """
        tapes = []
        for year in years:
            year_tapes = self._get_tapes_year(year)
            tapes.extend(year_tapes)
        return tapes

    def _get_tapes_year(self, year):
        """Get tape information for a year.

        Parameters:

            year: The year to download tape information for

        Returns a list of dictionaries of tape information
        """
        current_rows = 0
        tapes = []
        r = self._get_chunk(year)
        j = r.json()
        total = j['total']
        logger.debug(f"total rows {total}")
        current_rows += j['count']
        tapes = j['items']
        while current_rows < total:
            cursor = j['cursor']
            r = self._get_chunk(year, cursor)
            j = r.json()
            cursor = j['cursor']
            current_rows += j['count']
            tapes.extend(j['items'])
        return tapes

    def _get_piece(self, min_date, max_date, min_addeddate=None, collection=None):
        """Get one chunk of a year's tape information.
        Returns a list of dictionaries of tape information
        """
        parms = self.parms.copy()
        n_tries = 0
        need_retry = False
        collection = self.collection_list if collection is None else collection
        if min_addeddate is None:
            query = F'collection:{collection} AND date:[{min_date} TO {max_date}]'
        else:
            # max_addeddate = datetime.datetime.now().strftime('%Y-%m-%dT%H:%M:%SZ')
            query = F'collection:{collection} AND date:[{min_date} TO {max_date}] AND addeddate:[{min_addeddate} TO {max_date}]'
        parms['q'] = query
        try:
            r = requests.get(self.api, params=parms)
        except Exception as e:
            logger.exception(e)
            need_retry = True
        while need_retry or r.status_code == 502 and n_tries < 5:
            n_tries = n_tries + 1
            logger.warning(f"trying to pull data for {n_tries} time")
            if n_tries > 4:
                need_retry = False
            time.sleep(5 * n_tries)
            try:
                r = requests.get(self.api, params=parms)
            except Exception as e:
                logger.exception(e)

        logger.debug(f"url is {r.url}")
        if r.status_code != 200:
            logger.error(f"Error {r.status_code} collecting data")
            raise Exception(
                'Download', f'Error {r.status_code} collection')
            # ChunkedEncodingError:
        return r

    def _get_chunk(self, year, cursor=None):
        """Get one chunk of a year's tape information.

        Parameters:

            year: The year to download tape information for
            cursor: Used to download a segment of a year of tapes

        Returns a list of dictionaries of tape information
        """
        parms = self.parms.copy()
        if cursor is not None:
            parms['cursor'] = cursor
        query = F'collection:{self.collection_list} AND year:{year}'
        parms['q'] = query
        r = requests.get(self.api, params=parms)
        logger.debug(f"url is {r.url}")
        if r.status_code != 200:
            logger.error(f"Error {r.status_code} collecting data")
            raise Exception(
                'Download', f'Error {r.status_code} collection')
        return r


class PhishinArchive(BaseArchive):
    def __init__(self, url='https://phish.in', dbpath=os.path.join(ROOT_DIR, 'metadata'), reload_ids=False, with_latest=False, collection_list=['Phish']):
        """Create a new PhishinArchive.

        Parameters:

          dbpath: Path to filesystem location where data are stored
          url: URL for the phish data
          reload_ids: If True, force re-download of tape data
          with_latest: If True, query archive for recently added tapes, and append them.
          collection_list: Phish
        """
        super().__init__(url, dbpath, reload_ids, with_latest, collection_list)
        self.load_archive(reload_ids, with_latest)
        self.archive_type = 'Phishin Archive'

    def load_archive(self, reload_ids=False, with_latest=False):
        self.tapes = self.load_tapes(reload_ids, with_latest)
        self.tape_dates = self.get_tape_dates(sort_within=False)
        self.dates = sorted(self.tape_dates.keys())

    def load_tapes(self, reload_ids=False, with_latest=False):
        """ Load the tapes, then add anything which has been added since the tapes were saved """
        n_tapes = 0

        if reload_ids or not os.path.exists(self.idpath):
            os.system(f'rm -rf {self.idpath}')
            logger.info('Loading Tapes from Phish.in. This will take a few minutes')
            n_tapes = self.downloader.get_all_tapes(self.idpath)  # this will write chunks to folder
            logger.info(f'Loaded {n_tapes} tapes from archive')

        if with_latest:
            max_showdate = max(self.tape_dates.keys())
            logger.debug(f'Refreshing Tapes\nmax showdate {max_showdate}')
            n_tapes = self.downloader.get_all_tapes(self.idpath, max_showdate)
            logger.info(f'Loaded {n_tapes} new tapes from archive')
        else:
            if len(self.tapes) > 0:  # The tapes have already been written, and nothing was added
                return self.tapes
        loaded_tapes, _ = self.load_current_tapes()
        self.tapes = [PhishinTape(self.dbpath, tape, self.set_data) for tape in loaded_tapes]
        return self.tapes

    def load_current_tapes(self, reload_ids=False):   # Phishin
        logger.debug("Loading current tapes")
        tapes = []
        if reload_ids or not os.path.exists(self.idpath):
            os.system(f'rm -rf {self.idpath}')
            logger.info(f'Loading Tapes from the Archive...this will take a few minutes. Writing to {self.idpath}')
            n_tapes = self.downloader.get_all_tapes(self.idpath)  # this will write chunks to folder
            logger.info(f'Loaded {n_tapes} tapes from archive')
        # loop over chunks -- get max addeddate before filtering collections.
        if os.path.isdir(self.idpath):
            for filename in os.listdir(self.idpath):
                if filename.endswith('.json'):
                    chunk = json.load(open(os.path.join(self.idpath, filename), 'r'))
                    # chunk = [t for t in chunk if any(x in self.collection_list for x in t['collection'])]
                    tapes.extend(chunk)
        else:
            tapes = json.load(open(self.idpath, 'r'))
            # addeddates.append(max([x['addeddate'] for x in tapes]))
            # tapes = [t for t in tapes if any(x in self.collection_list for x in t['collection'])]
        max_addeddate = None
        return (tapes, max_addeddate)

    def resort_tape_date(self, date):
        """ Phishin version of this method """
        if isinstance(date, datetime.date):
            date = date.strftime('%Y-%m-%d')
        if date not in self.dates:
            return [None]
        tapes = self.tape_dates[date]
        return tapes

    def best_tape(self, date, resort=True):
        """ Phishin version of this method """
        if isinstance(date, datetime.date):
            date = date.strftime('%Y-%m-%d')
        if date not in self.dates:
            return None
        if resort:
            tapes = self.resort_tape_date(date)
        else:
            tapes = self.tape_dates[date]
        return tapes[0]

    def year_artists(self, year, other_year=None):
        id_dict = {1983: 'Phish'}
        return id_dict


class PhishinTape(BaseTape):
    """ A Phishin tape  """

    def __init__(self, dbpath, raw_json, set_data):
        super().__init__(dbpath, raw_json, set_data)
        attribs = ['date', 'id', 'duration', 'incomplete', 'sbd', 'venue_name', 'venue_location']
        for k, v in raw_json.items():
            if k in attribs:
                setattr(self, k, v)
        self.identifier = F"phishin_{self.id}"
        self.set_data = None
        self.collection = ['Phish']
        self.artist = 'Phish'
        delattr(self, 'id')
        date = to_date(self.date).date()
        self.meta_path = os.path.join(self.dbpath, str(date.year), str(date.month), self.identifier + '.json')
        self.url_metadata = 'https://phish.in/api/v1/shows/' + self.date
        try:
            self.apikey = open(os.path.join(os.getenv('HOME'), '.phishinkey'), 'r').read().rstrip()
        except Exception:
            self.apikey = None
        self.parms = {'sort_attr': 'date',
                      'sort_dir': 'asc', 'per_page': '300'}
        self.headers = {'Accept': 'application/json',
                        'Authorization': f'Bearer {self.apikey}'}

    def stream_only(self):
        return False

    def compute_score(self):
        return 5

    def venue(self, tracknum=0):
        """return the venue, city, state"""
        return F"{self.venue_name},{self.venue_location}"

    def get_metadata(self, only_if_cached=False):
        if self.meta_loaded:
            return
        if only_if_cached and not os.path.exists(self.meta_path):
            return
        self._tracks = []
        try:     # I used to check if file exists, but it may also be corrupt, so this is safer.
            page_meta = json.load(open(self.meta_path, 'r'))
        except Exception:
            parms = self.parms.copy()
            parms['page'] = 1
            r = requests.get(self.url_metadata, headers=self.headers)
            logger.info(f"url is {r.url}")
            if r.status_code != 200:
                logger.warning(f"error pulling data for {self.identifier}")
                raise Exception('Download', f'Error {r.status_code} url {self.url_metadata}')
            try:
                page_meta = r.json()
            except ValueError:
                logger.warning(f"Json Error {r.url}")
                return None
            except Exception:
                logger.warning("Error getting metadata (json?)")
                return None

        if page_meta['total_pages'] > 1:
            logger.warning(F"More than 1 page in metadata for show on {page_meta['data']['date']}. There are {page_meta['total_pages']} pages")

        data = page_meta['data']
        for itrack, track_data in enumerate(data['tracks']):
            set_name = track_data['set']
            if itrack == 0:
                current_set = set_name
            if set_name != current_set:
                self._tracks.append(PhishinTrack(track_data, self.identifier, break_track=True))
                current_set = set_name
            self._tracks.append(PhishinTrack(track_data, self.identifier))

        os.makedirs(os.path.dirname(self.meta_path), exist_ok=True)
        json.dump(page_meta, open(self.meta_path, 'w'))
        self.meta_loaded = True
        # return page_meta
        for track in self._tracks:
            track.title = re.sub(r'gd\d{2}(?:\d{2})?-\d{2}-\d{2}[ ]*([td]\d*)*', '', track.title).strip()
            track.title = re.sub(r'(.flac)|(.mp3)|(.ogg)$', '', track.title).strip()
        return


class PhishinTrack(BaseTrack):
    """ A track from a Phishin recording """

    def __init__(self, tdict, parent_id, break_track=False):
        super().__init__(tdict, parent_id, break_track)
        attribs = ['set', 'venue_name', 'venue_location', 'title', 'position', 'duration', 'mp3', 'updated_at']
        for k, v in tdict.items():
            if k in attribs:
                setattr(self, k, v)
        self.format = 'MP3'
        self.track = self.position
        self.files = []
        self.add_file(tdict, break_track)

    def add_file(self, tdict, break_track=False):
        d = {}
        d['source'] = 'phishin'
        if not break_track:
            d['name'] = self.title
            d['format'] = 'MP3'
            d['size'] = self.duration
            d['path'] = ''
            d['url'] = self.mp3
        else:
            logger.info("adding break track in Phishin")
            d['name'] = ''
            if self.set == 'E':
                d['path'] = pkg_resources.resource_filename('timemachine.metadata', 'silence0.ogg')
                self.title = 'Encore Break'
            else:
                d['path'] = pkg_resources.resource_filename('timemachine.metadata', 'silence600.ogg')
                logger.info(f"path is {d['path']}")
                self.title = 'Set Break'
            d['format'] = 'Ogg Vorbis'
            # d['url'] = 'file://'+os.path.join(d['path'], d['name'])
            d['url'] = f'file://{d["path"]}'
        self.files.append(d)


class GDArchive(BaseArchive):
    """ The Grateful Dead Collection on Archive.org """

    def __init__(self, url='https://archive.org', dbpath=os.path.join(ROOT_DIR, 'metadata'), reload_ids=False, with_latest=False, collection_list=['GratefulDead'], date_range=None):
        """Create a new GDArchive.

        Parameters:

          dbpath: Path to filesystem location where data are stored
          url: URL for the internet archive
          reload_ids: If True, force re-download of tape data
          with_latest: If True, query archive for recently added tapes, and append them.
          collection_list: A list of collections from archive.org
        """
        super().__init__(url, dbpath, reload_ids, with_latest, collection_list, date_range)
        self.archive_type = 'Internet Archive'
        self.set_data = GDSet(self.collection_list)
        self.date_range = date_range
        self.load_archive(reload_ids, with_latest)

    def load_archive(self, reload_ids=False, with_latest=False):
        self.tapes = self.load_tapes(reload_ids, with_latest)
        sort_within = True
        if 'georgeblood' in self.collection_list:
            sort_within = False
        self.tape_dates = self.get_tape_dates(sort_within=sort_within)
        self.dates = sorted(self.tape_dates.keys())

    def resort_tape_date(self, date):        # IA
        """  archive.org version of this method """
        if isinstance(date, datetime.date):
            date = date.strftime('%Y-%m-%d')
        if date not in self.dates:
            return [None]
        tapes = self.tape_dates[date]
        _ = [t.tracks() for t in tapes[:3]]   # load first 3 tapes' tracks. Decrease score of those without titles.
        tapes = sorted(tapes, key=methodcaller('compute_score'), reverse=True)
        tapes = [t for t in tapes if not t._remove_from_archive]  # eliminate missing tapes
        return tapes

    def best_tape(self, date, resort=True):        # IA
        """  archive.org version of this method """
        if isinstance(date, datetime.date):
            date = date.strftime('%Y-%m-%d')
        if date not in self.dates:
            return None

        if resort:
            tapes = self.resort_tape_date(date)
        else:
            tapes = self.tape_dates[date]
        return tapes[0]

    def load_current_tapes(self, reload_ids=False, meta_path=None):   # IA
        """ Load current tapes or download them from archive.org if they are not already loaded """
        logger.debug("Loading current tapes")
        meta_path = self.idpath if meta_path is None else meta_path
        tapes = []
        addeddates = []
        collection_path = os.path.join(os.getenv('HOME'), '.etree_collection_names.json')
        yearly_collections = ['etree', 'georgeblood']  # should this be in config?

        if not self.date_range:
            self.date_range = [1880, datetime.datetime.now().year]
        elif isinstance(self.date_range, int):
            self.date_range = [self.date_range]
        years_to_load = range(min(self.date_range), max(self.date_range) + 1) if len(self.date_range) <= 2 else self.date_range

        meta_files = os.listdir(meta_path) if os.path.exists(meta_path) else []
        meta_files = [x for x in meta_files if x.endswith('.json')]
        meta_files = [x for x in meta_files if int(os.path.splitext(x)[0].split('_')[-1]) in years_to_load]

        if reload_ids or len(meta_files) == 0:
            if reload_ids:
                os.system(f'rm -rf {meta_path}')
            logger.info('Loading Tapes from the Archive...this will take a few minutes')
            n_tapes = self.downloader.get_all_tapes(meta_path, date_range=self.date_range)  # this will write chunks to folder
            logger.info(f'Loaded {n_tapes} tapes from archive')

        elif (len(meta_files) < len(years_to_load)) and os.path.basename(meta_path).replace('_ids', '') in yearly_collections:
            for year in years_to_load:
                if len([x for x in meta_files if f'{year}' in x]) == 0:
                    n_tapes = self.downloader.get_all_tapes(meta_path, date_range=[year])

        if reload_ids or not os.path.exists(collection_path) and meta_path.endswith('etree_ids'):
            logger.info('Loading collection names from archive.org')
            try:
                self.downloader.save_all_collection_names()
            except Exception as e:
                logger.warning(f'Error saving all collection_names {e}')
        # loop over chunks -- get max addeddate before filtering collections.
        if os.path.isdir(meta_path):
            for filename in os.listdir(meta_path):
                if filename.endswith('.json'):
                    time_period = int(filename.split('_')[-1].replace('.json', ''))
                    # if min_year <= time_period <= max_year:
                    if time_period in years_to_load:
                        logger.info(f"loading time period {time_period}")
                        chunk = json.load(open(os.path.join(meta_path, filename), 'r'))
                        addeddates.append(max([x['addeddate'] for x in chunk]))
                        chunk = [t for t in chunk if any(x in self.collection_list for x in t['collection'])]
                        tapes.extend(chunk)
        else:
            tapes = json.load(open(meta_path, 'r'))
            addeddates.append(max([x['addeddate'] for x in tapes]))
            tapes = [t for t in tapes if any(x in self.collection_list for x in t['collection'])]
        max_addeddate = max(addeddates) if len(tapes) > 0 else None
        return (tapes, max_addeddate)

    def load_tapes(self, reload_ids=False, with_latest=False):    # IA
        """ Load the tapes, then add anything which has been added since the tapes were saved """
        logger.info('begin loading tapes')
        all_tapes_count = 0
        all_loaded_tapes = []
        for meta_path in self.idpath:
            n_tapes = 0
            loaded_tapes, max_addeddate = self.load_current_tapes(reload_ids, meta_path=meta_path)
            if len(loaded_tapes) == 0:  # e.g. in case of an invalid collection
                continue
            logger.debug(f'max addeddate {max_addeddate}')
            if with_latest:
                min_download_addeddate = (datetime.datetime.fromisoformat(max_addeddate[:-1])) - datetime.timedelta(hours=1)
                min_download_addeddate = datetime.datetime.strftime(min_download_addeddate, '%Y-%m-%dT%H:%M:%SZ')
                logger.debug(f'Refreshing Tapes\nmax addeddate {max_addeddate}\nmin_download_addeddate {min_download_addeddate}')
                n_tapes = self.downloader.get_all_tapes(meta_path, min_download_addeddate)
                logger.info(f'Loaded {n_tapes} new tapes from archive')
            if n_tapes > 0:
                logger.info(f'Adding {n_tapes} tapes')
                loaded_tapes, _ = self.load_current_tapes(meta_path=meta_path)
            all_loaded_tapes.extend(loaded_tapes)
            all_tapes_count = all_tapes_count + n_tapes
        if (all_tapes_count == 0) and (len(self.tapes) > 0):  # The tapes have already been written, and nothing was added
            return self.tapes
        self.tapes = [GDTape(self.dbpath, tape, self.set_data) for tape in all_loaded_tapes]
        return self.tapes

    def year_artists(self, year, other_year=None):
        """ NOTE: should use some caching here """
        id_dict = {}
        other_year = other_year if other_year else year
        start_year, end_year = sorted([year, other_year])
        year_tapes = {k: v for k, v in self.tape_dates.items() if start_year <= int(k[:4]) <= end_year}
        logger.info(f"Select artists between {start_year} and {end_year}. There are {len(year_tapes)} tapes")

        tapes = [item for sublist in year_tapes.values() for item in sublist]
        kvlist = [(' '.join(x.identifier.split('_')[2].split('-')[:2]), x) for x in tapes]
        for kv in kvlist:
            id_dict.setdefault(kv[0], []).append(kv[1])
        return id_dict


class GDTape(BaseTape):
    """ A Grateful Dead Identifier Item -- does not contain tracks """

    def __init__(self, dbpath, raw_json, set_data):
        super().__init__(dbpath, raw_json, set_data)
        self.meta_loaded = False
        self.venue_name = None
        self.coverage = None
        attribs = ['date', 'identifier', 'avg_rating', 'format', 'collection', 'num_reviews', 'downloads', 'addeddate']
        for k in attribs:
            if k in raw_json.keys():
                setattr(self, k, raw_json[k])

        # for k, v in raw_json.items():
        #     if k in attribs:
        #         setattr(self, k, v)
        self.url_metadata = 'https://archive.org/metadata/' + self.identifier
        self.url_details = 'https://archive.org/details/' + self.identifier
        if self.addeddate.startswith('0000'):
            self.addeddate = '1990-01-01T00:00:00Z'
        self.addeddate = datetime.datetime.fromisoformat(self.addeddate[:-1])
        if isinstance(self.date, list):
            self.date = self.date[0]
        self.date = self.date[:10]
        self.set_data = set_data.get(self.date)
        colls = config.optd['COLLECTIONS']
        self.artist = colls[min([colls.index(c) if c in colls else 100 for c in self.collection])] if len(colls) > 1 else colls[0]
        date = to_date(self.date).date()
        self.meta_path = os.path.join(self.dbpath, str(date.year), str(date.month), self.identifier + '.json')

        self.avg_rating = float(raw_json.get('avg_rating', 2))
        self.num_reviews = int(raw_json.get('num_reviews', 1))
        self.downloads = int(raw_json.get('downloads', 1))

    def stream_only(self):
        return 'stream_only' in self.collection

    def compute_score(self):
        """ compute a score for sorting the tape. High score means it should be played first """
        if self._remove_from_archive:
            return -1
        score = 3
        if self.stream_only():
            score = score + 10
        if 'optd' in dir(config) and len(config.optd['FAVORED_TAPER']) > 0:
            if any(x.lower() in self.identifier.lower() for x in config.optd['FAVORED_TAPER']):
                score = score + 3
        # This is now taken care of at the Archivary level.
        # if 'optd' in dir(config) and len(config.optd['COLLECTIONS']) > 1:
        #    colls = config.optd['COLLECTIONS']
        #    score = score + 5 * (len(colls) - min([colls.index(c) if c in colls else 100 for c in self.collection]))
        self.get_metadata(only_if_cached=True)
        if self.meta_loaded:
            if not self.contains_sound():
                self._remove_from_archive = True
                return -1
            score = score + 3 * (self.title_fraction() - 1)  # reduce score for tapes without titles.
            score = score + min(20, len(self._tracks)) / 4
        score = score + math.log(1 + self.downloads)
        score = score + 0.5 * (self.avg_rating - 2.0 / math.sqrt(self.num_reviews))  # down-weigh avg_rating: it's usually about the show, not the tape.
        return score

    def title_fraction(self):
        n_tracks = len(self._tracks)
        lc = string.ascii_lowercase
        n_known = len([t for t in self._tracks if t.title != 'unknown' and sum([x in lc for x in t.title.lower()]) > 4])
        return (1 + n_known) / (1 + n_tracks)

    def remove_from_archive(self, page_meta):
        self._remove_from_archive = True

    def get_metadata(self, only_if_cached=False):
        if self.meta_loaded:
            return
        if only_if_cached and not os.path.exists(self.meta_path):   # we don't have it cached, so return.
            return
        self._tracks = []
        try:     # I used to check if file exists, but it may also be corrupt, so this is safer.
            page_meta = json.load(open(self.meta_path, 'r'))
        except Exception:
            r = requests.get(self.url_metadata)
            logger.info("url is {}".format(r.url))
            if r.status_code != 200:
                logger.warning("error pulling data for {}".format(self.identifier))
                raise Exception('Download', 'Error {} url {}'.format(r.status_code, self.url_metadata))
            try:
                page_meta = r.json()
            except ValueError:
                logger.warning("Json Error {}".format(r.url))
                return
            except Exception:
                logger.warning("Error getting metadata (json?)")
                return

        # self.reviews = page_meta['reviews'] if 'reviews' in page_meta.keys() else []
        orig_titles = {}
        if 'files' not in page_meta.keys():
            # This tape can not be played, and should be removed from the data.
            self.remove_from_archive(page_meta)
            return
        for ifile in page_meta['files']:
            try:
                if ifile['source'] == 'original':
                    try:
                        orig_titles[ifile['name']] = ifile['title'] if ('title' in ifile.keys() and ifile['title'] != 'unknown') else ifile['name']
                        # orig_titles[ifile['name']] = re.sub(r'(.flac)|(.mp3)|(.ogg)$','', orig_titles[ifile['name']])
                    except Exception as e:
                        logger.exception(e)
                        pass
                if ifile['format'] in (self._lossy_formats if self.stream_only() else self._playable_formats):
                    self.append_track(ifile, orig_titles)
            except KeyError as e:
                logger.warning("Error in parsing metadata")
                raise(e)
                pass
            except Exception as e:   # TODO handle this!!!
                raise (e)

        try:
            self.venue_name = page_meta['metadata']['venue']
            self.coverage = page_meta['metadata']['coverage']
        except Exception:
            # logger.warn(f"Failed to read venue, city, state from metadata. {self.meta_path}")
            pass

        self.write_metadata(page_meta)

        for track in self._tracks:
            track.title = re.sub(r'gd\d{2}(?:\d{2})?-\d{2}-\d{2}[ ]*([td]\d*)*', '', track.title).strip()
            track.title = re.sub(r'(.flac)|(.mp3)|(.ogg)$', '', track.title).strip()
        self.insert_breaks()
        return

    def write_metadata(self, page_meta):
        os.makedirs(os.path.dirname(self.meta_path), exist_ok=True)
        json.dump(page_meta, open(self.meta_path, 'w'))
        self.meta_loaded = True

    def append_track(self, tdict, orig_titles={}):
        if not 'original' in tdict.keys():  # This is not a valid track
            return
        name = tdict.get('name', 'unknown')
        if name.startswith('_78'):          # in the georgeblood collections, these are auxilliary tracks, to be ignored.
            return
        source = tdict['source']
        if source == 'original':
            orig = tdict['name']
            # orig = re.sub(r'(.flac)|(.mp3)|(.ogg)$','', orig)
        else:
            orig = tdict['original']
        if tdict.get('title', 'unknown') == 'unknown':
            if orig in orig_titles.keys():
                tdict['title'] = orig_titles[orig]
        for i, t in enumerate(self._tracks):  # loop over the _tracks we already have
            if orig == t.original:  # add in alternate formats.
                # make sure that this isn't a duplicate!!!
                t.add_file(tdict)
                return t  # don't append this, because we already have this _track
        self._tracks.append(GDTrack(tdict, self.identifier))

    def venue(self, tracknum=0):
        """return the venue, city, state"""
        # Note, if tracknum > 0, this could be a second show...check after running insert_breaks
        # 1970-02-14 is an example with 2 shows.
        if self.artist not in ['GratefulDead']:
            self.get_metadata(only_if_cached=True)
            if self.meta_loaded:
                venue_name = self.venue_name
                city_state = self.coverage
                venue_string = f'{venue_name}, {city_state}'
                return venue_string
        sd = self.set_data
        if sd is None:
            return self.identifier
        venue_string = ""
        loc = sd['location']
        if tracknum > 0:    # only pull the metadata if the query is about a late track.
            self.get_metadata()
            breaks = self._compute_breaks()
            if (len(breaks['location']) > 0) and (tracknum > breaks['location'][0]):
                loc = sd['location2']
        venue_string = F"{loc[0]}, {loc[1]}, {loc[2]}"
        return venue_string

    def _compute_breaks(self):
        if not self.meta_loaded:
            self.get_metadata()
        tlist = [x.title for x in self._tracks]
        replacements = {'GDTRFB': 'Going Down the Road Feeling Bad', 'FOTD': 'Friend of the Devil', 'EOTW': 'Eyes of the World'}
        replacer = replacements.get
        tlist = [replacer(n, n) for n in tlist]
        sd = self.set_data
        if sd is None:
            sd = {}
        lb = sd['longbreaks'] if 'longbreaks' in sd.keys() else []
        sb = sd['shortbreaks'] if 'shortbreaks' in sd.keys() else []
        locb = sd['locationbreak'] if 'locationbreak' in sd.keys() else []
        long_breaks = []
        short_breaks = []
        location_breaks = []
        try:
            long_breaks = [difflib.get_close_matches(x, tlist)[0] for x in lb]
            short_breaks = [difflib.get_close_matches(x, tlist)[0] for x in sb]
            location_breaks = [difflib.get_close_matches(x, tlist)[0] for x in locb]
        except Exception:
            pass
        # NOTE: Use the _last_ element here to handle sandwiches.
        lb_locations = []
        sb_locations = []
        locb_locations = []
        lb_locations = [j for t, j in {t: j + 1 for j, t in enumerate(tlist) if t in long_breaks}.items()]
        sb_locations = [j for t, j in {t: j + 1 for j, t in enumerate(tlist) if t in short_breaks}.items()]
        locb_locations = [j for t, j in {t: j + 1 for j, t in enumerate(tlist) if t in location_breaks}.items()]
        # At this point, i need to add "longbreak" and "shortbreak" tracks to the tape.
        # This will require creating special GDTracks.
        # for now, return the location indices.
        return {'long': lb_locations, 'short': sb_locations, 'location': locb_locations}

    def insert_breaks(self, breaks=None, force=False):
        if not self.meta_loaded:
            self.get_metadata()
        if self._breaks_added and not force:
            return
        if not breaks:
            breaks = self._compute_breaks()
        longbreak_path = pkg_resources.resource_filename('timemachine.metadata', 'silence600.ogg')
        breakd = {'track': -1, 'original': 'setbreak', 'title': 'Set Break', 'format': 'Ogg Vorbis', 'size': 1, 'source': 'original', 'path': os.path.dirname(longbreak_path)}
        lbreakd = dict(list(breakd.items()) + [('title', 'Set Break'), ('name', 'silence600.ogg')])
        sbreakd = dict(list(breakd.items()) + [('title', 'Encore Break'), ('name', 'silence0.ogg')])
        locbreakd = dict(list(breakd.items()) + [('title', 'Location Break'), ('name', 'silence600.ogg')])
        flipbreakd = dict(list(breakd.items()) + [('title', 'Record Flip'), ('name', 'silence30.ogg')])
        recordbreakd = dict(list(breakd.items()) + [('title', 'Record Change'), ('name', 'silence120.ogg')])

        # make the tracks
        newtracks = []
        tlist = [x.title for x in self._tracks]
        set_breaks_already_in_tape = difflib.get_close_matches('Set Break', tlist, cutoff=0.6)
        set_breaks_already_locs = [tlist.index(x) for x in set_breaks_already_in_tape]
        for i, t in enumerate(self._tracks):
            if i not in set_breaks_already_locs:
                if 'long' in breaks.keys():
                    for j in breaks['long']:
                        if i == j:
                            newtracks.append(GDTrack(lbreakd, '', True))
                if 'short' in breaks.keys():
                    for j in breaks['short']:
                        if i == j:
                            newtracks.append(GDTrack(sbreakd, '', True))
                if 'location' in breaks.keys():
                    for j in breaks['location']:
                        if i == j:
                            newtracks.append(GDTrack(locbreakd, '', True))
                if 'flip' in breaks.keys():
                    for j in breaks['flip']:
                        if i == j:
                            newtracks.append(GDTrack(flipbreakd, '', True))
                if 'record' in breaks.keys():
                    for j in breaks['record']:
                        if i == j:
                            newtracks.append(GDTrack(recordbreakd, '', True))
            newtracks.append(t)
        self._breaks_added = True
        self._tracks = newtracks.copy()


class GDTrack(BaseTrack):
    """ A track from a GDTape recording """

    def __init__(self, tdict, parent_id, break_track=False):
        super().__init__(tdict, parent_id, break_track)
        attribs = ['track', 'original', 'title']

        """ NOTE This should be part of the player, not part of the tape or track, as it is now """
        if config.optd['PLAY_LOSSLESS']:
            self._playable_formats = ['Flac', 'Shorten', 'Ogg Vorbis', 'VBR MP3', 'MP3']
        else:
            self._playable_formats = ['Ogg Vorbis', 'VBR MP3', 'MP3']
        self._lossy_formats = ['Ogg Vorbis', 'VBR MP3', 'MP3']
        """ ----------------------------------------------------------------------------------- """

        if 'title' not in tdict.keys():
            tdict['title'] = tdict['name'] if 'name' in tdict.keys() else 'unknown'
        for k, v in tdict.items():
            if k in attribs:
                setattr(self, k, v)
        if tdict['source'] == 'original':
            self.original = tdict['name']
        try:
            self.track = int(self.track) if 'track' in dir(self) else None
        except ValueError:
            self.track = None
        self.files = []
        self.add_file(tdict, break_track)

    def add_file(self, tdict, break_track=False):
        attribs = ['name', 'format', 'size', 'source', 'path']
        d = {k: v for (k, v) in tdict.items() if k in attribs}
        d['size'] = int(d['size'])
        if not break_track:
            d['url'] = 'https://archive.org/download/' + self.parent_id + '/' + d['name']
        else:
            d['url'] = 'file://' + os.path.join(d['path'], d['name'])
        self.files.append(d)
        self.files = sorted(self.files, key=lambda x: self._playable_formats.index(x['format']))


class GDSet:
    """ Set Information from a Grateful Dead date """

    def __init__(self, collection_list):
        self.collection_list = collection_list
        set_data = {}
        if 'GratefulDead' not in self.collection_list:
            self.set_data = set_data
            return
        prevsong = None
        set_breaks = pkg_resources.resource_stream('timemachine.metadata', 'set_breaks.csv')
        utf8_reader = codecs.getreader("utf-8")
        r = [r for r in csv.reader(utf8_reader(set_breaks))]
        headers = r[0]
        for row in r[1:]:
            d = dict(zip(headers, row))
            date = d['date']
            time = d['time']
            song = d['song']
            if date not in set_data.keys():
                set_data[date] = {}
            set_data[date]['start_time'] = datetime.time.fromisoformat(time) if len(time) > 0 else None
            if int(d['ievent']) == 1:
                set_data[date]['location'] = (d['venue'], d['city'], d['state'])
                prevsong = song
            if int(d['ievent']) == 2:
                set_data[date]['location2'] = (d['venue'], d['city'], d['state'])
                set_data[date]['locationbreak'] = [prevsong]
            if d['break_length'] == 'long':
                try:
                    set_data[date]['longbreaks'].append(song)
                except KeyError:
                    set_data[date]['longbreaks'] = [song]
            if d['break_length'] == 'short':
                try:
                    set_data[date]['shortbreaks'].append(song)
                except KeyError:
                    set_data[date]['shortbreaks'] = [song]

        self.set_data = set_data
        """
    for k,v in set_data.items():
       setattr(self,k,v)
    """

    def get(self, date):
        return self.set_data[date] if date in self.set_data.keys() else None

    def multi_location(self, date):
        d = self.get(date)
        return 'location2' in d.keys()

    def location(self, date):
        d = self.get(date)
        return d['location']

    def shortbreaks(self, date):
        d = self.get(date)
        return d['shortbreaks']

    def longbreaks(self, date):
        d = self.get(date)
        return d['longbreaks']

    def location2(self, date):
        d = self.get(date)
        if self.multi_location(date):
            return d['location2']
        else:
            return None

    def locationbreaks(self, date):
        d = self.get(date)
        if self.multi_location(date):
            return d['locationbreak']
        else:
            return None

    def __str__(self):
        return self.__repr__()

    def __repr__(self):
        retstr = "Grateful Dead set data"
        return retstr


class Archivary_Updater(Thread):
    """Updater runs in the backround checking for updates.

    The Updater runs in a thread periodically checking for and applying
    updates.

    It adds randomness to the update interval by adding +/- 10% randomness
    to the time spent waiting for the next update check.
    """

    def __init__(self, state, interval: float, event: Event, scr=None, lock: Optional[Lock] = None, stop_on_exception: bool = False) -> None:
        """Create an Updater.

             Args:
                 interval (float): Seconds between checks, pre-jitter.
                 state (controls.state): state of the player.
                 event (Event): Event which can be used to stop the update loop.
                 lock (Lock): Optional. Lock to acquire before an update. If a
                     lock is provided, it is only acquired when performing
                     the update and not when checking if the update is
                     necessary.
                 scr (controls.screen): The screen object, used to indicate that device is updating.
                 stop_on_exception (bool): Set to True to have the updater loop
                     stop checking for updates if there is an exception in the
                     update process.
             NOTE The Updater will check every <interval> seconds, but only update
                  every <min_time_between_updates> seconds. So we will check more often than we
                  will actually do an update. That is because we don't want to update while playing.
                  Is the "don't update while playing" worth the trouble?
        """
        super().__init__()
        self.interval = interval
        self.state = state
        self.stopped = event
        self.lock = lock
        self.scr = scr
        self.stop_on_exception = stop_on_exception
        self.last_update_time = datetime.datetime.now()
        self.min_time_between_updates = 5 * 3600

    def check_for_updates(self, playstate) -> bool:
        """Check for updates.
        Returns:
            (bool) True if AUTO_UPDATE and the player is currently not playing
        """
        if not config.optd['AUTO_UPDATE_ARCHIVE']:
            return False
        logger.debug("Checking for updates.")
        time_since_last_update = (datetime.datetime.now() - self.last_update_time).seconds
        playing = playstate == config.PLAYING
        return (not playing) and (time_since_last_update >= self.min_time_between_updates)

    def update(self) -> None:
        """Get the updates."""
        logger.info("Running update")
        archive = self.state.date_reader.archive
        if self.scr:
            self.scr.show_venue("UPDATING ARCHIVE", color=(255, 0, 0), force=True)
        archive.load_archive(reload_ids=False, with_latest=True)
        self.last_update_time = datetime.datetime.now()

    def run(self):
        while not self.stopped.wait(timeout=self.interval * (1 + 0.1 * random.random())):
            current = self.state.get_current()
            playstate = current['PLAY_STATE']
            if not self.check_for_updates(playstate):
                continue
            try:
                if self.lock:
                    if self.lock.acquire(timeout=10.0):
                        self.update()
            except Exception as e:
                if self.stop_on_exception:
                    raise e
                logger.exception(e)
            finally:
                if self.lock:
                    logger.debug('releasing updater lock')
                    self.lock.release()
