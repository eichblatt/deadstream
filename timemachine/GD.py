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
import aiofiles
import aiohttp
import asyncio
import codecs
import csv
import datetime
import difflib
import json
import logging
import math
import os
import requests
import threading
import time
from aiohttp import ClientResponse, ClientSession, ClientTimeout
from importlib import reload
from multiprocessing.pool import ThreadPool

from contextlib import closing
from operator import attrgetter, methodcaller
from mpv import MPV
from tenacity import retry
from tenacity.stop import stop_after_delay
from typing import Callable, List, Tuple

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


class BaseTapeDownloader(abc.ABC):
    """Abstract base class for a Grateful Dead tape downloader.

    Use one of the subclasses: TapeDownloader or AsyncTapeDownloader.
    """

    def __init__(self, url="https://archive.org", collection_name="GratefulDead"):
        self.url = url
        self.collection_name = collection_name
        self.api = f"{self.url}/services/search/v1/scrape"
        fields = ["identifier", "date", "avg_rating", "num_reviews",
                  "num_favorites", "stars", "downloads", "files_count",
                  "format", "collection", "source", "subject", "type"]
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

    def get_all_tapes(self):
        """Get a list of all tapes."""
        pass


class TapeDownloader(BaseTapeDownloader):
    """Synchronous Grateful Dead Tape Downloader"""

    def get_all_tapes(self):
        """Get a list of all tapes.
        Returns a list dictionaries of tape information
        """
        current_rows = 0
        tapes = []

        min_date = '1900-01-01'
        max_date = datetime.datetime.now().date().strftime('%Y-%m-%d')

        r = self._get_piece(min_date, max_date)
        j = r.json()
        total = j['total']
        logger.debug(f"total rows {total}")
        current_rows += j['count']
        tapes = j['items']

        while current_rows < total:
            min_date_field = tapes[-1]['date']
            min_date = min_date_field[:10]
            last_date_ids = [x['identifier'] for x in tapes if x['date'] == min_date_field]
            r = self._get_piece(min_date, max_date)
            j = r.json()
            current_rows += j['count']
            extra_tapes = j['items']
            extra_tapes = [x for x in extra_tapes if x['identifier'] not in last_date_ids]
            tapes.extend(extra_tapes)
        return tapes

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

    def _get_piece(self, min_date, max_date):
        """Get one chunk of a year's tape information.
        Returns a list of dictionaries of tape information
        """
        parms = self.parms.copy()
        query = F'collection:{self.collection_name} AND date:[{min_date} TO {max_date}]'
        parms['q'] = query
        r = requests.get(self.api, params=parms)
        logger.debug(f"url is {r.url}")
        if r.status_code != 200:
            logger.error(f"Error {r.status_code} collecting data")
            raise Exception(
                'Download', 'Error {} collection'.format(r.status_code))
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


class AsyncTapeDownloader(BaseTapeDownloader):
    """Asynchronous Grateful Dead Tape Downloader"""

    def get_all_tapes(self):
        """Get a list of all tapes."""
        pass

    def get_tapes(self, years):
        """Get a list of tapes.

        Parameters:

            years: List of years to download tapes for

        Returns a list dictionaries of tape information
        """
        tapes = asyncio.run(self._get_tapes(years))
        return tapes

    async def _get_tapes(self, years):
        """Get a list of tapes.

        Parameters:

            years: List of years to download tapes for

        Returns a list dictionaries of tape information
        """
        # This is the asynchronous impl of get_tapes()
        logger.info("Loading tapes from the archive...")
        timeout = aiohttp.ClientTimeout(total=600)
        async with aiohttp.ClientSession() as session:
            tasks = [self._get_tapes_year(session, year) for year in years]
            tapes = await asyncio.gather(*tasks)
        tapes = [tape for sublist in tapes for tape in sublist]
        return tapes

    async def _get_chunk(self, session, year, cursor=None):
        """Get one chunk of a year's tape information.

        Parameters:

            session: The aiohttp.ClientSession to make requests through
            year: The year to download tape information for
            cursor: Used to download a segment of a year of tapes

        Returns a list of dictionaries of tape information
        """
        parms = {"q": F"collection:{self.collection_name} AND year:{year}"}

        if cursor is not None:
            parms['cursor'] = cursor

        async with session.get(self.api, params={**self.parms, **parms}) as r:
            logger.debug(f"Year {year} chunk {cursor} url: {r.url}")
            json = await r.json()
            return json

    async def _get_tapes_year(self, session, year):
        """Get tape information for a year.

        Parameters:

            session: The aiohttp.ClientSession to make requests through
            year: The year to download tape information for

        Returns a list of dictionaries of tape information
        """
        tapes = []
        cursor = None
        n = 0

        while True:
            chunk = await self._get_chunk(session, year, cursor=cursor)
            n += chunk["count"]
            tapes.extend(chunk['items'])

            if n >= chunk["total"]:
                break

            cursor = chunk["cursor"]

        return tapes


