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
from operator import methodcaller
from threading import Event, Lock
from time import sleep

from gpiozero import Button, RotaryEncoder
from tenacity import retry
from tenacity.stop import stop_after_delay
from typing import Callable

from timemachine import Archivary, config, controls, GD

parser = optparse.OptionParser()
parser.add_option('--box', dest='box', type="string", default='v1', help="v0 box has screen at 270. [default %default]")
parser.add_option('--dbpath',
                  dest='dbpath',
                  default=os.path.join(GD.ROOT_DIR, 'metadata'),
                  help="path to database [default %default]")
parser.add_option('--state_path',
                  dest='state_path',
                  default=os.path.join(GD.ROOT_DIR, 'metadata/etree_state.json'),
                  help="path to state [default %default]")
parser.add_option('--options_path',
                  dest='options_path',
                  default=os.path.join(GD.ROOT_DIR, 'options.txt'),
                  help="path to options file [default %default]")
parser.add_option('--knob_sense_path',
                  dest='knob_sense_path',
                  type="string",
                  default=os.path.join(os.getenv('HOME'), ".knob_sense"),
                  help="path to file describing knob directions [default %default]")
parser.add_option('--test_update',
                  dest='test_update',
                  action="store_true",
                  default=False,
                  help="test that software update succeeded[default %default]")
parser.add_option('--pid_to_kill',
                  dest='pid_to_kill',
                  type='int',
                  default=None,
                  help="process id to kill during test_update [default %default]")
parser.add_option('-d', '--debug',
                  dest='debug',
                  type="int",
                  default=0,
                  help="If > 0, don't run the main script on loading [default %default]")
parser.add_option('-v', '--verbose',
                  dest='verbose',
                  action="store_true",
                  default=False,
                  help="Print more verbose information [default %default]")
parms, remainder = parser.parse_args()

logging.basicConfig(format='%(asctime)s.%(msecs)03d %(levelname)s: %(name)s %(message)s',
                    level=logging.INFO,
                    datefmt='%Y-%m-%d %H:%M:%S')
logger = logging.getLogger(__name__)
GDLogger = logging.getLogger('timemachine.GD')
controlsLogger = logging.getLogger('timemachine.controls')
logger.setLevel(logging.INFO)
GDLogger.setLevel(logging.INFO)
controlsLogger.setLevel(logging.WARN)

stagedate_event = Event()
select_event = Event()
track_event = Event()
playstate_event = Event()
# busy_event = Event()
free_event = Event()
stop_event = Event()
knob_event = Event()
button_event = Event()
screen_event = Event()
stop_update_event = Event()
stop_loop_event = Event()

random.seed(datetime.datetime.now())  # to ensure that random show will be new each time.


@retry(stop=stop_after_delay(10))
def retry_call(callable: Callable, *args, **kwargs):
    """Retry a call."""
    return callable(*args, **kwargs)


def sequential(func):
    def inner(*args, **kwargs):
        free_event.wait()
        free_event.clear()
        try:
            func(*args, **kwargs)
        except BaseException:
            raise
        finally:
            free_event.set()

    return inner


def load_saved_state(state):
    """ This function loads a subset of the fields from the state, which was saved with json
        Not Yet Working !!!
    """
    logger.info(F"Loading Saved State from {parms.state_path}")
    state_orig = state
    try:
        current = state.get_current()
        # if not os.path.exists(parms.state_path):
        f = open(parms.state_path, 'r')
        loaded_state = json.loads(f.read())
        fields_to_load = [
            'DATE', 'VENUE', 'STAGED_DATE', 'ON_TOUR', 'TOUR_YEAR', 'TOUR_STATE', 'EXPERIENCE', 'TRACK_NUM', 'TAPE_ID',
            'TRACK_TITLE', 'NEXT_TRACK_TITLE', 'TRACK_ID', 'DATE_READER', 'VOLUME']
        for field in fields_to_load:
            if field in ['DATE', 'STAGED_DATE', 'DATE_READER']:
                current[field] = to_date(loaded_state[field])
            else:
                current[field] = loaded_state[field]
        if current['DATE']:
            state.date_reader.m.steps = current['DATE'].month
            state.date_reader.d.steps = current['DATE'].day
            state.date_reader.y.steps = current['DATE'].year - min(state.date_reader.archive.year_list())
            state.date_reader.update()
        elif current['DATE_READER']:
            state.date_reader.m.steps = current['DATE_READER'].month
            state.date_reader.d.steps = current['DATE_READER'].day
            state.date_reader.y.steps = current['DATE_READER'].year - min(state.date_reader.archive.year_list())
            state.date_reader.update()

        current['DATE_READER'] = state.date_reader
        state.player._set_property('volume', current['VOLUME'])
        current['TOUR_STATE'] = config.INIT
        state.set(current)
        stagedate_event.set()
    except BaseException:
        logger.warning(F"Failed while Loading Saved State from {parms.state_path}")
        # raise
        return (state_orig)
    return state


