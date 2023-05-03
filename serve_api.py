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
from timemachine import GD

config.load_options()

config.optd = {
"COLLECTIONS": ["GratefulDead", "Phish", "PhilLeshandFriends", "TedeschiTrucksBand", "DeadAndCompany"],
"FAVORED_TAPER": {"UltraMatrix": 10, "miller": 5},
"PLAY_LOSSLESS": "false",
}
aa = Archivary.Archivary(collection_list=config.optd["COLLECTIONS"])

app = Flask(__name__)

def get_tapes(date):
    collection = request.args.get('collection',[])
    if collection != [] and collection not in aa.collection_list:
        return {'error':f'Invalid Collection {collection}'}
    if isinstance(collection, str):
        collection = [collection]
    tapes = aa.tape_dates[date]
    get_anything = True
    t = []
    if len(collection) > 0:
        get_anything = False
    for tape in tapes:
        if get_anything:
            t.append(tape)
            collection.append(tape.collection[0])
        elif collection[0] in tape.collection:
            t.append(tape)
    if len(t) == 0:
        return {'error':f'no tape for {collection} on {date}'}
    return t, collection

def get_tape(date):
    collection = request.args.get('collection','')
    if collection != '' and collection not in aa.collection_list:
        return {'error':f'Invalid Collection {collection}'}
    tapes = aa.tape_dates[date]
    t = None
    for tape in tapes:
        if collection == '':
            t = tape
            collection = t.collection[0]
            break
        elif collection in tape.collection:
            t = tape
            break
    if t is None:
        return {'error':f'no tape for {collection} on {date}'}
    return t, collection


@app.route("/")
def index():
    return "Deadstream API"

@app.route("/<name>")
def hello(name):
    return f"hello {escape(name)}"


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
    tapes,collections = get_tapes(date)
    tape_ids = [t.identifier for t in tapes]
    return dict(zip(tape_ids,collections))

if __name__ == "main":
    app.run(debug=True, host="0.0.0.0")

# tape = aa.best_tape("1992-05-05")
# tape = aa.best_tape("1996-11-18")