class GDArchive:
    """ The Grateful Dead Collection on Archive.org """

    def __init__(self, dbpath=os.path.join(ROOT_DIR, 'metadata'), url='https://archive.org', reload_ids=False, sync=True, collection_name='GratefulDead'):
        """Create a new GDArchive.

        Parameters:

          dbpath: Path to filesystem location where data are stored
          url: URL for the internet archive
          reload_ids: If True, force re-download of tape data
          sync: If True use the slower synchronous downloader
        """
        self.url = url
        self.dbpath = dbpath
        self.collection_name = collection_name
        self.idpath = os.path.join(self.dbpath, f'{collection_name}_ids.json')
        #self.idpath_pkl = os.path.join(self.dbpath, f'{collection_name}_ids.pkl')
        self.set_data = GDSet(self.collection_name)
        self.downloader = (TapeDownloader if sync else AsyncTapeDownloader)(url, collection_name)
        self.tapes = self.load_tapes(reload_ids)
        self.tape_dates = self.get_tape_dates()
        self.dates = sorted(self.tape_dates.keys())

    def __str__(self):
        return self.__repr__()

    def __repr__(self):
        retstr = F"{self.collection_name} Archive with {len(self.tapes)} tapes on {len(self.dates)} dates from {self.dates[0]} to {self.dates[-1]} "
        return retstr

    def year_list(self):
        return sorted(set([datetime.datetime.strptime(x, '%Y-%m-%d').year for x in self.dates]))

    def best_tape(self, date):
        if isinstance(date, datetime.date):
            date = date.strftime('%Y-%m-%d')
        if date not in self.dates:
            logger.info("No Tape for date {}".format(date))
            return None
        return self.tape_dates[date][0]

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

    def write_tapes(self, tapes):
        os.makedirs(os.path.dirname(self.idpath), exist_ok=True)
        json.dump(tapes, open(self.idpath, 'w'))

    def load_tapes(self, reload_ids=False):
        if (not reload_ids) and os.path.exists(self.idpath):
            tapes = json.load(open(self.idpath, 'r'))
        else:
            logger.info("Loading Tapes from the Archive...this will take a few minutes")
            #tapes = self.downloader.get_tapes(self.year_list())
            tapes = self.downloader.get_all_tapes()
            self.write_tapes(tapes)
        return [GDTape(self.dbpath, tape, self.set_data) for tape in tapes]


