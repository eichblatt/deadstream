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


class BaseTapeDownloader(abc.ABC):
    """Abstract base class for a Grateful Dead tape downloader.

    Use one of the subclasses: TapeDownloader or AsyncTapeDownloader.
    """

    def __init__(self, url="https://archive.org", collection_name="etree"):
        self.url = url
        self.collection_name = collection_name
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

    @abc.abstractmethod
    def get_tapes(self, years):
        """Get a list of tapes for years."""
        pass

    def get_all_tapes(self, iddir, min_addeddate=None):
        """Get a list of all tapes."""
        pass


class TapeDownloader(BaseTapeDownloader):
    """Synchronous Grateful Dead Tape Downloader"""

    def store_by_period(self, iddir, tapes, period_func=to_decade):
        """Store the tapes json data into files by period"""
        os.makedirs(iddir, exist_ok=True)
        periods = sorted(list(set([period_func(t['date']) for t in tapes])))
        n_tapes_added = 0
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

    def get_all_tapes(self, iddir, min_addeddate=None):
        """Get a list of all tapes.
        Write all tapes to a folder by time period
        """
        current_rows = 0
        n_tapes_added = 0
        n_tapes_total = 0
        tapes = []

        min_date = '1900-01-01'
        max_date = datetime.datetime.now().date().strftime('%Y-%m-%d')

        r = self._get_piece(min_date, max_date, min_addeddate)
        j = r.json()
        total = j['total']
        logger.debug(f"total rows {total}")
        current_rows += j['count']
        tapes = j['items']

        if iddir.endswith('etree_ids'):
            n_tapes_added = self.store_by_period(iddir, tapes, period_func=to_year)
        else:
            n_tapes_added = self.store_by_period(iddir, tapes, period_func=to_decade)
        n_tapes_total = n_tapes_added

        while (current_rows < 1.25*total) and n_tapes_added > 0:
            min_date_field = tapes[-1]['date']
            min_date = min_date_field[:10]  # Should we subtract some days for overlap?
            r = self._get_piece(min_date, max_date, min_addeddate)
            j = r.json()
            current_rows += j['count']
            tapes = j['items']
            if iddir.endswith('etree_ids'):
                n_tapes_added = self.store_by_period(iddir, tapes, period_func=to_year)
            else:
                n_tapes_added = self.store_by_period(iddir, tapes, period_func=to_decade)
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

    def _get_piece(self, min_date, max_date, min_addeddate=None):
        """Get one chunk of a year's tape information.
        Returns a list of dictionaries of tape information
        """
        parms = self.parms.copy()
        if min_addeddate is None:
            query = F'collection:{self.collection_name} AND date:[{min_date} TO {max_date}]'
        else:
            # max_addeddate = datetime.datetime.now().strftime('%Y-%m-%dT%H:%M:%SZ')
            query = F'collection:{self.collection_name} AND date:[{min_date} TO {max_date}] AND addeddate:[{min_addeddate} TO {max_date}]'
        parms['q'] = query
        r = requests.get(self.api, params=parms)
        logger.debug(f"url is {r.url}")
        if r.status_code != 200:
            logger.error(f"Error {r.status_code} collecting data")
            raise Exception(
                'Download', 'Error {} collection'.format(r.status_code))
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
        query = F'collection:{self.collection_name} AND year:{year}'
        parms['q'] = query
        r = requests.get(self.api, params=parms)
        logger.debug(f"url is {r.url}")
        if r.status_code != 200:
            logger.error(f"Error {r.status_code} collecting data")
            raise Exception(
                'Download', 'Error {} collection'.format(r.status_code))
        return r