@sequential
def save_state(state):
    # logger.debug (F"Saving state to {parms.state_path}")
    current = state.get_current()
    with open(parms.state_path, 'w') as statefile:
        json.dump(current, statefile, indent=1, default=str)


def default_options():
    d = {}
    d['COLLECTIONS'] = ['GratefulDead']
    d['QUIESCENT_TIME'] = 20
    d['SLEEP_AFTER_SECONDS'] = 3600
    d['SCROLL_VENUE'] = True
    d['FAVORED_TAPER'] = ''
    d['PWR_LED_ON'] = False
    d['AUTO_PLAY'] = True
    d['RELOAD_STATE_ON_START'] = True
    d['AUTO_UPDATE_ARCHIVE'] = False
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
            try:
                if k in ['QUIESCENT_TIME', 'SLEEP_AFTER_SECONDS']:
                    tmpd[k] = int(tmpd[k])
                if k in ['PWR_LED_ON', 'SCROLL_VENUE', 'AUTO_PLAY', 'AUTO_UPDATE_ARCHIVE', 'RELOAD_STATE_ON_START']:
                    tmpd[k] = tmpd[k].lower() == 'true'
                if k in ['COLLECTIONS']:
                    tmpd[k] = [x.strip() for x in tmpd[k].split(',')]
                if k in ['DEFAULT_START_TIME']:
                    tmpd[k] = datetime.datetime.strptime(tmpd[k], "%H:%M:%S").time()
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
    if not config.optd["PWR_LED_ON"]:
        led_cmd = 'sudo bash -c "echo none > /sys/class/leds/led1/trigger"'
    logger.info(F"in load_options, running {led_cmd}")
    os.system(led_cmd)


def twist_knob(knob: RotaryEncoder, label, date_reader: controls.date_knob_reader):
    if knob.is_active:
        logger.debug(f"Knob {label} steps={knob.steps} value={knob.value}")
    else:
        if knob.steps < knob.threshold_steps[0]:
            knob.steps = knob.threshold_steps[0]
        if knob.steps > knob.threshold_steps[1]:
            knob.steps = knob.threshold_steps[1]
        logger.debug(f"Knob {label} is inactive")
    date_reader.update()
    knob_event.set()
    stagedate_event.set()


if parms.verbose or parms.debug:
    logger.debug(F"Setting logger levels to {logging.DEBUG}")
    logger.setLevel(logging.DEBUG)
    GDLogger.setLevel(logging.DEBUG)
    controlsLogger.setLevel(logging.INFO)


def select_tape(tape, state, autoplay=False):
    current = state.get_current()
    if tape.identifier == current['TAPE_ID']:
        return                           # already selected.
    logger.debug(F"current state at entry {current}")
    EOT = False
    if current['PLAY_STATE'] == config.ENDED:
        EOT = True
    current['PLAY_STATE'] = config.READY  # eject current tape, insert new one in player
    current['TAPE_ID'] = tape.identifier
    logger.info(F"Set TAPE_ID to {current['TAPE_ID']}")
    current['TRACK_NUM'] = -1
    current['DATE'] = state.date_reader.date
    current['VENUE'] = state.date_reader.venue()
    state.player.insert_tape(tape)
    state.player._set_property('volume', current['VOLUME'])
    logger.debug(F"current state {current}")
    if autoplay and not EOT:
        logger.debug("Autoplaying tape")
        scr.show_playstate(staged_play=True, force=True)
        state.player.play()
        current['PLAY_STATE'] = config.PLAYING
        playstate_event.set()
    state.set(current)
    return state


def select_current_date(state, autoplay=False):
    if not state.date_reader.tape_available():
        return
    date_reader = state.date_reader
    tapes = date_reader.archive.tape_dates[date_reader.fmtdate()]
    scr.show_playstate(staged_play=True, force=True)
    _ = [t.tracks() for t in tapes[:3]]   # load the tracks so we can increase the score of those with titles.
    tapes = sorted(tapes, key=methodcaller('compute_score'), reverse=True)
    tape = tapes[0]
    state = select_tape(tape, state, autoplay=autoplay)

    logger.debug(F"current state after selecting tape {state}")
    select_event.set()
    return state


