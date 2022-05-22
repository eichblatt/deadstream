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
                  dest='dbpath',
                  default=os.path.join(GD.ROOT_DIR, 'metadata'),
                  help="path to database [default %default]")
parser.add_option('--state_path',
                  dest='state_path',
                  default=os.path.join(GD.ROOT_DIR, 'metadata/georgeblood_state.json'),
                  help="path to state [default %default]")
parser.add_option('--options_path',
                  dest='options_path',
                  default=os.path.join(os.getenv('HOME'), '.vinyl78_options.txt'),
                  help="path to options file [default %default]")
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

knob_sense_path = os.path.join(os.getenv('HOME'), ".knob_sense")

logging.basicConfig(format='%(asctime)s.%(msecs)03d %(levelname)s: %(name)s %(message)s',
                    level=logging.INFO,
                    datefmt='%Y-%m-%d %H:%M:%S')
logger = logging.getLogger(__name__)
GDLogger = logging.getLogger('timemachine.GD')
controlsLogger = logging.getLogger('timemachine.controls')
logger.setLevel(logging.INFO)
GDLogger.setLevel(logging.INFO)
controlsLogger.setLevel(logging.WARN)

choose_artist_event = Event()
stagedate_event = Event()
track_event = Event()
playstate_event = Event()
free_event = Event()
stop_update_event = Event()
stop_loop_event = Event()
venue_counter = (0, 0)
QUIESCENT_TIME = 20
SLEEP_AFTER_SECONDS = 3600
PWR_LED_ON = False
AUTO_PLAY = True
RELOAD_STATE_ON_START = True

artist_year_dict = {}   # this needs to be either in state or somewhere.

random.seed(datetime.datetime.now().timestamp())  # to ensure that random show will be new each time.


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
            'DATE', 'STAGED_DATE', 'TRACK_NUM', 'TAPE_ID', 'TRACK_TITLE', 'NEXT_TRACK_TITLE', 'TRACK_ID', 'DATE_READER', 'VOLUME']
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
        state.set(current)
        stagedate_event.set()
    except BaseException:
        logger.warning(F"Failed while Loading Saved State from {parms.state_path}")
        # raise
        state = state_orig
    finally:
        current['PLAY_STATE'] = config.INIT
        state.set(current)
    return


@sequential
def save_state(state):
    # logger.debug (F"Saving state to {parms.state_path}")
    current = state.get_current()
    with open(parms.state_path, 'w') as statefile:
        json.dump(current, statefile, indent=1, default=str)


def default_options():
    d = {}
    d['COLLECTIONS'] = ['georgeblood']
    d['FAVORED_TAPER'] = []
    d['AUTO_UPDATE_ARCHIVE'] = True
    d['PLAY_LOSSLESS'] = False
    d['PULSEAUDIO_ENABLE'] = False
    if controls.get_os_version() > 10:
        d['PULSEAUDIO_ENABLE'] = True
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
                if k in ['AUTO_UPDATE_ARCHIVE', 'PLAY_LOSSLESS', 'PULSEAUDIO_ENABLE']:  # make booleans.
                    tmpd[k] = tmpd[k].lower() == 'true'
                if k in ['COLLECTIONS', 'FAVORED_TAPER']:   # make lists from comma-separated strings.
                    c = [x.strip() for x in tmpd[k].split(',') if x != '']
                    if k == 'COLLECTIONS':
                        c = ['Phish' if x.lower() == 'phish' else x for x in c]
                    tmpd[k] = c
                if k in ['DEFAULT_START_TIME']:            # make datetime
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
    if not PWR_LED_ON:
        led_cmd = 'sudo bash -c "echo none > /sys/class/leds/led1/trigger"'
    logger.info(F"in load_options, running {led_cmd}")
    os.system(led_cmd)


def decade_knob(knob: RotaryEncoder, label, artist_counter: controls.artist_knob_reader):
    if label == "day":
        TMB.decade_knob(TMB.d, "day", artist_counter)
    elif label == "month":
        TMB.decade_knob(TMB.m, "month", artist_counter)
    TMB.knob_event.set()
    choose_artist_event.set()