class GDArchive:
    """ The Grateful Dead Collection on Archive.org """

    def __init__(self, dbpath=os.path.join(ROOT_DIR, 'metadata'), url='https://archive.org', reload_ids=False, sync=True, with_latest=False, collection_name=['GratefulDead']):
        """Create a new GDArchive.

        Parameters:

          dbpath: Path to filesystem location where data are stored
          url: URL for the internet archive
          reload_ids: If True, force re-download of tape data
          sync: If True use the slower synchronous downloader
          with_latest: If True, query archive for recently added tapes, and append them.
          collection_name: A list of collections from archive.org
        """
        self.tapes = []
        self.url = url
        self.dbpath = dbpath
        self.collection_name = collection_name if type(collection_name) == list else [collection_name]
        if len(self.collection_name) == 1:
            self.idpath = os.path.join(self.dbpath, F'{collection_name[0]}_ids')
            # self.idpath_pkl = os.path.join(self.dbpath, F'{collection_name[0]}_ids.pkl')
            self.downloader = TapeDownloader(url, collection_name=collection_name[0])
        else:
            self.idpath = os.path.join(self.dbpath, 'etree_ids')
            # self.idpath_pkl = os.path.join(self.dbpath, 'etree_ids.pkl')
            self.downloader = TapeDownloader(url)
        self.set_data = GDSet(self.collection_name)
        self.load_archive(reload_ids, with_latest)

    def __str__(self):
        return self.__repr__()

    def __repr__(self):
        retstr = F"{self.collection_name} Archive with {len(self.tapes)} tapes on {len(self.dates)} dates from {self.dates[0]} to {self.dates[-1]} "
        return retstr

    def year_list(self):
        return sorted(set([to_date(x).year for x in self.dates]))

    def load_archive(self, reload_ids=False, with_latest=False):
        self.tapes = self.load_tapes(reload_ids, with_latest)
        self.tape_dates = self.get_tape_dates()
        self.dates = sorted(self.tape_dates.keys())

    def best_tape(self, date, resort=True):
        if isinstance(date, datetime.date):
            date = date.strftime('%Y-%m-%d')
        if date not in self.dates:
            logger.info("No Tape for date {}".format(date))
            return None
        tapes = self.tape_dates[date]
        if resort:
            _ = [t.tracks() for t in tapes[:3]]   # load first 3 tapes' tracks. Decrease score of those without titles.
            tapes = sorted(tapes, key=methodcaller('compute_score'), reverse=True)
        return tapes[0]

    def tape_at_date(self, dt, which_tape=0):
        then_date = dt.date()
        then = then_date.strftime('%Y-%m-%d')
        try:
            tape = self.tape_dates[then]
        except KeyError:
            return None
        return tape[which_tape]

    def tape_start_time(self, dt, default_start=datetime.time(19, 0)):
        tape = self.tape_at_date(dt)
        if not tape:
            return None
        tape_start_time = tape.set_data['start_time'] if tape.set_data else None
        if tape_start_time is None:
            tape_start_time = default_start
        tape_start = datetime.datetime.combine(dt.date(), tape_start_time)  # date + time
        return tape_start

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

    def get_tape_dates(self):
        tape_dates = {}
        for tape in self.tapes:
            k = tape.date
            if k not in tape_dates.keys():
                tape_dates[k] = [tape]
            else:
                tape_dates[k].append(tape)
        # Now that we have all tape for a date, put them in the right order
        self.tape_dates = {}
        for k, v in tape_dates.items():
            self.tape_dates[k] = sorted(v, key=methodcaller('compute_score'), reverse=True)
        return self.tape_dates

    def load_current_tapes(self, reload_ids=False):
        logger.debug("Loading current tapes")
        tapes = []
        addeddates = []
        if reload_ids or not os.path.exists(self.idpath):
            os.system(f'rm -rf {self.idpath}')
            logger.info('Loading Tapes from the Archive...this will take a few minutes')
            n_tapes = self.downloader.get_all_tapes(self.idpath)  # this will write chunks to folder
            logger.info(f'Loaded {n_tapes} tapes from archive')
        # loop over chunks -- get max addeddate before filtering collections.
        if os.path.isdir(self.idpath):
            for filename in os.listdir(self.idpath):
                if filename.endswith('.json'):
                    chunk = json.load(open(os.path.join(self.idpath, filename), 'r'))
                    addeddates.append(max([x['addeddate'] for x in chunk]))
                    chunk = [t for t in chunk if any(x in self.collection_name for x in t['collection'])]
                    tapes.extend(chunk)
        else:
            tapes = json.load(open(self.idpath, 'r'))
            addeddates.append(max([x['addeddate'] for x in tapes]))
            tapes = [t for t in tapes if any(x in self.collection_name for x in t['collection'])]
        max_addeddate = max(addeddates)
        return (tapes, max_addeddate)

    def load_tapes(self, reload_ids=False, with_latest=False):
        """ Load the tapes, then add anything which has been added since the tapes were saved """
        n_tapes = 0
        loaded_tapes, max_addeddate = self.load_current_tapes(reload_ids)
        logger.debug(f'max addeddate {max_addeddate}')

        min_download_addeddate = (datetime.datetime.strptime(max_addeddate, '%Y-%m-%dT%H:%M:%SZ')) - datetime.timedelta(hours=1)
        min_download_addeddate = datetime.datetime.strftime(min_download_addeddate, '%Y-%m-%dT%H:%M:%SZ')
        logger.debug(f'min_download_addeddate {min_download_addeddate}')

        if with_latest:
            logger.debug(f'Refreshing Tapes\nmax addeddate {max_addeddate}\nmin_download_addeddate {min_download_addeddate}')
            n_tapes = self.downloader.get_all_tapes(self.idpath, min_download_addeddate)
            logger.info(f'Loaded {n_tapes} new tapes from archive')
        if n_tapes > 0:
            logger.info(f'Adding {n_tapes} tapes')
            loaded_tapes, _ = self.load_current_tapes()
        else:
            if len(self.tapes) > 0:  # The tapes have already been written, and nothing was added
                return self.tapes
        self.tapes = [GDTape(self.dbpath, tape, self.set_data) for tape in loaded_tapes]
        return self.tapes


