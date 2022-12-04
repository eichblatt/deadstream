import datetime
import json
import os
import logging
import subprocess
import time

logger = logging.getLogger(__name__)
try:
    from timemachine import controls
except NotImplementedError:
    logger.warning(f"Failied to import controls")

OPTIONS_PATH = (os.path.join(os.getenv("HOME"), ".timemachine_options.txt"),)

optd = {}


def get_board_version():
    try:
        cmd = "board_version.sh"
        raw = subprocess.check_output(cmd, shell=True)
        raw = raw.decode()
        if raw == "version 2\n":
            return 2
    except Exception:
        return 1


# State variables
NOT_READY = -1
INIT = 0
READY = 1
PAUSED = 2
STOPPED = 3
PLAYING = 4
ENDED = 5
PLAY_STATE = INIT
# PLAY_STATES = ['Init','Ready','Paused','Stopped','Playing']
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
if get_board_version() == 2:
    rewind_pin = 21
else:
    rewind_pin = 3


def default_options():
    d = {}
    d["MODULE"] = "livemusic"
    d["COLLECTIONS"] = ["GratefulDead"]
    d["FAVORED_TAPER"] = ["miller"]
    d["AUTO_UPDATE_ARCHIVE"] = True
    d["UPDATE_ARCHIVE_ON_STARTUP"] = False
    d["PLAY_LOSSLESS"] = False
    d["ON_TOUR_ALLOWED"] = False
    d["PULSEAUDIO_ENABLE"] = False
    if controls.get_os_version() > 10:
        d["PULSEAUDIO_ENABLE"] = True
        d["BLUETOOTH_ENABLE"] = True
    d["DEFAULT_START_TIME"] = datetime.time(15, 0)
    d["TIMEZONE"] = "America/New_York"
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
            options[arg] = optd_to_save[arg]
    with open(OPTIONS_PATH, "w") as outfile:
        json.dump(options, outfile, indent=1)


def load_options(parms):
    global optd
    optd = default_options()
    tmpd = {}
    try:
        f = open(OPTIONS_PATH, "r")
        tmpd = json.loads(f.read())
        for k in optd.keys():
            logger.debug(f"Loading options key is {k}")
            try:
                if k in [
                    "AUTO_UPDATE_ARCHIVE",
                    "PLAY_LOSSLESS",
                    "PULSEAUDIO_ENABLE",
                    "ON_TOUR_ALLOWED",
                    "BLUETOOTH_ENABLE",
                    "UPDATE_ARCHIVE_ON_STARTUP",
                ]:  # make booleans.
                    tmpd[k] = tmpd[k].lower() == "true"
                    logger.debug(f"Booleans k is {k}")
                if k in ["COLLECTIONS", "FAVORED_TAPER"]:  # make lists from comma-separated strings.
                    logger.debug(f"lists k is {k}")
                    c = [x.strip() for x in tmpd[k].split(",") if x != ""]
                    if k == "COLLECTIONS":
                        c = ["Phish" if x.lower() == "phish" else x for x in c]
                    tmpd[k] = c
                if k in ["DEFAULT_START_TIME"]:  # make datetime
                    logger.debug(f"time k is {k}")
                    tmpd[k] = datetime.time.fromisoformat(tmpd[k])
            except Exception:
                logger.warning(f"Failed to set option {k}. Using {optd[k]}")
    except Exception:
        logger.warning(f"Failed to read options from {parms.options_path}. Using defaults")
    optd.update(tmpd)  # update defaults with those read from the file.
    logger.info(f"in load_options, optd {optd}")
    os.environ["TZ"] = optd["TIMEZONE"]
    time.tzset()
    led_cmd = 'sudo bash -c "echo default-on > /sys/class/leds/led1/trigger"'
    os.system(led_cmd)
    led_cmd = 'sudo bash -c "echo none > /sys/class/leds/led1/trigger"'
    logger.info(f"in load_options, running {led_cmd}")
    os.system(led_cmd)
