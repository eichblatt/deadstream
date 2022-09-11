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

knob_sense_path = os.path.join(os.getenv('HOME'), ".knob_sense")

logging.basicConfig(format='%(asctime)s.%(msecs)03d %(levelname)s: %(name)s %(message)s',
                    level=logging.INFO,
                    datefmt='%Y-%m-%d %H:%M:%S')
VERBOSE = 5
logging.addLevelName(VERBOSE, "VERBOSE")
logger = logging.getLogger(__name__)
GDLogger = logging.getLogger('timemachine.GD')
controlsLogger = logging.getLogger('timemachine.controls')
logger.setLevel(logging.INFO)
GDLogger.setLevel(logging.INFO)
controlsLogger.setLevel(logging.WARN)

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

random.seed(datetime.datetime.now().timestamp())  # to ensure that random show will be new each time.
parms = None


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
    state_path = os.path.join(parms.dbpath, 'etree_state.json')
    logger.info(F"Loading Saved State from {state_path}")
    state_orig = state
    try:
        current = state.get_current()
        # if not os.path.exists(state_path):
        f = open(state_path, 'r')
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
        if not config.optd['ON_TOUR_ALLOWED']:
            current['ON_TOUR'] = False
        current['TOUR_STATE'] = config.INIT
        state.set(current)
        stagedate_event.set()
    except FileNotFoundError as e:
        logger.warning(F"{state_path} not present -- using defaults")
    except BaseException as e:
        logger.exception(F"in load_saved_state {e}")
        logger.warning(F"Failed while Loading Saved State from {state_path}")
        # raise
        state = state_orig
    finally:
        current['PLAY_STATE'] = config.INIT
        state.set(current)
    return


@sequential
def save_state(state):
    state_path = os.path.join(parms.dbpath, 'etree_state.json')
    # logger.debug (F"Saving state to {state_path}")
    current = state.get_current()
    with open(state_path, 'w') as statefile:
        json.dump(current, statefile, indent=1, default=str)

# def save_pid():
#    try:
#        pid_file = os.path.join(os.getenv('HOME'),'tm.pid')
#        if os.path.exists(pid_file):
#            os.remove(pid_file)
#        f = open(pid_file,'w')
#        f.write(str(os.getpid()))
#    except Exception as e:
#        logger.exception(f'{e} while trying to write pid file')
#        raise e


def twist_knob(knob: RotaryEncoder, label, date_reader: controls.date_knob_reader):
    TMB.twist_knob(knob, label, date_reader)
    TMB.knob_event.set()
    stagedate_event.set()


def set_logger_debug():
    logger.debug(F"Setting logger levels to {logging.DEBUG}")
    logger.setLevel(logging.DEBUG)
    GDLogger.setLevel(logging.DEBUG)
    controlsLogger.setLevel(logging.INFO)


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
    current['VENUE'] = tape.venue()
    current['ARTIST'] = tape.artist
    venue_counter = (0, 0)

    try:
        state.player.insert_tape(tape)
        state.player._set_property('volume', current['VOLUME'])
        logger.debug(F"select_tape: current state {current}")
        if autoplay:
            TMB.scr.show_playstate(staged_play=True, force=True)
            state.player.play()
            current['PLAY_STATE'] = config.PLAYING
            playstate_event.set()
            state.set(current)
    except Exception as e:
        logger.exception(e)
        pass
    return state


def select_current_date(state, autoplay=True):
    date_reader = state.date_reader
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
    if current['ON_TOUR'] and current['TOUR_STATE'] in [config.READY, config.PLAYING]:
        return
    select_current_date(state, autoplay=autoplay)
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
                sleep(0.25)
                if not button.is_held:
                    break
    tape_id = tapes[itape].identifier
    sbd = tapes[itape].stream_only()
    id_color = (0, 255, 255) if sbd else (0, 0, 255)
    TMB.scr.show_venue(tape_id, color=id_color)
    tape = tapes[itape]
    state = select_tape(tape, state, autoplay=AUTO_PLAY)
    TMB.select_event.set()


@sequential
def play_pause_button(button, state):
    current = state.get_current()
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
    current['VENUE'] = tape.venue()
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
    if current['ON_TOUR'] and current['TOUR_STATE'] in [config.READY, config.PLAYING]:
        return
    if current['PLAY_STATE'] in [config.READY, config.INIT, config.STOPPED]:
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
        sleep(25)
        # if this program hasn't been killed after 25 seconds, then the code was already the latest version
        TMB.scr.show_text("Code is\nup to Date", clear=True, force=True)
        sleep(5)
        TMB.scr.image.frombytes(pixels)
        TMB.scr.refresh(force=True)
        # exit()


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
    if current['TRACK_NUM'] == 0:
        state.player.stop()
        state.player.play()
    if current['TRACK_NUM'] < len(state.player.playlist):
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
    if current['EXPERIENCE'] or (current['ON_TOUR'] and current['TOUR_STATE'] in [config.READY, config.PLAYING]):
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


