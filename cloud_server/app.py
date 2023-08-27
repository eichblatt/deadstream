# to run this:
# flask --app serve_api run --host 0.0.0.0

import sys
import time
from flask import Flask


from markupsafe import escape
from flask import request
from flask import url_for
from timemachine import Archivary
from timemachine import config

config.load_options()

config.optd = {
"COLLECTIONS": ["DeadAndCompany"], 
"FAVORED_TAPER": {"UltraMatrix": 10, "miller": 5},
"PLAY_LOSSLESS": "false",
}
aa = Archivary.Archivary(collection_list=config.optd["COLLECTIONS"])

app = Flask(__name__)


def intersect(lis1, lis2):
    return [x for x in lis1 if x in set(lis2)]

def xcept(lis1, lis2):
    return [x for x in lis1 if not x in set(lis2)]

def get_all_tapes(date):
    global aa
    collections = request.args.get('collections',[]).split(',')
    print(f"Collections is {collections}. Length {len(collections)}, aa.collection_list:{aa.collection_list}")
    colls = intersect(collections, aa.collection_list)
    if collections != [] and len(collections) > len(colls):
        colls_to_add = xcept(collections, aa.collection_list)
        print(f'Need to add collection {colls_to_add}')
        config.optd['COLLECTIONS'] = config.optd['COLLECTIONS'] + colls_to_add
        aa = Archivary.Archivary(collection_list=config.optd['COLLECTIONS'])
    tapes = aa.tape_dates[date]
    get_anything = True
    tape_collections = []
    t = []
    if len(collections) > 0:
        get_anything = False
    for tape in tapes:
        if get_anything:
            t.append(tape)
            tape_collections.append(tape.collection[0])
        else:
            matches = intersect(collections, tape.collection)
            if len(matches) > 0:
                t.append(tape)
                tape_collections.append(matches[0])
    if len(t) == 0:
        print(f'no tape for {collections} on {date}')
        return {'error':f'no tape for {collections} on {date}'}, []
    return t, tape_collections

def get_tape(date):
    tapes,tape_collections = get_all_tapes(date)
    ntape = int(request.args.get('ntape',0))
    collection = tape_collections[ntape]
    t = tapes[ntape]
    return t, collection


@app.route("/")
def index():
    return "Deadstream API"

@app.route("/all_collection_names/")
def get_all_collection_names():
    collection_names = aa.get_all_collection_names()
    return {'collection_names':collection_names}


@app.route("/venue/<date>")
def venue(date):
    t,collection = get_tape(date)
    venue = t.venue()
    return {'collection':collection,'venue':venue}

@app.route("/tracklist/<date>")
def tracklist(date):
    t,collection = get_tape(date)
    t.get_metadata()
    tl = [x.title for x in t.tracks()]
    return {'collection':collection,'tracklist':tl}

@app.route("/urls/<date>")
def urls(date):
    t, collection = get_tape(date)
    t.get_metadata()
    trks = t.tracks()
    result = [x.files[0]['url'] for x in trks]
    # result_dict = {x.title: x.files[0]['url'] for x in trks} 
    # print(f"tmp is {result_dict}")  # dict is returned in order, but received out of order?
    return {'collection':collection, 'urls':result}

@app.route("/tape_ids/<date>")
def tape_ids(date):
    tapes,collections = get_all_tapes(date)
    tape_ids = [t.identifier for t in tapes]
    return list(zip(collections,tape_ids))

@app.route("/vcs/<collection>")
def vcs(collection):
    """
    load an archive collection and return a super-compressed version of the
    date, artist, venue, city, state
    which can be loaded by the player to save memory.
    """
    print(f"in vcs, collection:{collection}")
    coptd = config.optd['COLLECTIONS']
    vcs_data = {}
    try:
        config.optd['COLLECTIONS'] = [collection]
        a = Archivary.Archivary(collection_list=config.optd['COLLECTIONS'])
        vcs_data = {d: a.tape_dates[d][0].venue() for d in a.dates}
    except:
        pass
    finally:
        config.optd['COLLECTIONS'] = coptd
    return {collection:vcs_data}


if __name__ == "main":
    app.run(debug=True, host="0.0.0.0")

# tape = aa.best_tape("1992-05-05")
# tape = aa.best_tape("1996-11-18")
