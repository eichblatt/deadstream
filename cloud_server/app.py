# to run this:
# flask --app serve_api run --host 0.0.0.0

import json
import sys
import time
from flask import Flask


from markupsafe import escape
from flask import request
from flask import url_for
from timemachine import Archivary
from timemachine import config

from google.cloud import storage

config.load_options()

config.optd = {
    "COLLECTIONS": ["GratefulDead", "DeadAndCompany", "Phish"],
    "FAVORED_TAPER": {"UltraMatrix": 10, "miller": 5, "fix": 1, "prefm": 4},
    "PLAY_LOSSLESS": False,
}
print(config.optd)
aa = Archivary.Archivary(collection_list=config.optd["COLLECTIONS"])
storage_client = storage.Client(project="able-folio-397115")
bucket = storage_client.bucket("spertilo-data")
SAVE_TO_CLOUD = True
# SAVE_TO_CLOUD = False

app = Flask(__name__)


def intersect(lis1, lis2):
    return [x for x in lis1 if x in set(lis2)]


def xcept(lis1, lis2):
    return [x for x in lis1 if not x in set(lis2)]


def save_tapeids_in_cloud(tids, date, collection):
    if not SAVE_TO_CLOUD:
        return ""
    tids_string = json.dumps(tids, indent=1)
    if len(tids_string) == 0:
        return tids_string
    tids_blob_name = f"tapes/{collection}/{date}/tape_ids.json"
    tids_blob = bucket.blob(tids_blob_name)
    tids_blob.upload_from_string(tids_string)
    return tids_string


def save_tape_data_in_cloud(t, date, collection, i_tape):
    if not SAVE_TO_CLOUD:
        return ""
    id = t.identifier
    tracks = t.tracks()
    trackdata = {
        "id": id,
        "collection": collection,
        "venue": t.venue(),
        "tracklist": [x.title for x in tracks],
        "urls": [x.files[0]["url"] for x in tracks],
    }
    trackdata_string = json.dumps(trackdata, indent=1)

    if len(trackdata_string) > 0:
        trackdata_blob_name = f"tapes/{collection}/{date}/{id}/trackdata.json"
        trackdata_blob = bucket.blob(trackdata_blob_name)
        trackdata_blob.upload_from_string(trackdata_string)
    return ""


def save_vcs_in_cloud(vcs_data, collection):
    if not SAVE_TO_CLOUD:
        return ""
    print(vcs_data)
    vcs_string = json.dumps(vcs_data, indent=1)

    if len(vcs_string) > 0:
        vcs_blob_name = f"vcs/{collection}_vcs.json"
        vcs_blob = bucket.blob(vcs_blob_name)
        vcs_blob.upload_from_string(vcs_string)
    return ""


def get_all_tapes(date):
    global aa
    collections = request.args.get("collections", []).split(",")
    print(f"Collections is {collections}. Length {len(collections)}, aa.collection_list:{aa.collection_list}")
    colls = intersect(collections, aa.collection_list)
    if collections != [] and len(collections) > len(colls):
        colls_to_add = xcept(collections, aa.collection_list)
        print(f"Need to add collection {colls_to_add}")
        config.optd["COLLECTIONS"] = config.optd["COLLECTIONS"] + colls_to_add
        aa = Archivary.Archivary(collection_list=config.optd["COLLECTIONS"])
    tapes = aa.tape_dates[date]
    get_anything = True
    tape_collections = []
    t = []

    if len(collections) > 0:
        get_anything = False
    for i_tape, tape in enumerate(tapes):
        if get_anything:
            t.append(tape)
            this_collection = tape.collection[0]
            tape_collections.append(this_collection)
            save_tape_data_in_cloud(tape, date, this_collection, i_tape)
        else:
            matches = intersect(collections, tape.collection)
            if len(matches) > 0:
                this_collection = matches[0]
                t.append(tape)
                tape_collections.append(this_collection)
                save_tape_data_in_cloud(tape, date, this_collection, i_tape)
    if len(t) == 0:
        print(f"no tape for {collections} on {date}")
        return {"error": f"no tape for {collections} on {date}"}, []
    else:
        tids = [[x.identifier, x.compute_score()] for x in t]
        save_tapeids_in_cloud(tids, date, this_collection)

    return t, tape_collections


def get_tape(date):
    tapes, tape_collections = get_all_tapes(date)
    ntape = int(request.args.get("ntape", 0))
    collection = tape_collections[ntape]
    t = tapes[ntape]
    return t, collection


@app.route("/")
def index():
    return "Deadstream API"


@app.route("/all_collection_names/")
def get_all_collection_names():
    collection_names = aa.get_all_collection_names()
    return {"collection_names": collection_names}


@app.route("/venue/<date>")
def venue(date):
    t, collection = get_tape(date)
    venue = t.venue()
    return {"collection": collection, "venue": venue}


@app.route("/track_urls/<date>")
def track_urls(date):
    t, collection = get_tape(date)
    t.get_metadata()
    trks = t.tracks()
    tl = [x.title for x in trks]
    urls = [x.files[0]["url"] for x in trks]
    return {"collection": collection, "tracklist": tl, "urls": urls, "tape_id": t.identifier}


@app.route("/tracklist/<date>")
def tracklist(date):
    t, collection = get_tape(date)
    t.get_metadata()
    tl = [x.title for x in t.tracks()]
    return {"collection": collection, "tracklist": tl}


@app.route("/urls/<date>")
def urls(date):
    t, collection = get_tape(date)
    t.get_metadata()
    trks = t.tracks()
    result = [x.files[0]["url"] for x in trks]
    return {"collection": collection, "urls": result}


@app.route("/tape_ids/<date>")
def tape_ids(date):
    tapes, collections = get_all_tapes(date)
    tape_ids = [t.identifier for t in tapes]
    return dict(zip(collections, tape_ids))


@app.route("/vcs/<collection>")
def vcs(collection):
    """
    load an archive collection and return a super-compressed version of the
    date, artist, venue, city, state
    which can be loaded by the player to save memory.
    """
    print(f"in vcs, collection:{collection}")
    coptd = config.optd["COLLECTIONS"]
    vcs_data = {}
    try:
        config.optd["COLLECTIONS"] = [collection]
        a = Archivary.Archivary(collection_list=config.optd["COLLECTIONS"])
        vcs_data = {d: a.tape_dates[d][0].venue() for d in a.dates}
        save_vcs_in_cloud(vcs_data, collection)
    except:
        pass
    finally:
        pass
        # config.optd['COLLECTIONS'] = coptd
    return {collection: vcs_data}


if __name__ == "main":
    app.run(debug=True, host="0.0.0.0")

# tape = aa.best_tape("1992-05-05")
# tape = aa.best_tape("1996-11-18")
