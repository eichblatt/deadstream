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
import difflib
import logging
import math
import os
import re
import datetime
import requests
import string
from functools import lru_cache

from io import StringIO
from typing import Callable, Optional

from deadstream.timemachine import cloud_utils

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

FAVORED_TAPER = {"UltraMatrix": 10, "miller": 5}


class MetaAPI:
    """A class to pull metadata about a given collection from multiple archives,
    and save the metadata in our google cloud storage."""

    def __init__(self, collections=["GratefulDead"], save_to_cloud=False, bucket_name=None):
        self.api_dict = self.set_api_dict(collections)
        cloud_utils.SAVE_TO_CLOUD = save_to_cloud
        self.bucket_name = bucket_name if bucket_name is not None else cloud_utils.BUCKET_NAME

    def set_bucket_name(self, bucket_name):
        self.bucket_name = bucket_name
        return self.bucket_name

    def set_api_dict(self, collections):
        if isinstance(collections, str):
            collections = [collections]

        api_dict = {k: PhishinAPI() if k.lower() == "phish" else ArchiveAPI(k) for k in collections}
        return api_dict

    def collections(self):
        return list(self.api_dict.keys())

    def get_collection_vcs(self, clobber=False):
        vcs_dict = {}
        for collection, api in self.api_dict.items():
            logger.info(f"Getting vcs for {collection}")
            existing_data = {}
            if not clobber:
                try:
                    cloudpath = f"vcs/{collection}_vcs.json"
                    existing_data = cloud_utils.read_json(cloudpath)
                except Exception as e:
                    logger.info(f"No existing vcs data for {collection}: {e}")
            new_vcs = api.get_collection_vcs(collection, existing_data)
            vcs = existing_data | new_vcs
            outpath = self.save_collection_vcs_to_cloud(collection, vcs)
            vcs_dict[collection] = vcs
        return vcs_dict

    def save_collection_vcs_to_cloud(self, collection, vcs):
        # Save the vcs info to the metadata cache on the cloud. Non-blocking!
        if len(vcs) == 0:
            logger.warning(f"No vcs data to save for {collection}")
        outpath = f"vcs/{collection}_vcs.json"
        assert isinstance(vcs, dict)
        if not cloud_utils.SAVE_TO_CLOUD:
            return outpath
        logger.debug(f"Saving vcs for {collection} to {outpath} on cloud")
        cloud_utils.write_json(vcs, outpath, bucket_name=self.bucket_name)
        return outpath

    def get_tapes(self, date, collection=None):
        collections = list(self.api_dict.keys())
        tape_dict = {}
        for collection in collections:
            tapes = self.api_dict[collection].get_tapes(date)  # From the archive, not from cache
            tape_dict[collection] = tapes
        if len(collections) == 1:
            return tape_dict[collections[0]]
        return tape_dict

    def track_urls(self, date, collection=None, tape_no=0):
        if collection is None:
            collection = list(self.api_dict.keys())[0]
        logger.debug(f"Getting track URLs for {date} from {collection}, tape_no {tape_no}")
        tapes = self.get_tapes(date, collection)
        if len(tapes) == 0:
            logger.debug(f"No tapes found for {date} in {collection}")
            return Tape(
                id="none",
                collection=collection,
                date=date,
                score=0,
                vcs="",
                track_urls={"tracklist": [], "urls": []},
                title="No Tape Found",
            )
        if tape_no >= len(tapes):
            tape_no = 0

        for tape in tapes:
            if tape.track_urls is None:
                tape.track_urls = self.api_dict[collection].get_track_urls(tape)
        self.save_tapes_to_cloud(tapes)  # Make non-blocking
        return tapes[tape_no]

    def save_tapes_to_cloud(self, tapes):
        # Save the tape info to the metadata cache on the cloud. Non-blocking!
        if not cloud_utils.SAVE_TO_CLOUD:
            return
        seen = set()
        for tape in tapes:
            dirname = f"tapes/{tape.collection}/{tape.date}"
            if dirname not in seen:
                seen.add(dirname)
                # Write tape_ids.json to dirname
                tape_ids = [[t.id, t.score] for t in tapes]
                outpath = f"{dirname}/tape_ids.json"
                logger.info(f"Saving tape {tape_ids} to {outpath} on cloud")
                cloud_utils.write_json(tape_ids, outpath, bucket_name=self.bucket_name)
            tape_data = {
                "id": tape.id,
                "collection": tape.collection,
                "venue": tape.vcs,
                "tracklist": tape.tracklist,
                "urls": tape.urls,
            }
            filename = f"{dirname}/{tape.id}/trackdata.json"
            logger.debug(f"Saving tape {tape_data} to {filename} on cloud")
            cloud_utils.write_json(tape_data, filename, bucket_name=self.bucket_name)
        # raise NotImplementedError

    def get_all_collection_names(self):
        collection_names = []
        for api in [PhishinAPI(), ArchiveAPI("GratefulDead")]:
            collection_names.extend(api.get_all_collection_names())
        # self.save_collection_names_to_cloud(collection_names)
        return collection_names

    def save_collection_names_to_cloud(self, collection_names):
        if not cloud_utils.SAVE_TO_CLOUD:
            return
        filename = f"sundry/etree_collection_names.json"
        all_collection_names = {"items": collection_names}
        cloud_utils.write_json(all_collection_names, filename, bucket_name=self.bucket_name)
        return all_collection_names