class GDTape:
    """ A Grateful Dead Identifier Item -- does not contain tracks """

    def __init__(self, dbpath, raw_json, set_data):
        self.dbpath = dbpath
        self._playable_formats = ['Ogg Vorbis', 'VBR MP3', 'MP3']  # , 'Shorten', 'Flac']
        self._lossy_formats = ['Ogg Vorbis', 'VBR MP3', 'MP3']
        self._breaks_added = False
        self.meta_loaded = False
        attribs = ['date', 'identifier', 'avg_rating', 'format', 'collection', 'num_reviews', 'downloads', 'addeddate']
        for k, v in raw_json.items():
            if k in attribs:
                setattr(self, k, v)
        self.url_metadata = 'https://archive.org/metadata/' + self.identifier
        self.url_details = 'https://archive.org/details/' + self.identifier
        if self.addeddate.startswith('0000'):
            self.addeddate = '1990-01-01T00:00:00Z'
        self.addeddate = (datetime.datetime.strptime(self.addeddate, '%Y-%m-%dT%H:%M:%SZ'))
        if type(self.date) == list:
            self.date = self.date[0]
        self.date = str((datetime.datetime.strptime(self.date, '%Y-%m-%dT%H:%M:%SZ')).date())
        self.set_data = set_data.get(self.date)
        if 'avg_rating' in raw_json.keys():
            self.avg_rating = float(self.avg_rating)
        else:
            self.avg_rating = 2.0
        if 'num_reviews' in raw_json.keys():
            self.num_reviews = int(self.num_reviews)
        else:
            self.num_reviews = 1
        if 'downloads' in raw_json.keys():
            self.downloads = int(self.num_reviews)
        else:
            self.downloads = 1

    def __str__(self):
        return self.__repr__()

    def __repr__(self):
        tag = "SBD" if self.stream_only() else "aud"
        retstr = '{} - {} - {:5.2f} - {}\n'.format(self.date, tag, self.avg_rating, self.identifier)
        return retstr

    def stream_only(self):
        return 'stream_only' in self.collection

    def compute_score(self):
        """ compute a score for sorting the tape. High score means it should be played first """
        score = 3
        if self.stream_only():
            score = score + 10
        if 'optd' in dir(config) and len(config.optd['FAVORED_TAPER']) > 0:
            if config.optd['FAVORED_TAPER'].lower() in self.identifier.lower():
                score = score + 3
        if 'optd' in dir(config) and len(config.optd['COLLECTIONS']) > 1:
            colls = config.optd['COLLECTIONS']
            score = score + 5 * (len(colls) - min([colls.index(c) if c in colls else 100 for c in self.collection]))
        if self.meta_loaded:
            score = score + 3*(self.title_fraction()-1)  # reduce score for tapes without titles.
            score = score + len(self._tracks)/4
        score = score + math.log(1+self.downloads)
        score = score + 0.5 * (self.avg_rating - 2.0/math.sqrt(self.num_reviews))  # down-weigh avg_rating: it's usually about the show, not the tape.
        return score

    def contains_sound(self):
        return len(list(set(self._playable_formats) & set(self.format))) > 0

    def title_fraction(self):
        n_tracks = len(self._tracks)
        n_known = len([t for t in self._tracks if t.title != 'unknown'])
        return (1 + n_known) / (1 + n_tracks)

    def tracks(self):
        self.get_metadata()
        return self._tracks

    def tracklist(self):
        for i, t in enumerate(self._tracks):
            logger.info(i)

    def track(self, n):
        if not self.meta_loaded:
            self.get_metadata()
        return self._tracks[n-1]

    def get_metadata(self):
        if self.meta_loaded:
            return
        self._tracks = []
        date = to_date(self.date).date()
        meta_path = os.path.join(self.dbpath, str(date.year), str(date.month), self.identifier+'.json')
        try:     # I used to check if file exists, but it may also be corrupt, so this is safer.
            page_meta = json.load(open(meta_path, 'r'))
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
                return None
            except Exception:
                logger.warning("Error getting metadata (json?)")
                return None

        # self.reviews = page_meta['reviews'] if 'reviews' in page_meta.keys() else []
        orig_titles = {}
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
        os.makedirs(os.path.dirname(meta_path), exist_ok=True)
        json.dump(page_meta, open(meta_path, 'w'))
        self.meta_loaded = True
        # return page_meta
        for track in self._tracks:
            track.title = re.sub(r'gd\d{2}(?:\d{2})?-\d{2}-\d{2}[ ]*([td]\d*)*', '', track.title).strip()
            track.title = re.sub(r'(.flac)|(.mp3)|(.ogg)$', '', track.title).strip()
        self.insert_breaks()
        return

    def append_track(self, tdict, orig_titles={}):
        source = tdict['source']
        if source == 'original':
            orig = tdict['name']
            # orig = re.sub(r'(.flac)|(.mp3)|(.ogg)$','', orig)
        else:
            orig = tdict['original']
            if 'title' not in tdict.keys():
                tdict['title'] = 'unknown'
        if tdict['title'] == 'unknown':
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
        lb_locations = [j for t, j in {t: j+1 for j, t in enumerate(tlist) if t in long_breaks}.items()]
        sb_locations = [j for t, j in {t: j+1 for j, t in enumerate(tlist) if t in short_breaks}.items()]
        locb_locations = [j for t, j in {t: j+1 for j, t in enumerate(tlist) if t in location_breaks}.items()]
        # At this point, i need to add "longbreak" and "shortbreak" tracks to the tape.
        # This will require creating special GDTracks, I guess.
        # for now, return the location indices.
        return {'long': lb_locations, 'short': sb_locations, 'location': locb_locations}

    def insert_breaks(self):
        if not self.meta_loaded:
            self.get_metadata()
        if self._breaks_added:
            return
        breaks = self._compute_breaks()
        longbreak_path = pkg_resources.resource_filename('timemachine.metadata', 'silence600.ogg')
        breakd = {'track': -1, 'original': 'setbreak', 'title': 'Set Break', 'format': 'Ogg Vorbis', 'size': 1, 'source': 'original', 'path': os.path.dirname(longbreak_path)}
        lbreakd = dict(list(breakd.items()) + [('title', 'Set Break'), ('name', 'silence600.ogg')])
        # sbreakd = dict(list(breakd.items()) + [('title', 'Encore Break'), ('name', 'silence300.ogg')])
        sbreakd = dict(list(breakd.items()) + [('title', 'Encore Break'), ('name', 'silence0.ogg')])
        locbreakd = dict(list(breakd.items()) + [('title', 'Location Break'), ('name', 'silence600.ogg')])

        # make the tracks
        newtracks = []
        for i, t in enumerate(self._tracks):
            for j in breaks['long']:
                if i == j:
                    newtracks.append(GDTrack(lbreakd, '', True))
            for j in breaks['short']:
                if i == j:
                    newtracks.append(GDTrack(sbreakd, '', True))
            for j in breaks['location']:
                if i == j:
                    newtracks.append(GDTrack(locbreakd, '', True))
            newtracks.append(t)
        self._breaks_added = True
        self._tracks = newtracks.copy()


