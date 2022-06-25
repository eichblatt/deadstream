#!/usr/bin/python3
"""
    Grateful Dead Time Machine -- copyright 2021 Steve Eichblatt

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
import datetime
import json
import logging
import optparse
import os
import random
import re
import subprocess
import threading
import sys
import time
from threading import Event, Lock
from time import sleep

from gpiozero import RotaryEncoder
from tenacity import retry
from tenacity.stop import stop_after_delay
from typing import Callable

from timemachine import Archivary, config, controls, GD

parser = optparse.OptionParser()
parser.add_option('--box', dest='box', type="string", default='v1', help="v0 box has screen at 270. [default %default]")
parser.add_option('--dbpath',
                  default=os.path.join(GD.ROOT_DIR, 'metadata'),
                  help="path to database [default %default]")
parser.add_option('--options_path',
                  default=os.path.join(os.getenv('HOME'), '.timemachine_options.txt'),
                  help="path to options file [default %default]")
parser.add_option('--test_update',
                  action="store_true",
                  default=False,
                  help="test that software update succeeded[default %default]")
parser.add_option('--pid_to_kill',
                  type='int',
                  default=None,
                  help="process id to kill during test_update [default %default]")
parser.add_option('-d', '--debug',
                  type="int",
                  default=0,
                  help="If > 0, don't run the main script on loading [default %default]")
parser.add_option('-v', '--verbose',
                  action="store_true",
                  default=False,
                  help="Print more verbose information [default %default]")
parms, remainder = parser.parse_args()

logging.basicConfig(format='%(asctime)s.%(msecs)03d %(levelname)s: %(name)s %(message)s',
                    level=logging.INFO,
                    datefmt='%Y-%m-%d %H:%M:%S')
logger = logging.getLogger(__name__)

if parms.debug > 0:
    logger.setLevel(logging.DEBUG)

PWR_LED_ON = False


def default_options():
    d = {}
    d['MODULE'] = 'livemusic'
    d['COLLECTIONS'] = ['GratefulDead']
    d['FAVORED_TAPER'] = ['miller']
    d['AUTO_UPDATE_ARCHIVE'] = True
    d['PLAY_LOSSLESS'] = False
    d['ON_TOUR_ALLOWED'] = False
    d['PULSEAUDIO_ENABLE'] = False
    if controls.get_os_version() > 10:
        d['PULSEAUDIO_ENABLE'] = True
        d['BLUETOOTH_ENABLE'] = True
    d['DEFAULT_START_TIME'] = datetime.time(15, 0)
    d['TIMEZONE'] = 'America/New_York'
    return d


def load_options(parms):
    config.optd = default_options()
    optd = {}
    try:
        f = open(parms.options_path, 'r')
        tmpd = json.loads(f.read())
        for k in config.optd.keys():
            logger.debug(f"Loading options key is {k}")
            try:
                if k in ['AUTO_UPDATE_ARCHIVE', 'PLAY_LOSSLESS', 'PULSEAUDIO_ENABLE', 'ON_TOUR_ALLOWED', 'BLUETOOTH_ENABLE']:  # make booleans.
                    tmpd[k] = tmpd[k].lower() == 'true'
                    logger.debug(f"Booleans k is {k}")
                if k in ['COLLECTIONS', 'FAVORED_TAPER']:   # make lists from comma-separated strings.
                    logger.debug(f"lists k is {k}")
                    c = [x.strip() for x in tmpd[k].split(',') if x != '']
                    if k == 'COLLECTIONS':
                        c = ['Phish' if x.lower() == 'phish' else x for x in c]
                    tmpd[k] = c
                if k in ['DEFAULT_START_TIME']:            # make datetime
                    logger.debug(f"time k is {k}")
                    tmpd[k] = datetime.time.fromisoformat(tmpd[k])
            except Exception:
                logger.warning(F"Failed to set option {k}. Using {config.optd[k]}")
        optd = tmpd
    except Exception:
        logger.warning(F"Failed to read options from {parms.options_path}. Using defaults")
    config.optd.update(optd)  # update defaults with those read from the file.
    logger.info(F"in load_options, optd {optd}")
    os.environ['TZ'] = config.optd['TIMEZONE']
    time.tzset()
    led_cmd = 'sudo bash -c "echo default-on > /sys/class/leds/led1/trigger"'
    os.system(led_cmd)
    if not PWR_LED_ON:
        led_cmd = 'sudo bash -c "echo none > /sys/class/leds/led1/trigger"'
    logger.info(F"in load_options, running {led_cmd}")
    os.system(led_cmd)


def save_options(optd):
    logger.debug(F"in save_options. optd {optd}")
    options = {}
    f = open(parms.options_path, 'r')
    tmpd = json.loads(f.read())
    if optd['COLLECTIONS'] == None:
        optd['COLLECTIONS'] = tmpd['COLLECTIONS']
    for arg in optd.keys():
        if arg == arg.upper():
            if arg == 'DEFAULT_START_TIME':
                if isinstance(optd[arg], datetime.time):
                    optd[arg] = datetime.time.strftime(optd[arg], '%H:%M:%S')
            elif isinstance(optd[arg], (list, tuple)):
                optd[arg] = ','.join(optd[arg])
            elif isinstance(optd[arg], (bool)):
                optd[arg] = str(optd[arg]).lower()
            options[arg] = optd[arg]
    with open(parms.options_path, 'w') as outfile:
        json.dump(options, outfile, indent=1)


try:
    load_options(parms)
except Exception:
    logger.warning("Failed in loading options")


def main_test_update():
    from timemachine import livemusic as tm
    parms.test_update = True
    tm.default_options = default_options  # All modules share this function.
    tm.save_options = save_options
    tm.main_test_update(parms)


def main():
    # archive = Archivary.Archivary(parms.dbpath, reload_ids=reload_ids, with_latest=False, collection_list=config.optd['COLLECTIONS'])
    # player = GD.GDPlayer()
    if '__update__' in config.optd['COLLECTIONS']:
        config.optd['COLLECTIONS'] = [x for x in config.optd['COLLECTIONS'] if x != '__update__']
        parms.__update__ = True
    else:
        parms.__update__ = False
    if config.optd['MODULE'] == 'livemusic':
        from timemachine import livemusic as tm
    elif config.optd['MODULE'] == '78rpm':
        from timemachine import m78rpm as tm
    else:
        logger.error(f"MODULE {config.optd['MODULE']} not in valid set of modules (['livemusic','78rpm'])")
        exit()

    tm.default_options = default_options  # All modules share this function.
    tm.save_options = save_options
    tm.main(parms)
    exit()


"""
from timemachine import m78rpm
m78rpm.parms = parms
m78rpm.load_saved_state(m78rpm.state)
m78rpm.eloop.start()
"""

for k in parms.__dict__.keys():
    logger.info(F"{k:20s} : {parms.__dict__[k]}")

if __name__ == "__main__" and parms.debug == 0:
    main()

if __name__ == "__main__" and parms.test_update:
    main_test_update()
