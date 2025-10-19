import datetime
import json
import os
import logging
import subprocess
import time


logger = logging.getLogger(__name__)

ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
OPTIONS_PATH = os.path.join(os.getenv("HOME"), ".timemachine_options.txt")

optd = {}


# State variables
NOT_READY = -1
INIT = 0
READY = 1
PAUSED = 2
STOPPED = 3
PLAYING = 4
ENDED = 5
PLAY_STATE = INIT
# PLAY_STATES = ['Not Ready', 'Init','Ready','Paused','Stopped','Playing', 'Ended']
SELECT_STAGED_DATE = False
DATE = None
VENUE = None
ARTIST = None
STAGED_DATE = None
PAUSED_AT = None
WOKE_AT = None
OTHER_YEAR = None
DATE_RANGE = None

ON_TOUR = False
EXPERIENCE = False
TOUR_YEAR = None
TOUR_STATE = 0

# Hardware pins

year_pins = (22, 16, 23)  # cl, dt, sw
month_pins = (5, 12, 6)
day_pins = (17, 13, 27)


screen_led_pin = 19

select_pin = 4  # pin 4 ok w/ Sound card
play_pause_pin = 20  # pin 18 interferes with sound card
stop_pin = 2  # from the I2C bus (may need to connect to ground)
ffwd_pin = 26  # pin 26 ok with sound card.


def default_options():
    d = {}
    d["COLLECTIONS"] = ["GratefulDead"]
    d["FAVORED_TAPER"] = ["miller"]
    d["PLAY_LOSSLESS"] = False
    return d


def save_options(optd_to_save):
    logger.debug(f"in save_options. optd {optd_to_save}")
    options = {}
    f = open(OPTIONS_PATH, "r")
    tmpd = json.loads(f.read())
    if optd_to_save["COLLECTIONS"] == None:
        optd_to_save["COLLECTIONS"] = tmpd["COLLECTIONS"]
    for arg in optd_to_save.keys():
        if arg == arg.upper():
            if arg == "DEFAULT_START_TIME":
                if isinstance(optd_to_save[arg], datetime.time):
                    optd_to_save[arg] = datetime.time.strftime(optd_to_save[arg], "%H:%M:%S")
            elif isinstance(optd_to_save[arg], (list, tuple)):
                optd_to_save[arg] = ",".join(optd_to_save[arg])
            elif isinstance(optd_to_save[arg], (bool)):
                optd_to_save[arg] = str(optd_to_save[arg]).lower()
            elif isinstance(optd_to_save[arg], dict):
                optd_to_save[arg] = ",".join([f"{k}:{v}" for k, v in optd_to_save[arg].items()])
            options[arg] = optd_to_save[arg]
    with open(OPTIONS_PATH, "w") as outfile:
        json.dump(options, outfile, indent=1)


def load_options():
    global optd
    optd = default_options()
    tmpd = {}
    optd.update(tmpd)  # update defaults with those read from the file.
