# to run this:
# flask --app app2 run --host 0.0.0.0

import json
import logging
from flask import Flask


from markupsafe import escape
from flask import request
from flask import url_for
from deadstream.timemachine import MetaAPI
from deadstream.timemachine import cloud_utils

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

SAVE_TO_CLOUD = True

app = Flask(__name__)


@app.route("/")
def index():
    return "Deadstream API"


# This function does not need to be available publicly.
# I will run this in update_cloud_meta instead.
# @app.route("/all_collection_names/")
# def get_all_collection_names():
#    mapi = MetaAPI.MetaAPI(save_to_cloud=SAVE_TO_CLOUD)
#    collection_names = mapi.get_all_collection_names()
#    return {"collection_names": collection_names}


@app.route("/vcs/<collection>")
def vcs(collection):
    """
    load an archive collection and return a super-compressed version of the
    date, artist, venue, city, state
    which can be loaded by the player to save memory.
    """
    print(f"in vcs, collection:{collection}")
    vcs_data = {}
    try:
        mapi = MetaAPI.MetaAPI(collection, save_to_cloud=SAVE_TO_CLOUD)
        vcs_data = mapi.get_collection_vcs()
    except:
        pass
    finally:
        pass
    return vcs_data


@app.route("/track_urls/<date>")
def track_urls(date):
    # This function only works on one collection, but the "collections" param might be a list.
    # This is for backward compatibility, but we are only going to use the first collection.
    collections = request.args.get("collections", "GratefulDead").split(",")
    ntape = int(request.args.get("ntape", 0))
    if not isinstance(collections, list):
        print(f"collections is not a list! {collections}")
        collections = [collections]
    collection = collections[0]
    mapi = MetaAPI.MetaAPI(collection, save_to_cloud=SAVE_TO_CLOUD)
    tape = mapi.track_urls(date, tape_no=ntape)
    return {"collection": collection, "tape_id": tape.id, "tracklist": tape.tracklist, "urls": tape.urls}


@app.route("/tape_ids/<date>")
def tape_ids(date):
    collections = request.args.get("collections", "GratefulDead").split(",")
    mapi = MetaAPI.MetaAPI(collections, save_to_cloud=SAVE_TO_CLOUD)
    tape_dict = mapi.get_tapes(date)
    if len(collections) == 1:
        tape_dict = {collections[0]: tape_dict}
    # tape_ids = {k: v[0].id  for k, v in tape_dict.items()} # First tape only for compatibility?
    tape_ids = {k: [t.id for t in v] for k, v in tape_dict.items()}
    return tape_ids


if __name__ == "main":
    app.run(debug=True, host="0.0.0.0")