def twist_knob(knob: RotaryEncoder, label, date_reader: controls.date_knob_reader):
    if label != 'year':
        return
    TMB.twist_knob(knob, label, date_reader)
    TMB.knob_event.set()
    stagedate_event.set()


if parms.verbose or parms.debug:
    logger.debug(F"Setting logger levels to {logging.DEBUG}")
    logger.setLevel(logging.DEBUG)
    GDLogger.setLevel(logging.DEBUG)
    controlsLogger.setLevel(logging.INFO)


def choose_artist(state):
    choose_artist_event.clear()
    TMB.knob_event.clear()
    date_reader = state.date_reader
    artist_counter = state.artist_counter
    archive = date_reader.archive
    date = date_reader.date
    artist_year_dict = archive.year_artists(date.year)  # This needs to be availabe outside this function.
    artist_list = ['RETURN', 'Shuffle'] + sorted(list(artist_year_dict.keys()))
    chosen_artists = controls.select_option(TMB, artist_counter, "Choose artist", artist_list)
    if chosen_artists == 'RETURN':
        return None
    elif chosen_artists == 'Shuffle':
        chosen_artists = random.sample(artist_list[2:], len(artist_list[2:]))
    else:
        pass
    if not isinstance(chosen_artists, list):
        chosen_artists = [chosen_artists]
    logger.debug(F"artist is now {chosen_artists}")
    return (artist_year_dict, chosen_artists)
    # tapes = artist_year_dict[chosen_artists]
    # logger.info(F"tapes are {tapes}")
    # logger.info(F"tracks are {tapes[0].tracks()}")
    # return tapes


def select_tape(tape, state, autoplay=True):
    global venue_counter
    if tape._remove_from_archive:
        return
    current = state.get_current()
    if tape.identifier == current['TAPE_ID']:
        TMB.scr.show_experience(text=F"{controls.get_version()}", color=(255, 100, 0), force=True)
        sleep(1)
        return                           # already selected.
    logger.debug(F"select_tape: current state at entry {current}")
    current['PLAY_STATE'] = config.READY  # eject current tape, insert new one in player
    current['TAPE_ID'] = tape.identifier
    logger.info(F"Set TAPE_ID to {current['TAPE_ID']}")
    current['TRACK_NUM'] = -1
    current['DATE'] = state.date_reader.date
    current['VENUE'] = tape.identifier.replace('-', ' ').split('_')[2]
    current['ARTIST'] = current['VENUE']  # for now at least
    venue_counter = (0, 0)

    try:
        state.player.insert_tape(tape)
        state.player._set_property('volume', current['VOLUME'])
        logger.debug(F"select_tape: current state {current}")
        if autoplay:
            logger.debug("Autoplaying tape")
            TMB.scr.show_playstate(staged_play=True, force=True)
            state.player.play()
            current['PLAY_STATE'] = config.PLAYING
            playstate_event.set()
            state.set(current)
            track_event.set()
            TMB.select_event.set()
    except Exception as e:
        logger.exception(e)
        pass
    return state


def select_current_artist(state, autoplay=True):
    artist_counter = state.artist_counter
    tapes = date_reader.archive.resort_tape_date(date_reader.fmtdate())
    if len(tapes) == 0:
        TMB.scr.show_venue('No Audio', color=(255, 255, 255), force=True)
        sleep(2)
        return
    tape = tapes[date_reader.shownum]
    TMB.scr.show_playstate(staged_play=True, force=True)
    state = select_tape(tape, state, autoplay=autoplay)

    logger.debug(F"current state after selecting tape {state}")
    TMB.select_event.set()
    return state


def select_current_date(state, autoplay=True):
    artist_counter = state.artist_counter
    if not date_reader.tape_available():
        return
    tapes = date_reader.archive.resort_tape_date(date_reader.fmtdate())
    if len(tapes) == 0:
        TMB.scr.show_venue('No Audio', color=(255, 255, 255), force=True)
        sleep(2)
        return
    tape = tapes[date_reader.shownum]
    TMB.scr.show_playstate(staged_play=True, force=True)
    state = select_tape(tape, state, autoplay=autoplay)

    logger.debug(F"current state after selecting tape {state}")
    TMB.select_event.set()
    return state