@sequential
def select_button(button, state):
    sleep(button._hold_time * 1.01)
    if button.is_pressed or button.is_held:
        return
    logger.debug("pressing select")
    current = state.get_current()
    # if current['EXPERIENCE']: return
    if current['ON_TOUR'] and current['TOUR_STATE'] in [config.READY, config.PLAYING]:
        return
    state = select_current_date(state, autoplay=config.optd['AUTO_PLAY'])
    scr.wake_up()
    logger.debug(F"current state after select button {state}")
    return state


@sequential
def select_button_longpress(button, state):
    logger.debug("long pressing select")
    if not state.date_reader.tape_available():
        return
    date_reader = state.date_reader
    tapes = date_reader.archive.tape_dates[date_reader.fmtdate()]
    itape = -1
    while button.is_held:
        itape = divmod(itape + 1, len(tapes))[1]
        tape_id = tapes[itape].identifier
        sbd = tapes[itape].stream_only()
        id_color = (0, 255, 255) if sbd else (0, 0, 255)
        logger.info(F"Selecting Tape: {tape_id}, the {itape}th of {len(tapes)} choices. SBD:{sbd}")
        if len(tape_id) < 16:
            scr.show_venue(tape_id, color=id_color, force=True)
            sleep(5)
        else:
            for i in range(0, max(1, len(tape_id)), 2):
                scr.show_venue(tape_id[i:], color=id_color, force=True)
                if not button.is_held:
                    break
    scr.show_venue(tape_id, color=id_color)
    tape = tapes[itape]
    state = select_tape(tape, state, autoplay=config.optd['AUTO_PLAY'])
    select_event.set()


@sequential
def play_pause_button(button, state):
    current = state.get_current()
    if current['PLAY_STATE'] in [config.ENDED]:
        return
    if current['EXPERIENCE'] and current['PLAY_STATE'] in [config.PLAYING, config.PAUSED]:
        return
    if current['ON_TOUR'] and current['TOUR_STATE'] in [config.READY, config.PLAYING]:
        return
    logger.debug("pressing play_pause")
    if current['PLAY_STATE'] in [config.INIT]:
        logger.info("Selecting current date, and play")
        state = select_current_date(state, autoplay=True)
        current = state.get_current()
    elif current['PLAY_STATE'] == config.PLAYING:
        logger.info("Pausing on player")
        state.player.pause()
        current['PAUSED_AT'] = datetime.datetime.now()
        current['PLAY_STATE'] = config.PAUSED
    elif current['PLAY_STATE'] in [config.PAUSED, config.STOPPED, config.READY]:
        current['PLAY_STATE'] = config.PLAYING
        scr.wake_up()
        screen_event.set()
        scr.show_playstate(staged_play=True, force=True)  # show that we've registered the button-press before blocking call.
        state.player.play()                              # this is a blocking call. I could move the "wait_until_playing" to the event handler.
    state.set(current)
    playstate_event.set()


@sequential
def play_pause_button_longpress(button, state):
    logger.debug(" longpress of play_pause -- choose random date and play it")
    current = state.get_current()
    if current['EXPERIENCE']:
        current['EXPERIENCE'] = False
    scr.show_playstate(staged_play=True, force=True)  # show that we've registered the button-press before blocking call.
    new_date = random.choice(state.date_reader.archive.dates)
    tape = state.date_reader.archive.best_tape(new_date)
    current['DATE'] = to_date(new_date)
    state.date_reader.set_date(current['DATE'])
    current['VENUE'] = state.date_reader.venue()
    current_volume = state.player.get_prop('volume')
    state.player._set_property('volume', max(current_volume, 100))
    current['VOLUME'] = state.player.get_prop('volume')

    if current['PLAY_STATE'] in [config.PLAYING, config.PAUSED]:
        state.player.stop()
    state.player.insert_tape(tape)
    current['PLAY_STATE'] = config.PLAYING
    state.player.play()  # this is a blocking call. I could move the "wait_until_playing" to the event handler.

    state.set(current)
    select_event.set()
    stagedate_event.set()
    playstate_event.set()