@sequential
def month_button_longpress(button, state):
    logger.debug(F"long pressing month_button")
    pixels = TMB.scr.image.tobytes()
    TMB.scr.show_experience(text="Hold 5s to Switch\nto 78 RPM", color=(50, 255, 100), force=True)
    sleep(5)
    if button.is_held:
        TMB.scr.clear()
        config.optd['MODULE'] = '78rpm'
        save_options(config.optd)
        cmd = "sudo service timemachine restart"
        os.system(cmd)
        TMB.stop_event.set()
        TMB.scr.wake_up()
        TMB.scr.show_text("Switching\nStand By...", force=True)
        sleep(25)
        # if this program hasn't been killed after 25 seconds, then the code was already the latest version
        TMB.scr.show_text("Failed to Switch\nOoops!", clear=True, force=True)
        sleep(5)
        TMB.scr.image.frombytes(pixels)
        TMB.scr.refresh(force=True)


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
    if current['ON_TOUR']:
        TMB.scr.show_experience(text=F"ON_TOUR:{current['TOUR_YEAR']}\nHold 3s to exit", force=True)
        sleep(3)
        if button.is_held:
            logger.info("   EXITING ON_TOUR mode")
            current['ON_TOUR'] = False
            current['TOUR_YEAR'] = None
            current['TOUR_STATE'] = config.INIT
            TMB.scr.show_experience(text=F"ON_TOUR: Finished\n{ip_address}", force=True)
    elif config.optd['ON_TOUR_ALLOWED']:
        current['ON_TOUR'] = True
        current['TOUR_YEAR'] = state.date_reader.date.year
        current['TOUR_STATE'] = config.INIT
        logger.info(F" ---> ON_TOUR:{current['TOUR_YEAR']}")
        TMB.scr.show_experience(text=F"ON_TOUR:{current['TOUR_YEAR']}\n{ip_address}", force=True)
    sleep(3)
    track_event.set()
    state.set(current)


def update_tracks(state):
    current = state.get_current()
    if current['EXPERIENCE']:
        TMB.scr.show_experience()
    elif current['ON_TOUR'] and current['TOUR_STATE'] in [config.READY, config.PLAYING]:
        TMB.scr.show_experience(text=F"Hold Year to\nExit TOUR {current['TOUR_YEAR']}")
    else:
        TMB.scr.show_track(current['TRACK_TITLE'], 0)
        TMB.scr.show_track(current['NEXT_TRACK_TITLE'], 1)


def to_date(d):
    if not d:
        return d
    return datetime.datetime.fromisoformat(d).date()


@sequential
def play_on_tour(tape, state, seek_to=0):
    global venue_counter
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
    current['ARTIST'] = tape.artist
    venue_counter = (0, 0)
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
    TMB.select_event.set()
    return


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
    current['ON_TOUR'] = False
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
    if isinstance(arg, controls.date_knob_reader):
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
        venue_name = tape.identifier if show_id else tape.venue()
        venue_name = venue_name[offset:]
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
                        TMB.scr.show_experience(text=F"ON_TOUR:{current['TOUR_YEAR']}\nWaiting for show", force=True)
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
                if current['TOUR_STATE'] == config.PLAYING:
                    if current['PLAY_STATE'] == config.ENDED:
                        current['TOUR_STATE'] = config.ENDED
                        state.set(current)
                        track_event.set()
                        logger.debug(F" ENDED!! TOUR_STATE is {current['TOUR_STATE']}, default_start: {default_start}")

            if TMB.screen_event.is_set():
                TMB.scr.refresh()
                TMB.screen_event.clear()
            if stagedate_event.is_set():
                last_sdevent = now
                q_counter = True
                TMB.scr.show_staged_date(date_reader.date)
                show_venue_text(date_reader)
                # if clear_stagedate: stagedate_event.clear()
                # clear_stagedate = not clear_stagedate   # only clear stagedate event after updating twice
                stagedate_event.clear()
                TMB.scr.wake_up()
                TMB.screen_event.set()
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
                TMB.scr.show_staged_date(config.DATE)
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
                    # try:
                    # date_reader.archive.load_archive(with_latest=config.optd['AUTO_UPDATE_ARCHIVE'])
                    # except:
                    # logger.warning("Unable to refresh archive")
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
                        TMB.scr.show_staged_date(config.DATE)
                    try:
                        if current['PLAY_STATE'] > config.INIT:
                            refresh_venue(state)
                    except Exception as e:
                        raise e
                        logger.warning(f'event_loop, error refreshing venue {e}')
                else:
                    TMB.scr.show_staged_date(date_reader.date)
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