@sequential
def select_button(button, state):
    logger.info("pressing select")
    TMB.select_event.set()
    logger.info("pressing select")

    autoplay = AUTO_PLAY
    sleep(button._hold_time * 1.01)
    if button.is_pressed or button.is_held:
        return
    logger.debug("pressing select")
    current = state.get_current()
    if current['PLAY_STATE'] == config.ENDED:
        logger.debug("setting PLAY_STATE to READY, autoplay to False")
        autoplay = False
        current['PLAY_STATE'] = config.READY
        state.set(current)
    #select_current_artist(state, autoplay=autoplay)
    TMB.scr.wake_up()
    logger.debug(F"current state after select button {state}")
    return


@sequential
def select_button_longpress(button, state):
    logger.debug("long pressing select")
    if not state.date_reader.tape_available():
        return
    date_reader = state.date_reader
    tapes = date_reader.archive.resort_tape_date(date_reader.fmtdate())
    itape = -1
    while button.is_held:
        itape = divmod(itape + 1, len(tapes))[1]
        tape_id = tapes[itape].identifier
        sbd = tapes[itape].stream_only()
        id_color = (0, 255, 255) if sbd else (0, 0, 255)
        logger.info(F"Selecting Tape: {tape_id}, the {itape}th of {len(tapes)} choices. SBD:{sbd}")
        if len(tape_id) < 16:
            show_venue_text(tapes[itape], color=id_color, show_id=True, force=True)
            sleep(4)
        else:
            for i in range(0, max(1, len(tape_id)), 2):
                show_venue_text(tapes[itape], color=id_color, show_id=True, offset=i, force=True)
                # TMB.scr.show_venue(tape_id[i:], color=id_color, force=True)
                if not button.is_held:
                    break
    TMB.scr.show_venue(tape_id, color=id_color)
    tape = tapes[itape]
    state = select_tape(tape, state, autoplay=AUTO_PLAY)
    TMB.select_event.set()


@sequential
def play_pause_button(button, state):
    current = state.get_current()
    if current['EXPERIENCE'] and current['PLAY_STATE'] in [config.PLAYING, config.PAUSED]:
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
    elif current['PLAY_STATE'] in [config.PAUSED, config.STOPPED, config.READY, config.ENDED]:
        current['PLAY_STATE'] = config.PLAYING
        TMB.scr.wake_up()
        TMB.screen_event.set()
        TMB.scr.show_playstate(staged_play=True, force=True)  # show that we've registered the button-press before blocking call.
        state.player.play()                              # this is a blocking call. I could move the "wait_until_playing" to the event handler.
    state.set(current)
    playstate_event.set()


@sequential
def play_pause_button_longpress(button, state):
    global venue_counter
    logger.debug(" longpress of play_pause -- choose random date and play it")
    current = state.get_current()
    if current['EXPERIENCE']:
        current['EXPERIENCE'] = False
    TMB.scr.show_playstate(staged_play=True, force=True)  # show that we've registered the button-press before blocking call.
    new_date = random.choice(state.date_reader.archive.dates)
    tape = state.date_reader.archive.best_tape(new_date)
    current['DATE'] = to_date(new_date)
    state.date_reader.set_date(current['DATE'])
    current['VENUE'] = tape.identifier.replace('-', ' ').split('_')[2]
    current['ARTIST'] = tape.artist
    venue_counter = (0, 0)
    current_volume = state.player.get_prop('volume')
    state.player._set_property('volume', max(current_volume, 100))
    current['VOLUME'] = state.player.get_prop('volume')

    if current['PLAY_STATE'] in [config.PLAYING, config.PAUSED]:
        state.player.stop()
    state.player.insert_tape(tape)
    current['PLAY_STATE'] = config.PLAYING
    state.player.play()  # this is a blocking call. I could move the "wait_until_playing" to the event handler.

    state.set(current)
    TMB.select_event.set()
    stagedate_event.set()
    playstate_event.set()