@sequential
def stop_button(button, state):
    current = state.get_current()
    if current['EXPERIENCE']:
        return
    if current['ON_TOUR'] and current['TOUR_STATE'] in [config.READY, config.PLAYING]:
        return
    if current['PLAY_STATE'] in [config.READY, config.INIT, config.STOPPED]:
        return
    button_event.set()
    state.player.stop()
    current['PLAY_STATE'] = config.STOPPED
    current['PAUSED_AT'] = datetime.datetime.now()
    state.set(current)
    playstate_event.set()


@sequential
def stop_button_longpress(button, state):
    logger.debug(" longpress of stop button -- loading options menu")
    scr.show_experience(text="Hold 5s to Update\nCode and Restart", force=True)
    sleep(5)
    if button.is_held:
        scr.clear()
        cmd = "sudo service update start"
        os.system(cmd)
        stop_event.set()
        scr.wake_up()
        scr.show_text("Updating\nCode\n\nStand By...", force=True)
        sleep(30)
        exit()


@sequential
def rewind_button(button, state):
    logger.debug("press of rewind")
    current = state.get_current()
    if current['EXPERIENCE'] or (current['ON_TOUR'] and current['TOUR_STATE'] in [config.READY, config.PLAYING]):
        current_volume = state.player.get_prop('volume')
        state.player._set_property('volume', max(current_volume * 0.9, 40))
        return
    sleep(button._hold_time)
    if button.is_pressed:
        return     # the button is being "held"
    if current['TRACK_NUM'] < len(state.player.playlist):
        state.player.prev()


@sequential
def rewind_button_longpress(button, state):
    logger.debug("longpress of rewind")
    while button.is_held:
        state.player.fseek(-30)


@sequential
def ffwd_button(button, state):
    logger.debug("press of ffwd")
    current = state.get_current()
    if current['EXPERIENCE'] or (current['ON_TOUR'] and current['TOUR_STATE'] in [config.READY, config.PLAYING]):
        current_volume = state.player.get_prop('volume')
        state.player._set_property('volume', min(current_volume * 1.1, 130))
        return
    sleep(button._hold_time)
    if button.is_pressed:
        return     # the button is being "held"
    if current['TRACK_NUM'] < len(state.player.playlist):
        state.player.next()
    return


@sequential
def ffwd_button_longpress(button, state):
    logger.debug("longpress of ffwd")
    while button.is_held:
        state.player.fseek(30)


@sequential
def month_button(button, state):
    current = state.get_current()
    if current['EXPERIENCE']:
        current['EXPERIENCE'] = False
    else:
        current['EXPERIENCE'] = True
    state.set(current)
    track_event.set()


def month_button_longpress(button, state):
    logger.debug(F"long pressing {button.name} -- nyi")


@sequential
def day_button(button, state):
    sleep(button._hold_time * 1.01)
    if button.is_pressed or button.is_held:
        return
    logger.debug("pressing day button")
    new_date = state.date_reader.next_date()
    state.date_reader.set_date(new_date)
    stagedate_event.set()


def day_button_longpress(button, state):
    logger.debug("long-pressing day button")
    scr.sleep()


@sequential
def year_button(button, state):
    sleep(button._hold_time)
    if button.is_pressed:
        return     # the button is being "held"
    today = datetime.date.today()
    now_m = today.month
    now_d = today.day
    m = state.date_reader.date.month
    d = state.date_reader.date.day
    y = state.date_reader.date.year

    if m == now_m and d == now_d:  # move to the next year where there is a tape available
        tihstring = F"{m:0>2d}-{d:0>2d}"
        tih_tapedates = [to_date(d) for d in state.date_reader.archive.dates if d.endswith(tihstring)]
        if len(tih_tapedates) > 0:
            cut = 0
            for i, dt in enumerate(tih_tapedates):
                if dt.year > y:
                    cut = i
                    break
            tapedate = (tih_tapedates[cut:] + tih_tapedates[:cut])[0]
            logger.debug(F"tapedate is {tapedate}")
            state.date_reader.set_date(datetime.date(tapedate.year, now_m, now_d))
    else:
        state.date_reader.set_date(datetime.date(y, now_m, now_d))
    stagedate_event.set()


