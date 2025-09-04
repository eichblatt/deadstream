#!/usr/bin/python3
"""
Live Music Time Machine -- copyright 2025 Steve Eichblatt

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
from functools import lru_cache
from threading import Event, Lock, Thread

from io import StringIO
from operator import methodcaller
from typing import Callable, Optional

from deadstream.timemachine import cloud_utils

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

FAVORED_TAPER = {"UltraMatrix": 10, "miller": 5}


class MetaAPI:
    """A class to pull metadata about a given collection from multiple archives,
    and save the metadata in our google cloud storage."""

    def __init__(self, collections=["GratefulDead"], save_to_cloud=False):
        self.api_dict = self.set_api_dict(collections)
        self.save_to_cloud = save_to_cloud

    def set_api_dict(self, collections):
        if isinstance(collections, str):
            collections = [collections]

        api_dict = {k: PhishinAPI() if k.lower() == "phish" else ArchiveAPI(k) for k in collections}
        return api_dict

    def collections(self):
        return list(self.api_dict.keys())

    def get_vcs(self):
        for collection, api in self.api_dict.items():
            logger.info(f"Getting vcs for {collection}")
            vcs = api.get_vcs(collection)
            self.save_vcs_to_cloud(vcs)
        return vcs

    def save_vcs_to_cloud(self, vcs):
        # Save the vcs info to the metadata cache on the cloud. Non-blocking!
        if not self.save_to_cloud:
            return
        raise NotImplementedError

    def get_tapes(self, date, collection=None):
        if collection is None:
            collection = list(self.api_dict.keys())[0]
        tapes = self.api_dict[collection].get_tapes(date)  # From the archive, not from cache
        return tapes

    def track_urls(self, date, collection=None, tape_no=0):
        if collection is None:
            collection = list(self.api_dict.keys())[0]
        tapes = self.get_tapes(date, collection)
        if len(tapes) == 0:
            return {"tracklist": [], "urls": []}
        if tape_no >= len(tapes):
            tape_no = 0

        for tape in tapes:
            if tape.track_urls is None:
                tape.track_urls = self.api_dict[collection].get_track_urls(tape)
        self.save_tapes_to_cloud(collection, date, tapes)  # Make non-blocking
        return tapes[tape_no].track_urls

    def save_tapes_to_cloud(self, collection, date, tapes):
        # Save the tape info to the metadata cache on the cloud. Non-blocking!
        if not self.save_to_cloud:
            return
        raise NotImplementedError

    def get_all_collection_names(self):
        collection_names = []
        for api in self.api_dict.values():
            collection_names.extend(api.get_all_collection_names())


class Tape:
    """A simple class to store tape data. we may also need to add vcs data"""

    def __init__(self, id, collection, date, score: float, vcs, track_urls: dict, title=""):
        self.id = id
        self.collection = collection
        self.title = title
        self.date = date
        self.score = score
        self.vcs = ""
        self.track_urls = track_urls

    def __repr__(self):
        return f"Tape(id={self.id}, collection={self.collection}, date={self.date}, title={self.title}, score={self.score}, vcs={self.vcs}, n_tracks={len(self.track_urls['tracklist']) if self.track_urls else None})"


class PhishinAPI:
    """For dealing with Phish.in API"""

    def __init__(self, collection="Phish"):
        self.collection = collection
        self.api = "https://phish.in/api/v2"
        self.tapes = None

    def get_tapes(self, date):
        raw_meta = self._get_raw_meta(date)
        vcs = ""
        tapes = [Tape(f'phishin_{raw_meta["id"]}', "Phish", date, 5.0, vcs, self.get_track_urls(date))]
        return tapes

    def get_track_urls(self, date):
        raw_meta = self._get_raw_meta(date)
        previous_set_name = "Set 1"
        track_urls = {"tracklist": [], "urls": []}
        for m in raw_meta["tracks"]:
            track_name = m.get("title", "unknown")
            set_name = m.get("set_name", "Set 1")
            url = m.get("mp3_url", "")
            if set_name != previous_set_name:
                previous_set_name = set_name
                if set_name.startswith("Encore"):
                    track_urls["tracklist"].append("Encore Break")
                    track_urls["urls"].append("https://storage.googleapis.com/spertilo-data/sundry/silence0.ogg")
                else:
                    track_urls["tracklist"].append("Set Break")
                    track_urls["urls"].append("https://storage.googleapis.com/spertilo-data/sundry/silence600.ogg")
            track_urls["tracklist"].append(track_name)
            track_urls["urls"].append(url)
        return track_urls

    @lru_cache(maxsize=32)
    def _get_raw_meta(self, date):
        url = f"{self.api}/shows/{date}"
        r = requests.get(url)
        if r.status_code != 200:
            raise Exception("Download", f"Error {r.status_code} collecting data")
        raw_meta = r.json()
        return raw_meta

    def get_all_collection_names(self):
        return [self.collection]


class ArchiveAPI:
    """This class queries the archive.org API for metadata, generally about a given collection"""

    def __init__(self, collection="GratefulDead"):
        self.api = "https://archive.org/services/search/v1"
        self.collection = collection
        self.params = {
            "debug": "false",
            "xvar": "production",
            "total_only": "false",
            "count": "10000",
        }
        self._lossy_formats = ["Ogg Vorbis", "VBR MP3", "MP3"]
        self._audio_formats = ["Ogg Vorbis", "VBR MP3", "MP3", "Flac", "Shorten", "WAV"]
        self.tapes = None

    def get_all_collection_names(self):
        """
        get a list of all collection names within archive.org's etree collection.
        """
        current_rows = 0
        total = 0
        collection_names = []
        params = self.params | {
            "fields": "identifier, item_count,collection_size,downloads,num_favorites",
            "q": "collection:etree AND mediatype:collection",
        }
        first_time = True
        while first_time or current_rows < total:
            first_time = False
            r = requests.get(f"{self.api}/scrape", params=params)
            logger.debug(f"url is {r.url}")
            if r.status_code != 200:
                logger.error(f"Error {r.status_code} collecting data")
                raise Exception("Download", f"Error {r.status_code} collection")
            j = r.json()
            current_rows += j["count"]
            collection_names.extend([x["identifier"] for x in j["items"]])

        logger.info(f"Download {current_rows}/{total} collection names")
        return collection_names

    def get_tapes(self, date):
        raw_meta = self._get_date_meta(date)
        items = raw_meta.get("items", [])
        logger.info(f"Found {len(items)} tapes for {self.collection} on {date}")
        tapes = [self.make_tape(item, date) for item in items]
        self.tapes = sorted(tapes, key=lambda tape: tape.score, reverse=True)
        return self.tapes

    def make_tape(self, meta_item: dict, date: str):
        id = meta_item["identifier"]
        if "addeddate" in meta_item:
            if isinstance(meta_item["addeddate"], str):
                meta_item["addeddate"] = datetime.datetime.fromisoformat(meta_item["addeddate"][:-1])
            elif not isinstance(meta_item["addeddate"], datetime.datetime):
                raise ValueError(f"Unexpected addeddate type: {type(meta_item['addeddate'])}")

        collection = self.collection

        stream_only = "stream_only" in meta_item["collection"]
        avg_rating = float(meta_item.get("avg_rating", 2))
        num_reviews = int(meta_item.get("num_reviews", 1))
        downloads = int(meta_item.get("downloads", 1))
        download_rate = downloads / max(100, (datetime.datetime.now() - meta_item["addeddate"]).days)

        score = 3
        if stream_only:
            score = score + 10
        for taper, points in FAVORED_TAPER.items():
            if taper.lower() in id.lower():
                score = score + float(points)
        score = score + download_rate
        score = score + math.log(1 + downloads)
        # down-weigh avg_rating: it's usually about the show, not the tape.
        score = score + 0.5 * (avg_rating - 2.0 / math.sqrt(num_reviews))

        return Tape(id, collection, date, score, "", None)

    def update_tape_score(self, tape):
        score = tape.score
        if tape.track_urls is None:
            track_urls = self.get_track_urls(tape)
        tracks = tape.track_urls["tracklist"]
        score = score + 3 * (self.title_fraction(tracks) - 1)  # reduce score for tapes without titles.
        score = score + min(20, len(tracks)) / 4
        tape.score = score
        return score

    def get_track_urls(self, tape):
        # Getting the tape files is slow. We should return immediately, and do this in the background.
        track_data = self.get_track_data(tape)
        track_data = self.insert_set_breaks(tape.date, track_data)
        track_urls = {"tracklist": [t["title"] for t in track_data], "urls": [t["url"] for t in track_data]}
        tape.track_urls = track_urls
        self.update_tape_score(tape)
        return track_urls

    def insert_set_breaks(self, date, tracks):
        tlist = [t["title"] for t in tracks]
        set_breaks_already_in_tape = difflib.get_close_matches("Set Break", tlist, cutoff=0.6)
        if len(set_breaks_already_in_tape) > 0:
            return tracks

        replacements = {
            "GDTRFB": "Going Down the Road Feeling Bad",
            "FOTD": "Friend of the Devil",
            "EOTW": "Eyes of the World",
        }
        tlist = [replacements.get(n, n) for n in tlist]

        sb = SetBreaks()
        pre_longbreak_tracks = sb.longbreaks(self.collection, date)
        pre_shortbreak_tracks = sb.shortbreaks(self.collection, date)
        if len(pre_longbreak_tracks) + len(pre_shortbreak_tracks) == 0:
            return tracks

        def strings_match_case_insensitive(s1, s2, threshold=0.7):
            s1 = s1.lower()
            s2 = s2.lower()
            ratio = difflib.SequenceMatcher(None, s1, s2).ratio()
            return ratio >= threshold

        tracks_with_breaks = []
        longbreak_path = "https://storage.googleapis.com/spertilo-data/sundry/silence600.ogg"
        shortbreak_path = "https://storage.googleapis.com/spertilo-data/sundry/silence0.ogg"
        for i, track in enumerate(tracks[:-1]):
            tracks_with_breaks.append(track)
            track_name = track["title"].lower()

            # Check if this track should be followed by a set break
            for break_track in pre_longbreak_tracks:
                if strings_match_case_insensitive(break_track, track_name, threshold=0.7):
                    # Insert a set break after this track
                    tracks_with_breaks.append({"track": None, "title": "Set Break", "url": longbreak_path})
                    break
            for break_track in pre_shortbreak_tracks:
                if strings_match_case_insensitive(break_track, track_name, threshold=0.7):
                    # Insert a set break after this track
                    tracks_with_breaks.append({"track": None, "title": "Encore Break", "url": shortbreak_path})
                    break
        tracks_with_breaks.append(tracks[-1])
        return tracks_with_breaks

    def _get_track_data(self, tape_id):
        meta_url = f"https://archive.org/metadata/{tape_id}"
        resp = requests.get(meta_url)
        resp.raise_for_status()
        data = resp.json()
        return data

    def get_track_data(self, tape):
        data = self._get_track_data(tape.id)
        tape_files = data.get("files", [])
        orig_tracks = []
        music_tracks = []
        venue = data.get("metadata", {}).get("venue", "")
        city_state = data.get("metadata", {}).get("coverage", " , ")
        tape.vcs = f"{venue}, {city_state}"
        orig_files = [x for x in tape_files if x.get("source") == "original" and x.get("format") in self._audio_formats]
        for fileinfo in orig_files:
            name = fileinfo["name"]
            title = fileinfo.get("title", name)
            try:
                trackno = int(fileinfo.get("track"))
            except (ValueError, TypeError):
                trackno = fileinfo.get("track")
            download = f"https://archive.org/download/{tape.id}/{name}"
            orig_tracks.append({"track": trackno, "title": title, "url": download})

        while len(music_tracks) == 0:
            for format in self._lossy_formats:
                music_files = [x for x in tape_files if x.get("format") == format]
                for fileinfo in music_files:
                    name = fileinfo["name"]
                    base_name = os.path.splitext(name)[0]  # Get filename without extension

                    # Look for matching original track
                    matching_orig = None
                    for orig in orig_tracks:
                        orig_name = os.path.splitext(os.path.basename(orig["url"]))[0]
                        if orig_name == base_name:
                            matching_orig = orig
                            break

                    # Use original track data if found, otherwise use ogg file data
                    if matching_orig:
                        title = matching_orig["title"]
                        trackno = matching_orig["track"]
                    else:
                        title = fileinfo.get("title", name)
                        if not isinstance(title, (str, bytes)):
                            title = ""
                        title = re.sub(r"gd\d{2}(?:\d{2})?-\d{2}-\d{2}[ ]*([td]\d*)*", "", title).strip()
                        title = re.sub(r"(.flac)|(.mp3)|(.ogg)$", "", title).strip()
                        try:
                            trackno = int(fileinfo.get("track"))
                        except (ValueError, TypeError):
                            trackno = fileinfo.get("track")
                    title = re.sub(r"^\d+[\s\.\-_]+", "", title).strip()
                    download = f"https://archive.org/download/{tape.id}/{name}"
                    music_tracks.append({"track": trackno, "title": title, "url": download})
                if len(music_tracks) > 0:
                    break

        # sort by track number, falling back to filename order
        music_tracks.sort(key=lambda t: t["track"] or 0)
        return music_tracks

        """
        try:
            self.venue_name = tape_files["metadata"]["venue"]
            self.coverage = tape_files["metadata"]["coverage"]
        except Exception:
            # logger.warn(f"Failed to read venue, city, state from metadata. {self.meta_path}")
            pass

        return music_tracks
        """

    def _make_track(self, ifile, orig_titles, orig_tracknums):
        raise NotImplementedError

    def title_fraction(self, tracklist):
        n_tracks = len(tracklist)
        lc = string.ascii_lowercase
        n_known = len([t for t in tracklist if t is not None and t != "unknown" and sum([x in lc for x in t.lower()]) > 4])
        return (1 + n_known) / (1 + n_tracks)

    @lru_cache(maxsize=32)
    def _get_date_meta(self, date):
        url = f"{self.api}/scrape"
        fields = ",".join(
            [
                "identifier",
                "date",
                "avg_rating",
                "num_reviews",
                "num_favorites",
                "stars",
                "downloads",
                "files_count",
                "format",
                "collection",
                "source",
                "subject",
                "type",
                "addeddate",
            ]
        )
        sorts = ",".join(["date asc", "avg_rating desc", "num_favorites desc", "downloads desc"])
        query = f"collection:{self.collection} AND date:[{date} TO {date}]"
        params = self.params | {"sorts": sorts, "fields": fields, "q": query}
        r = requests.get(url, params=params)
        if r.status_code != 200:
            raise Exception("Download", f"Error {r.status_code} collecting data")
        raw_meta = r.json()
        if raw_meta["count"] < raw_meta["total"]:
            logger.warning(f"Only {raw_meta['count']} of {raw_meta['total']} tapes found for {self.collection} on {date}")
        return raw_meta

    def get_all_collection_names(self):
        raise NotImplementedError


class SetBreaks:
    """Set Information from a Grateful Dead date"""

    def __init__(self):
        self.asd = {}
        self.set_rows = []
        response = requests.get("https://storage.googleapis.com/spertilo-data/sundry/set_breaks.csv")
        response.raise_for_status()
        csv_buffer = StringIO(response.text)
        r = list(csv.reader(csv_buffer))
        headers = r[0]
        for row in r[1:]:
            d = dict(zip(headers, row))
            current_row = Set_row(d)
            self.set_rows.append(current_row)

        # self.set_data = set_data

    def __str__(self):
        return self.__repr__()

    def __repr__(self):
        retstr = "Set Data"
        return retstr

    def get_artist_set_dict(self, artist):
        if artist in self.asd.keys():
            return self.asd[artist]

        self.asd[artist] = {}
        artist_rows = [sd for sd in self.set_rows if sd.artist == artist]
        for s in artist_rows:
            if not s.date in self.asd[artist].keys():
                self.asd[artist][s.date] = [s]
            else:
                self.asd[artist][s.date].append(s)

        return self.asd[artist]

    def get_date(self, artist, date):
        return Date_info(self.get_artist_set_dict(artist).get(date, []))

    def multi_location(self, artist, date):
        d = self.get_date(artist, date)
        return d.n_locations > 1

    def location(self, artist, date):
        d = self.get_date(artist, date)
        return d.location

    def shortbreaks(self, artist, date):
        d = self.get_date(artist, date)
        return d.shortbreaks

    def longbreaks(self, artist, date):
        d = self.get_date(artist, date)
        return d.longbreaks

    def location2(self, artist, date):
        d = self.get_date(artist, date)
        if self.multi_location(artist, date):
            return d.location2
        else:
            return None

    def locationbreaks(self, artist, date):
        d = self.get_date(artist, date)
        if self.multi_location(artist, date):
            return d.locationbreak
        else:
            return None


class Set_row:
    """Set Information from a Grateful Dead or (other collection) date"""

    def __init__(self, data_row):
        for elem in [
            "date",
            "artist",
            "time",
            "song",
            "venue",
            "city",
            "state",
            "break_length",
            "show_set",
            "time",
            "song_n",
            "isong",
            "next_set",
            "Nevents",
            "ievent",
        ]:
            setattr(self, elem, data_row.get(elem, ""))
        self.start_time = datetime.time.fromisoformat(self.time) if len(self.time) > 0 else None

    def __repr__(self):
        retstr = f"{self.artist} {self.date}: {self.venue} {self.city}, {self.state}. {self.show_set} {self.song} "
        return retstr


class Date_info:
    """Date Information from a Grateful Dead or (other collection) date"""

    def __init__(self, set_rows):
        self.n_sets = len(set_rows)
        self.date = set_rows[0].date if self.n_sets > 0 else ""
        self.locationbreak = []
        self.longbreaks = []
        self.shortbreaks = []
        self.location = ()
        self.n_locations = 0
        for row in set_rows:
            prevsong = ""
            if int(row.ievent) == 1:
                self.location = (row.venue, row.city, row.state)
                self.n_locations = 1
                prevsong = row.song
            if int(row.ievent) == 2:
                self.n_locations = 2
                self.location2 = (row.venue, row.city, row.state)
                self.locationbreak = [prevsong]
            if row.break_length == "long":
                self.longbreaks.append(row.song)
            if row.break_length == "short":
                self.shortbreaks.append(row.song)

    def __repr__(self):
        retstr = (
            f"{self.date} {self.location} -- {self.n_sets} Rows. Long breaks:{self.longbreaks}. Short breaks {self.shortbreaks}"
        )
        return retstr