@sequential
def stop_button(button, state):
    current = state.get_current()
    if current['EXPERIENCE']:
        return
    if current['PLAY_STATE'] == config.ENDED:
        current['PLAY_STATE'] = config.STOPPED
        state.set(current)

    TMB.button_event.set()
    state.player.stop()
    current['PLAY_STATE'] = config.STOPPED
    current['PAUSED_AT'] = datetime.datetime.now()
    state.set(current)
    playstate_event.set()


@sequential
def stop_button_longpress(button, state):
    logger.debug(" longpress of stop button -- loading options menu")
    pixels = TMB.scr.image.tobytes()
    TMB.scr.show_experience(text="Hold 5s to Update\nCode and Restart", force=True)
    sleep(5)
    if button.is_held:
        TMB.scr.clear()
        cmd = "sudo service update start"
        os.system(cmd)
        TMB.stop_event.set()
        TMB.scr.wake_up()
        TMB.scr.show_text("Updating\nCode\n\nStand By...", force=True)
        sleep(20)
        # if this program hasn't been killed after 20 seconds, then the code was already the latest version
        TMB.scr.show_text("Code is\nup to Date", clear=True, force=True)
        sleep(5)
        TMB.scr.image.frombytes(pixels)
        TMB.scr.refresh(force=True)
        # exit()


@sequential
def rewind_button(button, state):
    logger.debug("press of rewind")
    current = state.get_current()
    if current['EXPERIENCE']:
        current_volume = state.player.get_prop('volume')
        state.player._set_property('volume', max(current_volume * 0.9, 40))
        return
    sleep(button._hold_time)
    if button.is_pressed:
        return     # the button is being "held"
    if current['TRACK_NUM'] == 0:
        state.player.stop()
        state.player.play()
    elif current['TRACK_NUM'] < len(state.player.playlist):
        state.player.prev()


@sequential
def rewind_button_longpress(button, state):
    logger.debug("longpress of rewind")
    while button.is_held:
        state.player.fseek(-15)


@sequential
def ffwd_button(button, state):
    logger.debug("press of ffwd")
    current = state.get_current()
    if current['EXPERIENCE']:
        current_volume = state.player.get_prop('volume')
        state.player._set_property('volume', min(current_volume * 1.1, 130))
        return
    sleep(button._hold_time)
    if button.is_pressed:
        return     # the button is being "held"
    if current['TRACK_NUM'] < len(state.player.playlist) - 1:  # before the last track
        state.player.next()
    else:
        state.player.stop()
        config.PLAY_STATE = config.ENDED
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
    state.date_reader.set_date(*state.date_reader.next_show())
    stagedate_event.set()


def day_button_longpress(button, state):
    logger.debug("long-pressing day button")
    TMB.scr.sleep()


@sequential
def year_button(button, state):
    sleep(button._hold_time)
    if button.is_pressed:
        return     # the button is being "held"
    stagedate_event.set()


@sequential
def year_button_longpress(button, state):
    sleep(button._hold_time)
    if not button.is_held:
        return
    ip_address = get_ip()
    TMB.scr.show_experience(text=F"{ip_address}:9090\nto configure", force=True)
    sleep(2 * button._hold_time)
    if not button.is_held:
        sleep(2 * button._hold_time)
        return
    logger.debug(" longpress of year button")
    current = state.get_current()
    sleep(3)
    track_event.set()
    state.set(current)


def update_tracks(state):
    current = state.get_current()
    if current['EXPERIENCE']:
        TMB.scr.show_experience()
    else:
        TMB.scr.show_track(current['TRACK_TITLE'], 0)
        TMB.scr.show_track(current['NEXT_TRACK_TITLE'], 1)


def to_date(d):
    if not d:
        return d
    return datetime.datetime.strptime(d, '%Y-%m-%d').date()