@sequential
def year_button_longpress(button, state):
    sleep(3*button._hold_time)
    if not button.is_held:
        return
    logger.debug(" longpress of year button")
    current = state.get_current()
    ip_address = get_ip()
    if current['ON_TOUR']:
        scr.show_experience(text=F"ON_TOUR:{current['TOUR_YEAR']}\nHold 3s to exit", force=True)
        sleep(3)
        if button.is_held:
            logger.info("   EXITING ON_TOUR mode")
            current['ON_TOUR'] = False
            current['TOUR_YEAR'] = None
            current['TOUR_STATE'] = config.INIT
            scr.show_experience(text=F"ON_TOUR: Finished\n{ip_address}", force=True)
    else:
        current['ON_TOUR'] = True
        current['TOUR_YEAR'] = state.date_reader.date.year
        current['TOUR_STATE'] = config.INIT
        logger.info(F" ---> ON_TOUR:{current['TOUR_YEAR']}")
        scr.show_experience(text=F"ON_TOUR:{current['TOUR_YEAR']}\n{ip_address}", force=True)
    sleep(3)
    track_event.set()
    state.set(current)


def update_tracks(state):
    current = state.get_current()
    if current['EXPERIENCE']:
        scr.show_experience()
    elif current['ON_TOUR'] and current['TOUR_STATE'] in [config.READY, config.PLAYING]:
        scr.show_experience(text=F"Hold Year to\nExit TOUR {current['TOUR_YEAR']}")
    else:
        scr.show_track(current['TRACK_TITLE'], 0)
        scr.show_track(current['NEXT_TRACK_TITLE'], 1)


def to_date(d):
    if not d:
        return d
    return datetime.datetime.strptime(d, '%Y-%m-%d').date()


@sequential
def play_on_tour(tape, state, seek_to=0):
    logger.debug("play_on_tour")
    current = state.get_current()
    if tape.identifier == current['TAPE_ID']:
        return                           # already playing.
    current['PLAY_STATE'] = config.READY  # eject current tape, insert new one in player
    current['TAPE_ID'] = tape.identifier
    logger.info(F"Set TAPE_ID to {current['TAPE_ID']}")
    current['TRACK_NUM'] = -1
    current['DATE'] = to_date(tape.date)
    current['VENUE'] = tape.venue()
    state.player.insert_tape(tape)
    state.player._set_property('volume', current['VOLUME'])
    state.player.pause()
    state.player.play()
    state.player.seek_in_tape_to(seek_to, ticking=True)
    current['PLAY_STATE'] = config.PLAYING
    current['TOUR_STATE'] = config.PLAYING
    playlist_pos = state.player.get_prop('playlist-pos')
    if playlist_pos is None:
        current['PLAY_STATE'] = config.ENDED
    else:
        state.player.play()
    state.set(current)
    select_event.set()
    return


@sequential
def refresh_venue(state, idle_second_hand, refresh_times, venue):
    venue = config.VENUE if config.VENUE else venue
    stream_only = False
    tape_color = (0, 255, 255)
    tape = state.player.tape
    if tape is not None:
        tape_id = tape.identifier
        stream_only = tape.stream_only()
        tape_color = (255, 255, 255) if stream_only else (0, 0, 255)
    else:
        tape_id = venue

    show_collection_name = tape_id == venue  # This is an arbitrary condition...fix!
    id_color = (0, 255, 255)

    if idle_second_hand < refresh_times[5]:
        display_string = venue
    elif show_collection_name and idle_second_hand < refresh_times[7] and tape is not None:
        collection = frozenset(state.date_reader.archive.collection_name) & frozenset(tape.collection)
        display_string = list(collection)[0]
    else:
        display_string = tape_id
        id_color = tape_color

    display_string = re.sub(r'\d{2,4}-\d\d-\d\d\.*', '~', display_string)
    # logger.debug(F"display_string is {display_string}")

    if not config.optd['SCROLL_VENUE']:
        scr.show_venue(display_string, color=id_color)
        return

    if idle_second_hand in refresh_times[:2]:
        scr.show_venue(display_string, color=id_color)
    elif idle_second_hand in [refresh_times[2], refresh_times[8]]:
        if len(display_string) > 12:
            scr.show_venue(display_string[13:], color=id_color)
        else:
            scr.show_venue(display_string, color=id_color)
    elif idle_second_hand in [refresh_times[3], refresh_times[9]]:
        if len(display_string) > 24:
            scr.show_venue(display_string[25:], color=id_color)
        elif len(display_string) > 12:
            scr.show_venue(display_string[11:], color=id_color)
        else:
            scr.show_venue(display_string, color=id_color)
    elif idle_second_hand == refresh_times[6]:
        if len(display_string) > 36:
            scr.show_venue(display_string[37:], color=id_color)
        elif len(display_string) > 24:
            scr.show_venue(display_string[25:], color=id_color)
        elif len(display_string) > 12:
            scr.show_venue(display_string[13:], color=id_color)
        else:
            scr.show_venue(display_string, color=id_color)
    elif idle_second_hand == refresh_times[7]:
        scr.show_venue(display_string, color=id_color)