class GDTrack:
    """ A track from a GDTape recording """

    def __init__(self, tdict, parent_id, break_track=False):
        self.parent_id = parent_id
        attribs = ['track', 'original', 'title']
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

    def __str__(self):
        return self.__repr__()

    def __repr__(self):
        retstr = 'track {}. {}'.format(self.track, self.title)
        return retstr

    def add_file(self, tdict, break_track=False):
        attribs = ['name', 'format', 'size', 'source', 'path']
        d = {k: v for (k, v) in tdict.items() if k in attribs}
        d['size'] = int(d['size'])
        if not break_track:
            d['url'] = 'https://archive.org/download/'+self.parent_id+'/'+d['name']
        else:
            d['url'] = 'file://'+os.path.join(d['path'], d['name'])
        self.files.append(d)
    # method to play(), pause().


class GDSet:
    """ Set Information from a Grateful Dead date """

    def __init__(self, collection_name):
        self.collection_name = collection_name
        set_data = {}
        if 'GratefulDead' not in self.collection_name:
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
            set_data[date]['start_time'] = datetime.datetime.strptime(time, '%H:%M:%S.%f').time() if len(time) > 0 else None
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


class GDPlayer(MPV):
    """ A media player to play a GDTape """

    def __init__(self, tape=None):
        super().__init__()
        # self._set_property('prefetch-playlist','yes')
        # self._set_property('cache-dir','/home/steve/cache')
        # self._set_property('cache-on-disk','yes')
        self._set_property('audio-buffer', 10.0)  # This allows to play directly from the html without a gap!
        self._set_property('cache', 'yes')
        # self.default_audio_device = 'pulse'
        self.default_audio_device = 'auto'
        audio_device = self.default_audio_device
        self._set_property('audio-device', audio_device)
        self.download_when_possible = False
        self.tape = None
        if tape is not None:
            self.insert_tape(tape)

    def __str__(self):
        return self.__repr__()

    def __repr__(self):
        retstr = str(self.playlist)
        return retstr

    def insert_tape(self, tape):
        self.tape = tape
        self.create_playlist()

    def eject_tape(self):
        self.stop()
        self.tape = None
        self.playlist_clear()

    def extract_urls(self, tape):  # NOTE this should also give a list of backup URL's.
        tape.get_metadata()
        urls = []
        playable_formats = tape._playable_formats
        preferred_format = playable_formats[0]
        for track_files in [x.files for x in tape.tracks()]:
            best_track = None
            candidates = []
            for f in track_files:
                if f['format'] == preferred_format:
                    best_track = f['url']
                elif f['format'] in playable_formats:
                    candidates.append(f['url'])
            if best_track is None and len(candidates) > 0:
                best_track = candidates[0]
            urls.append(best_track)
        return urls

    def create_playlist(self):
        self.playlist_clear()
        urls = self.extract_urls(self.tape)
        self.command('loadfile', urls[0])
        if len(urls) > 0:
            _ = [self.command('loadfile', x, 'append') for x in urls[1:]]
        self.playlist_pos = 0
        self.pause()
        logger.info(F"Playlist {self.playlist}")
        return

    def reset_audio_device(self, kwarg=None):
        if self.get_prop('audio-device') == 'null':
            logger.info(F"changing audio-device to {self.default_audio_device}")
            audio_device = self.default_audio_device
            self._set_property('audio-device', audio_device)
            self.wait_for_property('audio-device', lambda v: v == audio_device)
            if self.get_prop('current-ao') is None:
                logger.warning("Current-ao is None")
                self.stop()
                return False
            self.pause()
            self._set_property('pause', False)
            self.wait_until_playing()
            self.pause()
        return True

    def play(self):
        if not retry_call(self.reset_audio_device, None):
            logger.warning("Failed to reset audio device when playing")
        # if not self.reset_audio_device():
        #    return
        logger.info("playing")
        self._set_property('pause', False)
        self.wait_until_playing()

    def pause(self):
        logger.info("pausing")
        self._set_property('pause', True)
        self.wait_until_paused()

    def stop(self):
        self.playlist_pos = 0
        self.pause()

    def next(self, blocking=False):
        pos = self.get_prop('playlist-pos')
        if pos is None or pos + 1 == len(self.playlist):
            return
        self.command('playlist-next')
        if blocking:
            self.wait_for_event('file-loaded')

    def prev(self):
        pos = self.get_prop('playlist-pos')
        if pos is None or pos == 0:
            return
        self.command('playlist-prev')

    def time_remaining(self):
        icounter = 0
        self.wait_for_property('time-remaining', lambda v: v is not None)
        time_remaining = self.get_prop('time-remaining')
        while time_remaining is None and icounter < 20:
            logger.info(F'time-remaining is {time_remaining},icounter:{icounter},playlist:{self.playlist}')
            time.sleep(1)
            icounter = icounter + 1
            time_remaining = self.get_prop('time-remaining')
            self.status()
        logger.debug(F'time-remaining is {time_remaining}')
        return time_remaining

    def seek_in_tape_to(self, destination, ticking=True, threshold=1):
        """ Seek to a time position in a tape. Since this can take some
            time, the ticking option allows to take into account the time
            required to seek (the slippage).
            destination -- seconds from current tape location (from beginning?)
        """
        logger.debug(F'seek_in_tape_to {destination}')

        start_tick = datetime.datetime.now()
        slippage = 0
        skipped = 0
        dest_orig = destination
        time_remaining = self.time_remaining()
        playlist_pos = self.get_prop('playlist-pos')
        logger.debug(F'seek_in_tape_to dest:{destination},time-remainig:{time_remaining},playlist-pos:{playlist_pos}')
        while (destination > time_remaining) and self.get_prop('playlist-pos') + 1 < len(self.playlist):
            duration = self.get_prop('duration')
            logger.debug(F'seek_in_tape_to dest:{destination},time-remainig:{time_remaining},playlist-pos:{playlist_pos}, duration: {duration}, slippage {slippage}')
            self.next(blocking=True)
            skipped = skipped + time_remaining
            destination = dest_orig - skipped
            time_remaining = self.time_remaining()
            if ticking:
                now_tick = datetime.datetime.now()
                slippage = (now_tick - start_tick).seconds
                destination = destination + slippage
            playlist_pos = self.get_prop('playlist-pos')
        self.seek(destination)
        self.status()
        self.play()
        return

    def seek_to(self, track_no, destination=0.0, threshold=1):
        logger.debug(F'seek_to {track_no},{destination}')
        try:
            if track_no < 0 or track_no > len(self.playlist):
                raise Exception(F'seek_to track {track_no} out of bounds')
            paused = self.get_prop('pause')
            current_track = self.get_prop('playlist-pos')
            self.status()
            if current_track != track_no:
                self._set_property('playlist-pos', track_no)
                # self.wait_for_event('file-loaded')   # NOTE: this could wait forever!
                time.sleep(5)
            duration = self.get_prop('duration')
            if destination < 0:
                destination = duration + destination
            if (destination > duration) or (destination < 0):
                raise Exception(F'seek_to destination {destination} out of bounds (0,{duration})')

            self.seek(destination, reference='absolute')
            if not paused:
                self.play()
            time_pos = self.get_prop('time-pos')
            if abs(time_pos - destination) > threshold:
                raise Exception(F'Not close enough: time_pos {time_pos} - destination ({time_pos - destination})>{threshold}')
        except Exception as e:
            logger.warning(e)
        finally:
            pass

    def fseek(self, jumpsize=30, sleeptime=2):
        try:
            logger.debug(F'seeking {jumpsize}')

            current_track = self.get_prop('playlist-pos')
            time_pos = self.get_prop('time-pos')
            if time_pos is None:
                time_pos = 0
            time_pos = max(0, time_pos)
            duration = self.get_prop('duration')
            # self.wait_for_property('duration', lambda v: v is not None)

            destination = time_pos + jumpsize

            logger.debug(F'destination {destination} time_pos {time_pos} duration {duration}')

            if destination < 0:
                if abs(destination) < abs(sleeptime*5):
                    destination = destination - sleeptime*5
                self.seek_to(current_track-1, destination)
            if destination > duration:
                self.seek_to(current_track+1, destination-duration)
            else:
                self.seek_to(current_track, destination)
        except Exception as e:
            logger.warning(F'exception in seeking {e}')
        finally:
            time.sleep(sleeptime)

    def get_prop(self, property_name):
        return retry_call(self._get_property, property_name)

    def status(self):
        if self.playlist_pos is None:
            logger.info("Playlist not started")
            return None
        playlist_pos = self.get_prop('playlist-pos')
        paused = self.get_prop('pause')
        logger.info(F"Playlist at track {playlist_pos}, Paused {paused}")
        if self.raw.time_pos is None:
            logger.info("Track not started")
            return None
        duration = self.get_prop('duration')
        logger.info(F"duration: {duration}. time: {datetime.timedelta(seconds=int(self.raw.time_pos))}, time remaining: {datetime.timedelta(seconds=int(self.raw.time_remaining))}")
        return int(self.raw.time_remaining)

    def close(self): self.terminate()


class GDArchive_Updater(Thread):
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
        self.min_time_between_updates = 6*3600

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
        archive.load_archive(with_latest=True)
        self.last_update_time = datetime.datetime.now()

    def run(self):
        while not self.stopped.wait(timeout=self.interval*(1+0.1*random.random())):
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