config.PAUSED_AT = datetime.datetime.now()
config.WOKE_AT = datetime.datetime.now()

TMB = controls.Time_Machine_Board(mdy_bounds=None)
ip_address = get_ip()
TMB.scr.show_text("Time\n  Machine\n   Loading...", color=(0, 255, 255), force=False, clear=True)
TMB.scr.show_text(F"{ip_address}", loc=(0, 100), font=TMB.scr.smallfont, color=(255, 255, 255))


if TMB.rewind.is_pressed:
    TMB.scr.show_text("Reloading\nfrom\narchive.org...", color=(0, 255, 255), force=True, clear=True)
    logger.info('Reloading from archive.org')
if TMB.stop.is_pressed:
    logger.info('Resetting to factory archive -- nyi')

dbpath = os.path.join(GD.ROOT_DIR, 'metadata')


def set_date_range():
    start_year = 1880
    collection_path = os.path.join(os.getenv('HOME'), '.etree_collection_names.json')
    d = json.load(open(collection_path, 'r'))
    etree_collections = [x['identifier'].lower() for x in d['items']]
    my_collections = [x.lower() for x in config.optd['COLLECTIONS']]
    if set(my_collections).issubset(etree_collections):
        start_year = 1960
    date_range = (start_year, datetime.datetime.now().year)
    return date_range


try:
    date_range = set_date_range()
except Exception as e:
    logger.warning("Error setting date range. Using 1880 as start year")
    date_range = (1880, datetime.datetime.now().year)

if config.RELOAD_COLLECTIONS:
    logger.info('Reloading ids')
logger.info(f"config.optd is now {config.optd}")
archive = Archivary.Archivary(dbpath, reload_ids=config.RELOAD_COLLECTIONS, with_latest=False, collection_list=config.optd['COLLECTIONS'], date_range=date_range)
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
TMB.setup_knobs(mdy_bounds=[(1, 12), (1, 31), (0, num_years)])

if 'GratefulDead' in archive.collection_list:
    TMB.m.steps = 8
    TMB.d.steps = 13
    TMB.y.steps = min(max(0, 1975 - min(year_list)), num_years)
else:
    TMB.m.steps = 1
    TMB.d.steps = 1
    TMB.y.steps = 0

date_reader = controls.date_knob_reader(TMB.y, TMB.m, TMB.d, archive)
if 'GratefulDead' not in archive.collection_list:
    date_reader.set_date(*date_reader.next_show())

state = controls.state(date_reader, player)
TMB.m.when_rotated = lambda x: twist_knob(TMB.m, "month", date_reader)
TMB.d.when_rotated = lambda x: twist_knob(TMB.d, "day", date_reader)
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
TMB.m_button.when_held = lambda button: month_button_longpress(button, state)
TMB.y_button.when_held = lambda button: year_button_longpress(button, state)

TMB.scr.clear_area(controls.Bbox(0, 0, 160, 100))
TMB.scr.show_text("Powered by\n archive.org\n & phish.in", color=(0, 255, 255), force=True)
TMB.scr.show_text(str(len(archive.collection_list)).rjust(3), font=TMB.scr.boldsmall, loc=(120, 100), color=(255, 100, 0), force=True)

# save_pid()
lock = Lock()
eloop = threading.Thread(target=event_loop, args=[state, lock])


def main(parms_arg):
    global parms
    parms = parms_arg
    if parms.verbose or parms.debug:
        set_logger_debug()
    load_saved_state(state)
    if config.optd['AUTO_UPDATE_ARCHIVE'] or config.UPDATE_COLLECTIONS:
        archive_updater = Archivary.Archivary_Updater(state, 3600, stop_update_event, scr=TMB.scr, lock=lock)
        archive_updater.start()
        if config.UPDATE_COLLECTIONS:
            archive_updater.update()  # Do it now
    if parms.debug:
        eloop.start()
    else:
        eloop.run()
        sys.exit()


def main_test_update(parms_arg):
    global parms
    parms = parms_arg
    config.optd = default_options()  # no weirdness during update testing
    load_saved_state(state)
    test_update(state)