def test_update(state):
    """ This function is run when the script has been updated. If it passes, then the code
        in the temporary folder may be moved to the working directory (and be used as the latest version).
        If this function fails, then the code should NOT be placed in the working directory """

    current = state.get_current()
    current['EXPERIENCE'] = False
    current['ON_TOUR'] = False
    current['PLAY_STATE'] = config.PLAYING
    state.set(current)
    date_reader = state.date_reader
    last_sdevent = datetime.datetime.now()
    clear_stagedate = False
    scr.update_now = False
    free_event.set()
    stagedate_event.set()
    knob_event.clear()
    button_event.clear()
    scr.clear()
    try:
        if parms.pid_to_kill is not None:
            os.system(F"kill {parms.pid_to_kill}")
    except Exception:
        pass
    try:
        scr.show_text("Turn Any\nKnob", force=True)
        if knob_event.wait(290):
            knob_event.clear()
            scr.clear()
        else:
            sys.exit(-1)
        scr.show_text("Press Stop\nButton", force=True)
        if button_event.wait(10):
            button_event.clear()
            scr.show_text("Passed! ", force=True, clear=True)
            sys.exit(0)
        else:
            sys.exit(-1)
    except KeyboardInterrupt:
        sys.exit(-1)
    sys.exit(-1)


def event_loop(state, lock):
    date_reader = state.date_reader
    last_sdevent = datetime.datetime.now()
    q_counter = False
    n_timer = 0
    last_idle_second_hand = None
    now = datetime.datetime.now()
    last_idle_day = now.day
    last_idle_hour = now.hour
    last_idle_minute = now.minute
    refresh_times = [4, 9, 14, 19, 24, 29, 34, 39, 44, 49]
    max_second_hand = 50
    clear_stagedate = False
    scr.update_now = False
    free_event.set()
    stagedate_event.set()
    scr.clear()

    try:
        while not stop_loop_event.wait(timeout=0.001):
            if not free_event.wait(timeout=0.01):
                continue
            lock.acquire()
            now = datetime.datetime.now()
            n_timer = n_timer + 1
            idle_seconds = (now - last_sdevent).seconds
            idle_second_hand = divmod(idle_seconds, max_second_hand)[1]
            current = state.get_current()
            default_start = config.optd['DEFAULT_START_TIME']

            if current['ON_TOUR']:
                if current['TOUR_STATE'] == config.ENDED and now.hour < 1:  # reset ENDED to INIT after midnight.
                    current['TOUR_STATE'] = config.INIT
                if current['TOUR_STATE'] not in [config.PLAYING, config.ENDED]:
                    then_time = now.replace(year=current['TOUR_YEAR'])
                    # At the "scheduled time", stop whatever is playing and wait.
                    tape = state.date_reader.archive.tape_at_time(then_time, default_start=default_start)
                    if not tape:
                        current['TOUR_STATE'] = config.INIT
                    else:
                        current['TOUR_STATE'] = config.READY
                        state.player.stop()
                        current['TAPE_ID'] = None
                        start_time = state.date_reader.archive.tape_start_time(then_time, default_start=default_start)
                        scr.show_experience(text=F"ON_TOUR:{current['TOUR_YEAR']}\nWaiting for show", force=True)
                        then_date = then_time.date()
                        random.seed(then_date.year + then_date.month + then_date.day)
                        wait_time = random.randrange(60, 600)
                        logger.info(
                            F"On Tour Tape Found on {then_time}. Sleeping 10 seconds. Waiting for {(start_time + datetime.timedelta(seconds=wait_time)).time()}"
                        )
                        sleep(10)
                        if now.time() >= (start_time + datetime.timedelta(seconds=wait_time)).time():
                            point_in_show = (then_time - (start_time + datetime.timedelta(seconds=wait_time))).seconds
                            play_on_tour(tape, state, seek_to=point_in_show)
                    logger.debug(F"tape {tape}, tour state {current['TOUR_STATE']}, then_time {then_time}")
                if current['TOUR_STATE'] == config.PLAYING:
                    if current['PLAY_STATE'] == config.ENDED:
                        current['TOUR_STATE'] = config.ENDED
                        state.set(current)
                        track_event.set()
                        logger.debug(F" ENDED!! TOUR_STATE is {current['TOUR_STATE']}, default_start: {default_start}")

            if screen_event.is_set():
                scr.refresh()
                screen_event.clear()
            if stagedate_event.is_set():
                last_sdevent = now
                q_counter = True
                scr.show_staged_date(date_reader.date)
                scr.show_venue(date_reader)
                # if clear_stagedate: stagedate_event.clear()
                # clear_stagedate = not clear_stagedate   # only clear stagedate event after updating twice
                stagedate_event.clear()
                scr.wake_up()
                screen_event.set()
            if track_event.is_set():
                update_tracks(state)
                track_event.clear()
                screen_event.set()
            if select_event.is_set():
                current = state.get_current()
                scr.show_selected_date(current['DATE'])
                update_tracks(state)
                select_event.clear()
                scr.wake_up()
                screen_event.set()
            if playstate_event.is_set():
                scr.show_playstate()
                playstate_event.clear()
                screen_event.set()
            if q_counter and config.DATE and idle_seconds > config.optd['QUIESCENT_TIME']:
                logger.debug(F"Reverting staged date back to selected date {idle_seconds}> {config.optd['QUIESCENT_TIME']}")
                scr.show_staged_date(config.DATE)
                scr.show_venue(config.VENUE)
                q_counter = False
                screen_event.set()
            if idle_second_hand in refresh_times and idle_second_hand != last_idle_second_hand:
                last_idle_second_hand = idle_second_hand
                # if now.minute != last_idle_minute:
                # if now.day != last_idle_day:
                if (now.hour != last_idle_hour) and now.hour == 5:
                    last_idle_day = now.day
                    last_idle_hour = now.hour
                    last_idle_minute = now.minute
                    # try:
                    # date_reader.archive.load_archive(with_latest=config.optd['AUTO_UPDATE_ARCHIVE'])
                    # except:
                    # logger.warning("Unable to refresh archive")
                track_event.set()
                playstate_event.set()
                save_state(state)
                if current['PLAY_STATE'] != config.PLAYING:  # deal with overnight pauses, which freeze the alsa player.
                    if (now - config.PAUSED_AT).seconds > config.optd['SLEEP_AFTER_SECONDS'] and state.player.get_prop('audio-device') != 'null':
                        logger.debug(F"Paused at {config.PAUSED_AT}, sleeping after {config.optd['SLEEP_AFTER_SECONDS']}, now {now}")
                        scr.sleep()
                        state.player._set_property('audio-device', 'null')
                        state.player.wait_for_property('audio-device', lambda x: x == 'null')
                        state.set(current)
                        playstate_event.set()
                    elif (now - current['WOKE_AT']).seconds > config.optd['SLEEP_AFTER_SECONDS']:
                        scr.sleep()
                if idle_seconds > config.optd['QUIESCENT_TIME']:
                    if config.DATE:
                        scr.show_staged_date(config.DATE)
                    refresh_venue(state, idle_second_hand, refresh_times, date_reader.venue())
                else:
                    scr.show_staged_date(date_reader.date)
                    scr.show_venue(date_reader)
                screen_event.set()
            lock.release()

    except KeyboardInterrupt:
        exit(0)
    finally:
        lock.release()