class Tape:
    """A simple class to store tape data. we may also need to add vcs data"""

    def __init__(self, id, collection, date, score: float, vcs, track_urls: Optional[dict] = None, title=""):
        self.id = id
        self.collection = collection
        self.title = title
        self.date = date
        self.score = score
        self.vcs = vcs
        self.track_urls = track_urls

    @property
    def tracklist(self):
        return self.track_urls.get("tracklist", [])

    @property
    def urls(self):
        return self.track_urls.get("urls", [])

    def __repr__(self):
        return f"Tape(id={self.id}, collection={self.collection}, date={self.date}, title={self.title}, score={self.score}, vcs={self.vcs}, n_tracks={len(self.track_urls['tracklist']) if self.track_urls else None})"


class PhishinAPI:
    """For dealing with Phish.in API"""

    def __init__(self, collection="Phish"):
        self.collection = collection
        self.api = "https://phish.in/api/v2"
        self.tapes = None

    def get_tapes(self, date):
        logger.debug(f"PhishinAPI: Getting tapes for {date}")
        raw_meta = self._get_raw_meta(date)
        venue_meta = raw_meta.get("venue", {})
        vcs = (
            f"{venue_meta.get('name','Unknown venue')}, {venue_meta.get('city','location')} {venue_meta.get('state','Unknown')}"
        )
        title = raw_meta.get("tour_name", "Unknown Tour")
        tapes = [
            Tape(f'phishin_{raw_meta["id"]}', "Phish", date, 5.0, vcs=vcs, track_urls=self.get_track_urls(date), title=title)
        ]
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
        response = requests.get(url)
        response.raise_for_status()
        raw_meta = response.json()
        return raw_meta

    def get_all_collection_names(self):
        return [self.collection]

    def get_collection_vcs(self, collection, existing_data):
        logger.debug(f"getting vcs for {collection} from phish.in")

        max_date = "1970-01-01"
        if existing_data:
            max_date = max(existing_data.keys())
        start_date = (datetime.datetime.fromisoformat(max_date) + datetime.timedelta(days=1)).date().isoformat()
        logger.debug(f"start date is {start_date}")

        per_page = 1000
        page = 1
        total_pages = 1
        while page <= total_pages:
            params = {
                "page": f"{page}",
                "per_page": f"{per_page}",
                "sort": "date:desc",
                "audio_status": "any",
                "start_date": start_date,
                "liked_by_user": "false",
            }
            logger.debug(f"Getting vcs data from {self.api}/shows with params {params}")

            response = requests.get(f"{self.api}/shows", params=params)
            response.raise_for_status()
            json_data = response.json()
            total_pages = int(json_data.get("total_pages", 1))
            page = page + 1
            vcs_data = {}
            for show in json_data["shows"]:
                date = show["date"]
                venue = show.get("venue", {})
                vcs_data[date] = (
                    f"{venue.get('name','Unknown venue')}, {venue.get('city','location')} {venue.get('state','Unknown')}"
                )
        return vcs_data
        # Return all vcs info between start and end_date for this collection


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
            response = requests.get(f"{self.api}/scrape", params=params)
            response.raise_for_status()
            logger.debug(f"url is {response.url}")
            j = response.json()
            current_rows += j["count"]
            collection_names.extend([x["identifier"] for x in j["items"]])

        logger.info(f"Download {current_rows}/{total} collection names")
        return collection_names

    def get_tapes(self, date):
        raw_meta = self._get_meta_date_range(date, date)
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

        tape = Tape(id, collection, date, score, vcs="", track_urls=None, title="")
        logger.debug(f"Made tape: {tape}")
        return tape

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
        logger.debug(f"ArchiveAPI: Getting track URLs for tape {tape.id}")
        track_data = self.get_track_data(tape)
        track_data = self.insert_set_breaks(tape.date, track_data)
        track_urls = {"tracklist": [t["title"] for t in track_data], "urls": [t["url"] for t in track_data]}
        tape.track_urls = track_urls
        self.update_tape_score(tape)
        return track_urls

    def insert_set_breaks(self, date, tracks):
        logger.debug(f"ArchiveAPI: Inserting set breaks for tape on {date}")
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
        response = requests.get(meta_url)
        response.raise_for_status()
        data = response.json()
        return data

    def get_track_data(self, tape):
        logger.debug(f"ArchiveAPI: Getting track data for tape {tape.id}")
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
    def _get_meta_date_range(self, start_date, end_date):
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
        query = f"collection:{self.collection} AND date:[{start_date} TO {end_date}]"
        params = self.params | {"sorts": sorts, "fields": fields, "q": query}
        logger.debug(f"in _get_meta_date_range, url is {url} with params {params}")
        response = requests.get(url, params=params)
        response.raise_for_status()
        raw_meta = response.json()
        if raw_meta["count"] < raw_meta["total"]:
            logger.warning(f"Only {raw_meta['count']} of {raw_meta['total']} tapes found for {self.collection}")
        return raw_meta

    def get_collection_vcs(self, collection, existing_data):
        """Get the venue, city, state (vcs) info for all shows in this collection.
        Because getting this info is so slow, we will initially only save the dates and tape_ids. We can
        update the vcs info later by getting the tape info for the first tape on each date"""

        logger.debug(f"getting vcs for {collection} from archive.org")
        max_date = "1900-01-01"
        if existing_data:
            max_date = max(existing_data.keys())
            logger.debug(f"max date in existing data is {max_date}")
        start_date = (datetime.datetime.fromisoformat(max_date) + datetime.timedelta(days=1)).date().isoformat()

        total = 1
        count = 0
        vcs_data = {}

        while count < total:
            collection_meta = self._get_meta_date_range(start_date, datetime.date.max.isoformat())
            total = collection_meta["total"]
            count = collection_meta["count"]
            for item in collection_meta.get("items", []):
                date = item["date"]
                if "T" in date:
                    date = date.split("T")[0]
                try:
                    dt = datetime.datetime.fromisoformat(date)
                    date = dt.date().isoformat()
                except ValueError:
                    logger.warning(f"Invalid date format: {date}")
                    continue
                vcs_data[date] = item["identifier"]

        logger.debug(f"in get_collection_vcs, found {len(vcs_data)} new vcs entries for {collection}")
        return vcs_data


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