@sequential
def refresh_venue(state):
    global venue_counter

    stream_only = False
    tape_color = (0, 255, 255)
    tape = state.player.tape
    if tape is not None:
        tape_id = tape.identifier
        stream_only = tape.stream_only()
        tape_color = (255, 255, 255) if stream_only else (0, 0, 255)
    else:
        tape_id = None

    try:
        vcs = [x.strip() for x in config.VENUE.split(',')]
    except Exception:
        vcs = tape_id if tape_id is not None else ''

    artist = config.ARTIST if config.ARTIST is not None else ''
    venue = ''
    city_state = ''
    display_string = ''
    screen_width = 13
    n_fields = 4
    n_subfields = 4

    if len(vcs) == 3:
        venue = vcs[0]
        city_state = f'{vcs[1]},{vcs[2]}'
    elif len(vcs) > 3:
        venue = ','.join(vcs[:-2])
        city_state = f'{vcs[-2]},{vcs[-1]}'
    elif len(vcs) == 1:
        venue = vcs[0]
        city_state = venue
    elif len(vcs) == 2:
        venue = vcs[0]
        city_state = vcs[1]
    else:
        venue = city_state = vcs

    if tape_id is None:
        tape_id = venue

    # logger.debug(f'venue {venue}, city_state {city_state}')

    tape_id == venue  # This is an arbitrary condition...fix!
    id_color = (0, 255, 255)

    if venue_counter[0] == 0:
        display_string = venue
    elif venue_counter[0] == 1:
        display_string = city_state
    elif venue_counter[0] == 2:
        display_string = artist
    elif venue_counter[0] == 3:
        id_color = tape_color
        display_string = tape_id

    display_string = re.sub(r'\d{2,4}-\d\d-\d\d\.*', '~', display_string)
    # logger.debug(F"display_string is {display_string}")

    if not config.optd['SCROLL_VENUE']:
        TMB.scr.show_venue(display_string, color=id_color)
        return
    else:
        display_offset = min(max(0, len(display_string) - (screen_width - 1)), screen_width * venue_counter[1])
        if venue_counter[1] < n_subfields - 1:
            display_offset = 0 if (display_offset < screen_width) else display_offset
            TMB.scr.show_venue(display_string[display_offset:], color=id_color)
        else:
            TMB.scr.show_venue(display_string[-1 * (screen_width - 1):], color=id_color)

    div, mod = divmod(venue_counter[1] + 1, n_subfields)
    venue_counter = (divmod(venue_counter[0] + div, n_fields)[1], mod)


def test_update(state):
    """ This function is run when the script has been updated. If it passes, then the code
        in the temporary folder may be moved to the working directory (and be used as the latest version).
        If this function fails, then the code should NOT be placed in the working directory """

    current = state.get_current()
    current['EXPERIENCE'] = False
    current['PLAY_STATE'] = config.PLAYING
    state.set(current)
    date_reader = state.date_reader
    last_sdevent = datetime.datetime.now()
    TMB.scr.update_now = False
    free_event.set()
    stagedate_event.set()
    TMB.knob_event.clear()
    TMB.button_event.clear()
    TMB.scr.clear()
    try:
        if parms.pid_to_kill is not None:
            os.system(F"kill {parms.pid_to_kill}")
    except Exception:
        pass
    try:
        TMB.scr.show_text("Turn Any\nKnob", force=True)
        if TMB.knob_event.wait(3600):
            TMB.knob_event.clear()
            TMB.scr.clear()
        else:
            sys.exit(-1)
        TMB.scr.show_text("Press Stop\nButton", force=True)
        if TMB.button_event.wait(600):
            TMB.button_event.clear()
            TMB.scr.show_text("Passed! ", force=True, clear=True)
            sys.exit(0)
        else:
            sys.exit(-1)
    except KeyboardInterrupt:
        sys.exit(-1)
    sys.exit(-1)


def get_current(state):
    current = state.get_current()
    return current