def get_ip():
    cmd = "hostname -I"
    ip = subprocess.check_output(cmd, shell=True)
    ip = ip.decode().split(' ')[0]
    return ip


try:
    load_options(parms)
except Exception:
    logger.warning("Failed in loading options")
# parms.state_path = os.path.join(os.path.dirname(parms.state_path), F'{config.optd["COLLECTIONS"]}_{os.path.basename(parms.state_path)}')
config.PAUSED_AT = datetime.datetime.now()
config.WOKE_AT = datetime.datetime.now()

scr = controls.screen(upside_down=False)
ip_address = get_ip()
scr.show_text("Time\n  Machine\n   Loading...", color=(0, 255, 255), force=False, clear=True)
scr.show_text(F"{ip_address}", loc=(0, 100), font=scr.smallfont, color=(255, 255, 255))

if parms.test_update:
    config.optd = default_options()  # no weirdness during update testing

# Define the buttons here
select = retry_call(Button, config.select_pin, hold_time=0.5, hold_repeat=False)
play_pause = retry_call(Button, config.play_pause_pin, hold_time=7)
ffwd = retry_call(Button, config.ffwd_pin, hold_time=0.5, hold_repeat=False)
rewind = retry_call(Button, config.rewind_pin, hold_time=0.5, hold_repeat=False)
stop = retry_call(Button, config.stop_pin, hold_time=7)

