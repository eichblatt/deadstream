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

# config.optd = {
#   "COLLECTIONS": ["GratefulDead", "Phish", "PhilLeshandFriends", "TedeschiTrucksBand", "DeadAndCompany"],
#   "FAVORED_TAPER": {"UltraMatrix": 10, "miller": 5},
#   "PLAY_LOSSLESS": "false",
# }
aa = Archivary.Archivary(collection_list=config.optd["COLLECTIONS"])

app = Flask(__name__)
@app.route("/")
def index():
    return "Deadstream API"

@app.route("/<name>")
def hello(name):
    return f"hello {escape(name)}"

@app.route("/venue/<date>")
def venue(date):
    venue = aa.best_tape(date).venue()
    return {'venue':venue}

@app.route("/tracklist/<date>")
def tracklist(date):
    t = aa.best_tape(date)
    t.get_metadata()
    tl = [x.title for x in t.tracks()]
    return {'tracklist':tl}

@app.route("/urls/<date>")
def urls(date):
    t = aa.best_tape(date)
    t.get_metadata()
    trks = t.tracks()
    result = [x.files[0]['url'] for x in trks]
    # result_dict = {x.title: x.files[0]['url'] for x in trks} 
    # print(f"tmp is {result_dict}")  # dict is returned in order, but received out of order?
    return {'urls':result}



@app.route("/tapes/<date>")
def tapes(date):
    tapes = aa.tape_dates[date]
    return {'tapes':tapes}

if __name__ == "main":
    app.run(debug=True, host="0.0.0.0")

# tape = aa.best_tape("1992-05-05")
# tape = aa.best_tape("1996-11-18")