def show_venue_text(arg, color=(0, 255, 255), show_id=False, offset=0, force=False):
    if isinstance(arg, controls.artist_knob_reader):
        date_reader = arg
        archive = date_reader.archive
        tapes = archive.tape_dates[date_reader.fmtdate()] if date_reader.fmtdate() in archive.tape_dates.keys() else []
        num_events = len(date_reader.shows_available())
        venue_name = ''
        artist_name = ''
        if num_events > 0:
            venue_name = tapes[date_reader.shownum].venue()
            artist_name = tapes[date_reader.shownum].artist
    elif isinstance(arg, Archivary.BaseTape):
        tape = arg
        tape_info = tape.identifier.replace('-', ' ').split('_')
        venue_name = tape.info[3]
        venue_name = venue_name[offset:]
        tape.artist = tape_info[2]
        artist_name = tape.artist
        num_events = 1
    TMB.scr.clear_area(TMB.scr.venue_bbox)
    TMB.scr.show_text(venue_name, TMB.scr.venue_bbox.origin(), font=TMB.scr.boldsmall, color=color, force=force)
    if len(config.optd['COLLECTIONS']) > 1:
        TMB.scr.clear_area(TMB.scr.track1_bbox)
        TMB.scr.show_text(artist_name, TMB.scr.track1_bbox.origin(), font=TMB.scr.boldsmall, color=color, force=True)
    if num_events > 1:
        TMB.scr.show_nevents(str(num_events), force=force)


def event_loop(state, lock):
    global venue_counter
    key_error_count = 0
    date_reader = state.date_reader
    artist_counter = state.artist_counter
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
    # clear_stagedate = False
    TMB.scr.update_now = False
    free_event.set()
    stagedate_event.set()
    TMB.scr.clear()
    i_artist = 0
    i_tape = 0
    chosen_artists = None

    try:
        while not stop_loop_event.wait(timeout=0.001):
            if not free_event.wait(timeout=0.01):
                continue
            lock.acquire()
            now = datetime.datetime.now()
            n_timer = n_timer + 1
            idle_seconds = (now - last_sdevent).seconds
            idle_second_hand = divmod(idle_seconds, max_second_hand)[1]
            current = retry_call(get_current, state)   # if this fails, try again
            default_start = config.optd['DEFAULT_START_TIME']

            if TMB.screen_event.is_set():
                TMB.scr.refresh()
                TMB.screen_event.clear()
            if stagedate_event.is_set():
                logger.debug(F"year is now {date_reader.date.year}")
                last_sdevent = now
                q_counter = True
                TMB.scr.show_staged_year(date_reader.date)
                show_venue_text(date_reader)
                stagedate_event.clear()
                TMB.scr.wake_up()
                TMB.screen_event.set()
            if choose_artist_event.is_set():
                choice = choose_artist(state)
                TMB.scr.clear()
                if choice:
                    artist_year_dict, chosen_artists = choice
                    i_artist = 0
                    logger.debug(F"Number of chosen_artsts {len(chosen_artists)}")
                else:
                    current = state.get_current()
                    TMB.scr.show_selected_date(current['DATE'], force=True)
                TMB.scr.show_staged_year(date_reader.date, force=True)
                choose_artist_event.clear()
            if (current['PLAY_STATE'] in [config.ENDED, config.INIT, config.READY]) and chosen_artists:
                tapes = artist_year_dict[chosen_artists[i_artist]]
                if i_tape >= len(tapes):
                    i_tape = 1
                    i_artist = i_artist + 1
                    tapes = artist_year_dict[chosen_artists[i_artist]]
                else:
                    i_tape = i_tape + 1
                if i_artist >= len(chosen_artists):
                    continue
                logger.debug(F"artist {i_artist}/{len(chosen_artists)}")
                logger.debug(F"tape number {i_tape}/{len(tapes)}. tapes are {tapes}")
                logger.debug(F"tracks are {tapes[i_tape-1].tracks()}")
                select_tape(tapes[i_tape - 1], state)
            if track_event.is_set():
                update_tracks(state)
                track_event.clear()
                TMB.screen_event.set()
            if TMB.select_event.is_set():
                current = state.get_current()
                TMB.scr.show_selected_date(current['DATE'])
                update_tracks(state)
                TMB.select_event.clear()
                TMB.scr.wake_up()
                TMB.screen_event.set()
            if playstate_event.is_set():
                TMB.scr.show_playstate()
                playstate_event.clear()
                TMB.screen_event.set()
            if q_counter and config.DATE and idle_seconds > QUIESCENT_TIME:
                logger.debug(F"Reverting staged date back to selected date {idle_seconds}> {QUIESCENT_TIME}")
                TMB.scr.show_staged_year(config.DATE)
                TMB.scr.show_venue(config.VENUE)
                q_counter = False
                TMB.screen_event.set()
            if idle_second_hand in refresh_times and idle_second_hand != last_idle_second_hand:
                last_idle_second_hand = idle_second_hand
                # if now.minute != last_idle_minute:
                # if now.day != last_idle_day:
                if (now.hour != last_idle_hour) and now.hour == 5:
                    last_idle_day = now.day
                    last_idle_hour = now.hour
                    last_idle_minute = now.minute
                track_event.set()
                playstate_event.set()
                save_state(state)
                if current['PLAY_STATE'] != config.PLAYING:  # deal with overnight pauses, which freeze the alsa player.
                    if (now - config.PAUSED_AT).seconds > SLEEP_AFTER_SECONDS and state.player.get_prop('audio-device') not in ['null', 'pulse']:
                        logger.info(F"Paused at {config.PAUSED_AT}, sleeping after {SLEEP_AFTER_SECONDS}, now {now}")
                        TMB.scr.sleep()
                        state.player._set_property('audio-device', 'null')
                        state.player.wait_for_property('audio-device', lambda x: x == 'null')
                        state.set(current)
                        playstate_event.set()
                    elif (now - current['WOKE_AT']).seconds > SLEEP_AFTER_SECONDS:
                        TMB.scr.sleep()
                if idle_seconds > QUIESCENT_TIME:
                    if config.DATE:
                        TMB.scr.show_staged_year(config.DATE)
                    try:
                        if current['PLAY_STATE'] > config.INIT:
                            refresh_venue(state)
                    except Exception as e:
                        raise e
                        logger.warning(f'event_loop, error refreshing venue {e}')
                else:
                    TMB.scr.show_staged_year(date_reader.date)
                    show_venue_text(date_reader)
                TMB.screen_event.set()
            lock.release()

    except KeyError as e:
        logger.warning(e)
        key_error_count = key_error_count + 1
        logger.warning(f'{key_error_count} key errors')
        if key_error_count > 100:
            return
    except KeyboardInterrupt as e:
        logger.warning(e)
        exit(0)
    finally:
        pass
        # lock.release()