reload_ids = False
if rewind.is_pressed:
    scr.show_text("Reloading\nfrom\narchive.org...", color=(0, 255, 255), force=True, clear=True)
    logger.info('Reloading from archive.org')
    # reload_ids = True
if stop.is_pressed:
    logger.info('Resetting to factory archive -- nyi')

archive = Archive.Archivary(parms.dbpath, reload_ids=reload_ids, with_latest=False, collection_name=config.optd['COLLECTIONS'])
player = GD.GDPlayer()


@player.property_observer('playlist-pos')
def on_track_event(_name, value):
    logger.info(F'in track event callback {_name}, {value}')
    if value is None:
        config.PLAY_STATE = config.ENDED
        config.PAUSED_AT = datetime.datetime.now()
        select_button(select, state)
    track_event.set()


@player.event_callback('file-loaded')
def my_handler(event):
    logger.debug('file-loaded')


try:
    kfile = open(parms.knob_sense_path, 'r')
    knob_sense = int(kfile.read())
    kfile.close()
except Exception:
    knob_sense = 0

year_list = archive.year_list()
num_years = max(year_list) - min(year_list)
m = retry_call(RotaryEncoder, config.month_pins[knob_sense & 1], config.month_pins[~knob_sense & 1], max_steps=0, threshold_steps=(1, 12))
d = retry_call(RotaryEncoder, config.day_pins[(knob_sense >> 1) & 1], config.day_pins[~(knob_sense >> 1) & 1], max_steps=0, threshold_steps=(1, 31))
y = retry_call(RotaryEncoder, config.year_pins[(knob_sense >> 2) & 1], config.year_pins[~(knob_sense >> 2) & 1], max_steps=0, threshold_steps=(0, num_years))
m.steps = 1
d.steps = 1
y.steps = 0
if 'GratefulDead' in archive.collection_name:
    m.steps = 8
    d.steps = 13
    y.steps = min(1975 - 1965, num_years)
date_reader = controls.date_knob_reader(y, m, d, archive)
state = controls.state(date_reader, player)
m.when_rotated = lambda x: twist_knob(m, "month", date_reader)
d.when_rotated = lambda x: twist_knob(d, "day", date_reader)
y.when_rotated = lambda x: twist_knob(y, "year", date_reader)
m_button = retry_call(Button, config.month_pins[2])
d_button = retry_call(Button, config.day_pins[2], hold_time=0.3, hold_repeat=False)
y_button = retry_call(Button, config.year_pins[2], hold_time=0.5)

play_pause.when_pressed = lambda button: play_pause_button(button, state)
play_pause.when_held = lambda button: play_pause_button_longpress(button, state)

select.when_pressed = lambda button: select_button(button, state)
select.when_held = lambda button: select_button_longpress(button, state)

ffwd.when_pressed = lambda button: ffwd_button(button, state)
ffwd.when_held = lambda button: ffwd_button_longpress(button, state)

rewind.when_pressed = lambda button: rewind_button(button, state)
rewind.when_held = lambda button: rewind_button_longpress(button, state)

stop.when_pressed = lambda button: stop_button(button, state)
stop.when_held = lambda button: stop_button_longpress(button, state)

m_button.when_pressed = lambda button: month_button(button, state)
d_button.when_pressed = lambda button: day_button(button, state)
y_button.when_pressed = lambda button: year_button(button, state)

d_button.when_held = lambda button: day_button_longpress(button, state)
# m_button.when_held = lambda button: month_button_longpress(button,state)
y_button.when_held = lambda button: year_button_longpress(button, state)

scr.clear_area(controls.Bbox(0, 0, 160, 100))
scr.show_text("Powered by\n archive.org", color=(0, 255, 255), force=True)
scr.show_text(F"{archive.collection_name}", font=scr.smallfont, loc=(0, 70), force=True)

if config.optd['RELOAD_STATE_ON_START']:
    load_saved_state(state)

lock = Lock()
eloop = threading.Thread(target=event_loop, args=[state, lock])


def main():
    if config.optd['AUTO_UPDATE_ARCHIVE']:
        archive_updater = GD.GDArchive_Updater(state, 3600, stop_update_event, scr=scr, lock=lock)
        archive_updater.start()
    eloop.run()
    exit()


def main_test_update():
    test_update(state)


for k in parms.__dict__.keys():
    logger.info(F"{k:20s} : {parms.__dict__[k]}")

if __name__ == "__main__" and parms.test_update:
    main_test_update()
elif __name__ == "__main__" and parms.debug == 0:
    main()
