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
import abc
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

from deadstream.timemachine import config

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

FAVORED_TAPER = {"UltraMatrix": 10, "miller": 5}


class MetaAPI(abc.ABC):
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

    def get_tapes(self, date, collection=None, tape_no=0):
        if collection is None:
            collection = list(self.api_dict.keys())[0]
        tapes = self.api_dict[collection].get_tapes(date)  # From the archive, not from cache
        return tapes

    def track_urls(self, date, collection=None, tape_no=0):
        if collection is None:
            collection = list(self.api_dict.keys())[0]
        tapes = self.get_tapes(date, collection, tape_no)
        if len(tapes) == 0:
            return {}
        if tape_no >= len(tapes):
            tape_no = 0
        tape = tapes[tape_no]
        track_urls = tape.track_urls  # This may be None if not yet loaded.
        if track_urls is None:
            track_urls = self.api_dict[collection].get_track_urls(tape)
        self.save_tapes_to_cloud(collection, date, tapes)  # Make non-blocking
        return track_urls

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

    def __init__(self, id: str, date: str, score: float, track_urls: dict):
        self.id = id
        self.date = date
        self.score = score
        self.track_urls = track_urls

    def __repr__(self):
        return f"Tape(id={self.id}, date={self.date}, score={self.score}, n_tracks={len(self.track_urls) if self.track_urls else 0})"


class PhishinAPI(MetaAPI):
    """For dealing with Phish.in API"""

    def __init__(self, collection="Phish"):
        self.collection = collection
        self.api = "https://phish.in/api/v2"
        self.tapes = None

    def get_tapes(self, date):
        raw_meta = self._get_raw_meta(date)
        tapes = [Tape(f'phishin_{raw_meta["id"]}', date, 5.0, self.get_track_urls(date))]
        return tapes

    def get_track_urls(self, date):
        raw_meta = self._get_raw_meta(date)
        track_urls = {m["title"]: m["mp3_url"] for m in raw_meta["tracks"]}
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


class ArchiveAPI(MetaAPI):
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

        colls = meta_item.get("collection", [])
        artist = self.collection
        # How to add in set breaks?

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

        return Tape(id, date, score, None)

    def get_track_urls(self, tape):
        # Getting the tape files is slow. We should return immediately, and do this in the background.
        tracks = self.get_tracks(tape.id)
        track_urls = {t["title"]: t["url"] for t in tracks}
        return track_urls
        """
        score = score + 3 * (self.title_fraction() - 1)  # reduce score for tapes without titles.
        score = score + min(20, len(tracks)) / 4
        return score
        """

    def get_tracks(self, identifier):
        meta_url = f"https://archive.org/metadata/{identifier}"
        resp = requests.get(meta_url)
        resp.raise_for_status()
        data = resp.json()
        tape_files = data.get("files", [])
        orig_tracks = []
        music_tracks = []
        orig_files = [x for x in tape_files if x.get("source") == "original" and x.get("format") in self._audio_formats]
        for fileinfo in orig_files:
            name = fileinfo["name"]
            title = fileinfo.get("title", name)
            try:
                trackno = int(fileinfo.get("track"))
            except (ValueError, TypeError):
                trackno = fileinfo.get("track")
            download = f"https://archive.org/download/{identifier}/{name}"
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
                        try:
                            trackno = int(fileinfo.get("track"))
                        except (ValueError, TypeError):
                            trackno = fileinfo.get("track")
                    download = f"https://archive.org/download/{identifier}/{name}"
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

        for track in self._tracks:
            if not isinstance(track.title, (str, bytes)):
                track.title = ""
            track.title = re.sub(r"gd\d{2}(?:\d{2})?-\d{2}-\d{2}[ ]*([td]\d*)*", "", track.title).strip()
            track.title = re.sub(r"(.flac)|(.mp3)|(.ogg)$", "", track.title).strip()
        self.insert_breaks()

        return music_tracks
        """

    def _make_track(self, ifile, orig_titles, orig_tracknums):
        raise NotImplementedError

    def title_fraction(self):
        n_tracks = len(self._tracks)
        lc = string.ascii_lowercase
        n_known = len(
            [
                t
                for t in self._tracks
                if t.title is not None and t.title != "unknown" and sum([x in lc for x in t.title.lower()]) > 4
            ]
        )
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