def get_ip():
    cmd = "hostname -I"
    ip = subprocess.check_output(cmd, shell=True)
    ip = ip.decode().split(' ')[0]
    return ip


"""
while len(get_ip())==0:
    logger.info("Waiting for IP address")
    sleep(2)
"""

try:
    load_options(parms)
except Exception:
    logger.warning("Failed in loading options")
# parms.state_path = os.path.join(os.path.dirname(parms.state_path), F'{config.optd["COLLECTIONS"]}_{os.path.basename(parms.state_path)}')
config.PAUSED_AT = datetime.datetime.now()
config.WOKE_AT = datetime.datetime.now()

TMB = controls.Time_Machine_Board(mdy_bounds=None)
ip_address = get_ip()
TMB.scr.show_text("Time\n  Machine\n   Loading...", color=(0, 255, 255), force=False, clear=True)
TMB.scr.show_text(F"{ip_address}", loc=(0, 100), font=TMB.scr.smallfont, color=(255, 255, 255))

if parms.test_update:
    config.optd = default_options()  # no weirdness during update testing

reload_ids = False
if TMB.rewind.is_pressed:
    TMB.scr.show_text("Reloading\nfrom\narchive.org...", color=(0, 255, 255), force=True, clear=True)
    logger.info('Reloading from archive.org')
    # reload_ids = True
if TMB.stop.is_pressed:
    logger.info('Resetting to factory archive -- nyi')

archive = Archivary.Archivary(parms.dbpath, reload_ids=reload_ids, with_latest=False, collection_list=config.optd['COLLECTIONS'])
player = GD.GDPlayer()
if config.optd['PULSEAUDIO_ENABLE']:
    logger.debug('Setting Audio device to pulse')
    player.set_audio_device('pulse')