class GDTape:
    """ A Grateful Dead Identifier Item -- does not contain tracks """

    def __init__(self, dbpath, raw_json, set_data):
        self.dbpath = dbpath
        self._playable_formats = ['Ogg Vorbis', 'VBR MP3', 'Shorten', 'MP3']  # had to remove Flac because mpv can't play them!!!
        self._breaks_added = False
        self.meta_loaded = False
        attribs = ['date', 'identifier', 'avg_rating', 'format', 'collection', 'num_reviews', 'downloads']
        for k, v in raw_json.items():
            if k in attribs:
                setattr(self, k, v)
        self.url_metadata = 'https://archive.org/metadata/' + self.identifier
        self.url_details = 'https://archive.org/details/' + self.identifier
        self.date = str((datetime.datetime.strptime(raw_json['date'], '%Y-%m-%dT%H:%M:%SZ')).date())
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
        score = 0
        if self.stream_only():
            score = score + 10
        if 'optd' in dir(config) and len(config.optd['FAVORED_TAPER']) > 0:
            if config.optd['FAVORED_TAPER'].lower() in self.identifier.lower():
                score = score + 3
        score = score + math.log(1+self.downloads)
        score = score + self.avg_rating - 2.0/math.sqrt(self.num_reviews)
        return score

    def contains_sound(self):
        return len(list(set(self._playable_formats) & set(self.format))) > 0

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
        date = datetime.datetime.strptime(self.date, '%Y-%m-%d').date()
        meta_path = os.path.join(self.dbpath, str(date.year), str(date.month), self.identifier+'.json')
        try:     # I used to check if file exists, but it may also be corrupt, so this is safer.
            page_meta = json.load(open(meta_path, 'r'))
        except BaseException:
            r = requests.get(self.url_metadata)
            logger.info("url is {}".format(r.url))
            if r.status_code != 200:
                logger.warn("error pulling data for {}".format(self.identifier))
                raise Exception('Download', 'Error {} url {}'.format(r.status_code, self.url_metadata))
            try:
                page_meta = r.json()
            except ValueError:
                logger.warn("Json Error {}".format(r.url))
                return None
            except BaseException:
                logger.warn("Json Error, probably")
                return None

        # self.reviews = page_meta['reviews'] if 'reviews' in page_meta.keys() else []
        for ifile in page_meta['files']:
            try:
                if ifile['format'] in self._playable_formats:
                    self.append_track(ifile)
            except KeyError:
                pass
            except Exception as e:   # TODO handle this!!!
                raise (e)
        os.makedirs(os.path.dirname(meta_path), exist_ok=True)
        json.dump(page_meta, open(meta_path, 'w'))
        self.meta_loaded = True
        # return page_meta
        self.insert_breaks()
        return

    def append_track(self, tdict):
        source = tdict['source']
        if source == 'original':
            orig = tdict['name']
        else:
            orig = tdict['original']
        trackindex = None
        for i, t in enumerate(self._tracks):
            if orig == t.original:  # add in alternate formats
                trackindex = i
                # make sure that this isn't a duplicate!!!
                t.add_file(tdict)
                return t
        self._tracks.append(GDTrack(tdict, self.identifier))

    def venue(self, tracknum=0):
        """return the venue, city, state"""
        # Note, if tracknum > 0, this could be a second show...check after running insert_breaks
        # 1970-02-14 is an example with 2 shows.
        sd = self.set_data
        if sd is None:
            return self.identifier
        venue_string = ""
        l = sd['location']
        if tracknum > 0:    # only pull the metadata if the query is about a late track.
            self.get_metadata()
            breaks = self._compute_breaks()
            if (len(breaks['location']) > 0) and (tracknum > breaks['location'][0]):
                l = sd['location2']
        venue_string = F"{l[0]}, {l[1]}, {l[2]}"
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
        except BaseException:
            pass
        lb_locations = []
        sb_locations = []
        locb_locations = []
        lb_locations = [j+1 for j, t in enumerate(tlist) if t in long_breaks]
        sb_locations = [j+1 for j, t in enumerate(tlist) if t in short_breaks]
        locb_locations = [j+1 for j, t in enumerate(tlist) if t in location_breaks]
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
        sbreakd = dict(list(breakd.items()) + [('title', 'Encore Break'), ('name', 'silence300.ogg')])
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
            tdict['title'] = 'unknown'
        for k, v in tdict.items():
            if k in attribs:
                setattr(self, k, v)
        # if these don't exist, i'll throw an error!
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
        if self.collection_name != 'GratefulDead':
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
        retstr = F"Grateful Dead set data"
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
        #self.default_audio_device = 'pulse'
        self.default_audio_device = 'auto'
        audio_device = self.default_audio_device
        self._set_property('audio-device', audio_device)
        self.download_when_possible = False
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
        pathname = os.path.join(self.tape.dbpath, 'audience')
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
                logger.warning(F"Current-ao is None")
                self.stop()
                return False
            self.pause()
            self._set_property('pause', False)
            self.wait_until_playing()
            self.pause()
        return True

    def play(self):
        if not retry_call(self.reset_audio_device, None):
            logger.warn("Failed to reset audio device when playing")
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
            time_remaining = self.get_prop('time-remaining')
            time_pos = self.get_prop('time-pos')
            if time_pos is None:
                time_pos = 0
            time_pos = max(0, time_pos)
            duration = self.get_prop('duration')
            #self.wait_for_property('duration', lambda v: v is not None)

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
            logger.info(F"Playlist not started")
            return None
        playlist_pos = self.get_prop('playlist-pos')
        paused = self.get_prop('pause')
        logger.info(F"Playlist at track {playlist_pos}, Paused {paused}")
        if self.raw.time_pos is None:
            logger.info(F"Track not started")
            return None
        duration = self.get_prop('duration')
        logger.info(F"duration: {duration}. time: {datetime.timedelta(seconds=int(self.raw.time_pos))}, time remaining: {datetime.timedelta(seconds=int(self.raw.time_remaining))}")
        return int(self.raw.time_remaining)

    def close(self): self.terminate()