@player.property_observer('playlist-pos')
def on_track_event(_name, value):
    logger.info(F'in track event callback {_name}, {value}')
    if value is None:
        config.PLAY_STATE = config.ENDED
        config.PAUSED_AT = datetime.datetime.now()
        try:
            select_button(TMB.select, state)
        except Exception:  # variable state not defined at startup, but is defined later.
            pass
    track_event.set()


@player.event_callback('file-loaded')
def my_handler(event):
    logger.debug('file-loaded')


try:
    kfile = open(knob_sense_path, 'r')
    knob_sense = int(kfile.read())
    kfile.close()
except Exception:
    knob_sense = 7

year_list = archive.year_list()
num_years = max(year_list) - min(year_list)

# get lenght of list of artists. Should I get max for a single year, or just total. Currently getting total.
artists = [list(archive.year_artists(y).keys()) for y in year_list]
artists = [item for sublist in artists for item in sublist]
artists = sorted(list(set(artists)))

TMB.setup_knobs(mdy_bounds=[(0, len(artists) // 10), (0, len(artists)), (0, num_years)])
artist_counter = controls.decade_counter(TMB.m, TMB.d, bounds=(0, len(artists)))

#controls.select_option(TMB,artist_counter,"Choose artist",sorted(list(archive.year_artists(date_reader.date.year).keys())))

date_reader = controls.artist_knob_reader(TMB.y, TMB.m, TMB.d, archive)
date_reader.set_date(*date_reader.next_show())

TMB.m.steps = 1
TMB.d.steps = 1
TMB.y.steps = 0

state = controls.state((date_reader, artist_counter), player)
TMB.m.when_rotated = lambda x: decade_knob(TMB.m, "month", artist_counter)
TMB.d.when_rotated = lambda x: decade_knob(TMB.d, "day", artist_counter)
#TMB.y.when_rotated = lambda x: TMB.decade_knob(TMB.y, "year", counter)

# TMB.m.when_rotated = lambda x: twist_knob(TMB.m, "month", date_reader)
# TMB.d.when_rotated = lambda x: twist_knob(TMB.d, "day", date_reader)
TMB.y.when_rotated = lambda x: twist_knob(TMB.y, "year", date_reader)


TMB.play_pause.when_pressed = lambda button: play_pause_button(button, state)
TMB.play_pause.when_held = lambda button: play_pause_button_longpress(button, state)

TMB.select.when_pressed = lambda button: select_button(button, state)
TMB.select.when_held = lambda button: select_button_longpress(button, state)

TMB.ffwd.when_pressed = lambda button: ffwd_button(button, state)
TMB.ffwd.when_held = lambda button: ffwd_button_longpress(button, state)

TMB.rewind.when_pressed = lambda button: rewind_button(button, state)
TMB.rewind.when_held = lambda button: rewind_button_longpress(button, state)

TMB.stop.when_pressed = lambda button: stop_button(button, state)
TMB.stop.when_held = lambda button: stop_button_longpress(button, state)

TMB.m_button.when_pressed = lambda button: month_button(button, state)
TMB.d_button.when_pressed = lambda button: day_button(button, state)
TMB.y_button.when_pressed = lambda button: year_button(button, state)

TMB.d_button.when_held = lambda button: day_button_longpress(button, state)
# TMB.m_button.when_held = lambda button: month_button_longpress(button,state)
TMB.y_button.when_held = lambda button: year_button_longpress(button, state)

TMB.scr.clear_area(controls.Bbox(0, 0, 160, 100))
TMB.scr.show_text("Powered by\n archive.org", color=(0, 255, 255), force=True)
TMB.scr.show_text(str(len(archive.collection_list)).rjust(3), font=TMB.scr.boldsmall, loc=(120, 100), color=(255, 100, 0), force=True)

if RELOAD_STATE_ON_START:
    load_saved_state(state)


# save_pid()
lock = Lock()
eloop = threading.Thread(target=event_loop, args=[state, lock])


def main():
    if config.optd['AUTO_UPDATE_ARCHIVE']:
        archive_updater = Archivary.Archivary_Updater(state, 3600, stop_update_event, scr=TMB.scr, lock=lock)
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
