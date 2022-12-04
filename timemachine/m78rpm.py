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

knob_sense_path = os.path.join(os.getenv("HOME"), ".knob_sense")

logging.basicConfig(
    format="%(asctime)s.%(msecs)03d %(levelname)s: %(name)s %(message)s",
    level=logging.INFO,
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)
GDLogger = logging.getLogger("timemachine.GD")
controlsLogger = logging.getLogger("timemachine.controls")
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
MAX_LOADABLE_YEARS = 10  # NOTE: this should depend on psutil.virtual_memory()
SHUFFLE_SIZE = 12
MAX_TAPES_PER_ARTIST = 10

config.optd["COLLECTIONS"] = ["georgeblood"]
artist_year_dict = {}  # this needs to be either in state or somewhere.

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
    state_path = os.path.join(config.DB_PATH, "georgeblood_state.json")
    logger.info(f"Loading Saved State from {state_path}")
    state_orig = state
    try:
        current = state.get_current()
        # if not os.path.exists(state_path):
        f = open(state_path, "r")
        loaded_state = json.loads(f.read())
        fields_to_load = [
            "DATE",
            "STAGED_DATE",
            "TRACK_NUM",
            "TAPE_ID",
            "TRACK_TITLE",
            "NEXT_TRACK_TITLE",
            "TRACK_ID",
            "DATE_READER",
            "VOLUME",
        ]
        for field in fields_to_load:
            if field in ["DATE", "DATE_READER"]:
                current[field] = to_date(loaded_state[field])
            else:
                current[field] = loaded_state[field]
        if current["DATE"]:
            state.date_reader.m.steps = current["DATE"].month
            state.date_reader.d.steps = current["DATE"].day
            state.date_reader.y.steps = current["DATE"].year - min(year_list)
            state.date_reader.update()
        elif current["DATE_READER"]:
            state.date_reader.m.steps = current["DATE_READER"].month
            state.date_reader.d.steps = current["DATE_READER"].day
            state.date_reader.y.steps = current["DATE_READER"].year - min(year_list)
            state.date_reader.update()

        current["DATE_READER"] = state.date_reader
        state.player._set_property("volume", current["VOLUME"])
        state.set(current)
        stagedate_event.set()
    except BaseException:
        logger.warning(f"Failed while Loading Saved State from {state_path}")
        # raise
        state = state_orig
    finally:
        current["PLAY_STATE"] = config.INIT
        state.set(current)
    return


@sequential
def save_state(state):
    state_path = os.path.join(config.DB_PATH, "georgeblood_state.json")
    # logger.debug (F"Saving state to {state_path}")
    current = state.get_current()
    with open(state_path, "w") as statefile:
        json.dump(current, statefile, indent=1, default=str)


def decade_knob(knob: RotaryEncoder, label, artist_counter: controls.artist_knob_reader):
    if label == "day":
        TMB.decade_knob(TMB.d, "day", artist_counter)
    elif label == "month":
        TMB.decade_knob(TMB.m, "month", artist_counter)
    TMB.knob_event.set()
    choose_artist_event.set()


def twist_knob(knob: RotaryEncoder, label, date_reader: controls.date_knob_reader):
    if label != "year":
        return
    TMB.twist_knob(knob, label, date_reader)
    TMB.knob_event.set()
    stagedate_event.set()


def set_logger_debug():
    global logger
    global GDLogger
    global controlsLogger
    logger.debug(f"Setting logger levels to {logging.DEBUG}")
    logger.setLevel(logging.DEBUG)
    GDLogger.setLevel(logging.DEBUG)
    controlsLogger.setLevel(logging.INFO)


def shuffle_artist(state):
    global artist_year_dict
    current = state.get_current()
    current["CHOSEN_ARTISTS"] = []
    # it would be good to indicate on the screen that we are shuffling, because this can take a while.
    date_reader = state.date_reader
    year = date_reader.date.year
    config.DATE_RANGE = sorted([year, config.OTHER_YEAR if config.OTHER_YEAR else year])
    artist_counter = state.artist_counter
    date = date_reader.date
    if (max(config.DATE_RANGE) - min(config.DATE_RANGE)) > MAX_LOADABLE_YEARS:  # Do I really need the check?
        date_range = sorted(random.sample(range(*config.DATE_RANGE), MAX_LOADABLE_YEARS))
        logger.info(f"Loading a reduced set of years: {date_range}")
    else:
        date_range = config.DATE_RANGE
    TMB.scr.show_experience(text="Loading. May \n Require 5 Minutes", color=(255, 100, 0), force=True)
    date_reader.archive = Archivary.Archivary(
        reload_ids=reload_ids,
        with_latest=False,
        collection_list=config.optd["COLLECTIONS"],
        date_range=date_range,
    )
    artist_year_dict = date_reader.archive.year_artists(*config.DATE_RANGE)
    # artist_year_dict = archive.year_artists(date.year, config.OTHER_YEAR)
    artist_list = sorted(list(artist_year_dict.keys()))
    chosen_artists = random.sample(artist_list, min(SHUFFLE_SIZE, len(artist_list)))
    if not isinstance(chosen_artists, list):
        chosen_artists = [chosen_artists]
    current = stop_player(state).get_current()
    current["CHOSEN_ARTISTS"] = chosen_artists
    current["PLAY_STATE"] = config.READY
    state.set(current)
    logger.debug(f"artist is now {chosen_artists}")
    return chosen_artists


def choose_artist(state):
    # global artist_year_dict
    TMB.knob_event.clear()
    date_reader = state.date_reader
    artist_counter = state.artist_counter
    archive = date_reader.archive
    date = date_reader.date
    # ayd = archive.year_artists(date.year, config.OTHER_YEAR)
    artist_list = ["RETURN", "Shuffle"] + sorted(list(artist_year_dict.keys()))
    chosen_artists = controls.select_option(TMB, artist_counter, "Choose artist", artist_list)
    TMB.scr.clear()
    if chosen_artists == "RETURN":
        return None
    elif chosen_artists == "Shuffle":
        return shuffle_artist(state)
    if not isinstance(chosen_artists, list):
        chosen_artists = [chosen_artists]
    # current = state.get_current()
    # current['CHOSEN_ARTISTS'] = chosen_artists
    # logger.debug(F"artist is now {chosen_artists}")
    # state.set(current)
    # artist_year_dict = ayd
    return chosen_artists


def select_tape(tape, state, autoplay=True):
    global venue_counter
    if tape._remove_from_archive:
        return
    current = state.get_current()
    if tape.identifier == current["TAPE_ID"]:
        TMB.scr.show_experience(text=f"{controls.get_version()}", color=(255, 100, 0), force=True)
        sleep(1)
        return  # already selected.
    logger.debug(f"select_tape: current state at entry {current}")
    current["PLAY_STATE"] = config.READY  # eject current tape, insert new one in player
    current["TAPE_ID"] = tape.identifier
    logger.info(f"Set TAPE_ID to {current['TAPE_ID']}")
    current["TRACK_NUM"] = -1
    # current['DATE'] = state.date_reader.date
    current["DATE"] = to_date(tape.date)
    id_fields = tape.identifier.replace("-", " ").split("_")
    artist = " ".join(x.capitalize() for x in id_fields[2].split())
    track = " ".join(x.capitalize() for x in id_fields[1].split())
    current["VENUE"] = track.replace(" ", "")  # strip out the spaces
    current["ARTIST"] = artist.replace(" ", "")
    venue_counter = (0, 0)

    try:
        state.player.insert_tape(tape)
        state.player._set_property("volume", current["VOLUME"])
        logger.debug(f"select_tape: current state {current}")
        if autoplay:
            logger.debug("Autoplaying tape")
            TMB.scr.show_playstate(staged_play=True, force=True)
            state.player.play(wait=False)
            current["PLAY_STATE"] = config.PLAYING
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
    artist_tapes = date_reader.archive.resort_tape_date(date_reader.fmtdate())
    if len(artist_tapes) == 0:
        TMB.scr.show_venue("No Audio", color=(255, 255, 255), force=True)
        sleep(2)
        return
    tape = artist_tapes[date_reader.shownum]
    TMB.scr.show_playstate(staged_play=True, force=True)
    state = select_tape(tape, state, autoplay=autoplay)

    logger.debug(f"current state after selecting tape {state}")
    TMB.select_event.set()
    return state


@sequential
def select_button(button, state):
    logger.info("pressing select")
    TMB.select_event.set()

    autoplay = AUTO_PLAY
    sleep(button._hold_time * 1.01)
    if button.is_pressed or button.is_held:
        return
    current = state.get_current()
    if current["PLAY_STATE"] in [config.PAUSED, config.PLAYING]:
        if state.date_reader.date.year in config.DATE_RANGE:  # no change if current year already selected.
            TMB.select_event.clear()
            return
        shuffle_artist(state)
    elif current["PLAY_STATE"] in [config.INIT, config.READY, config.STOPPED]:
        shuffle_artist(state)
    elif current["PLAY_STATE"] == config.ENDED:  # I'm not sure what this does yet.
        logger.debug("setting PLAY_STATE to READY, autoplay to False")
        autoplay = False
        current["PLAY_STATE"] = config.READY
        state.set(current)
    # select_current_artist(state, autoplay=autoplay)
    TMB.scr.wake_up()
    logger.debug(f"current state after select button {state}")
    return


@sequential
def select_button_longpress(button, state):
    logger.debug("long pressing select")
    return


@sequential
def play_pause_button(button, state):
    current = state.get_current()
    if current["EXPERIENCE"] and current["PLAY_STATE"] in [config.PLAYING, config.PAUSED]:
        return
    logger.debug("pressing play_pause")
    if current["PLAY_STATE"] in [config.INIT]:
        logger.info("Selecting current date, and play")
        state = shuffle_artist(state)
        current = state.get_current()
    elif current["PLAY_STATE"] == config.PLAYING:
        logger.info("Pausing on player")
        state.player.pause()
        current["PAUSED_AT"] = datetime.datetime.now()
        current["PLAY_STATE"] = config.PAUSED
    elif current["PLAY_STATE"] in [config.PAUSED, config.STOPPED, config.READY, config.ENDED]:
        current["PLAY_STATE"] = config.PLAYING
        TMB.scr.wake_up()
        TMB.screen_event.set()
        TMB.scr.show_playstate(
            staged_play=True, force=True
        )  # show that we've registered the button-press before blocking call.
        state.player.play(
            wait=False
        )  # this is a blocking call. I could move the "wait_until_playing" to the event handler.
    state.set(current)
    playstate_event.set()


@sequential
def play_pause_button_longpress(button, state):
    global venue_counter
    logger.debug(" longpress of play_pause -- choose random date and play it")
    current = state.get_current()
    if current["EXPERIENCE"]:
        current["EXPERIENCE"] = False
    TMB.scr.show_playstate(
        staged_play=True, force=True
    )  # show that we've registered the button-press before blocking call.
    new_date = random.choice(state.date_reader.archive.dates)
    tape = state.date_reader.archive.best_tape(new_date)
    current["DATE"] = to_date(new_date)
    state.date_reader.set_date(current["DATE"])
    current["VENUE"] = tape.identifier.replace("-", " ").split("_")[2]
    current["ARTIST"] = tape.artist
    venue_counter = (0, 0)
    current_volume = state.player.get_prop("volume")
    state.player._set_property("volume", max(current_volume, 100))
    current["VOLUME"] = state.player.get_prop("volume")

    if current["PLAY_STATE"] in [config.PLAYING, config.PAUSED]:
        state.player.stop()
    state.player.insert_tape(tape)
    current["PLAY_STATE"] = config.PLAYING
    state.player.play(
        wait=False
    )  # this is a blocking call. I could move the "wait_until_playing" to the event handler.

    state.set(current)
    TMB.select_event.set()
    # stagedate_event.set()
    playstate_event.set()


def stop_player(state):
    current = state.get_current()
    if current["PLAY_STATE"] == config.ENDED:
        current["PLAY_STATE"] = config.STOPPED
        state.set(current)

    state.player.stop()
    current["PLAY_STATE"] = config.STOPPED
    current["CHOSEN_ARTISTS"] = []
    current["PAUSED_AT"] = datetime.datetime.now()
    state.set(current)
    playstate_event.set()
    return state


@sequential
def stop_button(button, state):
    current = state.get_current()
    if current["EXPERIENCE"]:
        return
    stop_player(state)


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
    if current["EXPERIENCE"]:
        current_volume = state.player.get_prop("volume")
        state.player._set_property("volume", max(current_volume * 0.9, 40))
        return
    sleep(button._hold_time)
    if button.is_pressed:
        return  # the button is being "held"
    if current["TRACK_NUM"] == 0:
        state.player.stop()
        state.player.play(wait=False)
    elif current["TRACK_NUM"] < len(state.player.playlist):
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
    if current["EXPERIENCE"]:
        current_volume = state.player.get_prop("volume")
        state.player._set_property("volume", min(current_volume * 1.1, 130))
        return
    sleep(button._hold_time)
    if button.is_pressed:
        return  # the button is being "held"
    if current["TRACK_NUM"] < len(state.player.playlist) - 1:  # before the last track
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
    if current["EXPERIENCE"]:
        current["EXPERIENCE"] = False
    else:
        current["EXPERIENCE"] = True
    state.set(current)
    track_event.set()


def month_button_longpress(button, state):
    logger.debug(f"long pressing month_button")
    pixels = TMB.scr.image.tobytes()
    TMB.scr.show_experience(text="Hold 5s to Switch\nto Live Music", color=(0, 255, 0), force=True)
    sleep(5)
    if button.is_held:
        TMB.scr.clear()
        config.optd["MODULE"] = "livemusic"
        config.optd["COLLECTIONS"] = None
        config.save_options(config.optd)
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
    # Move to the next Artist in the current playlist
    stagedate_event.set()


def day_button_longpress(button, state):
    logger.debug("long-pressing day button")
    TMB.scr.sleep()


@sequential
def year_button(button, state):
    # Set a start and end year
    sleep(button._hold_time)
    if button.is_pressed:
        return  # the button is being "held"
    TMB.y_event.set()
    config.OTHER_YEAR = state.date_reader.date.year
    stagedate_event.set()


@sequential
def year_button_longpress(button, state):
    sleep(button._hold_time)
    if not button.is_held:
        return
    ip_address = get_ip()
    TMB.scr.show_experience(text=f"{ip_address}:9090\nto configure", force=True)
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
    if current["EXPERIENCE"]:
        TMB.scr.show_experience()
        return
    if current.get("CHOSEN_ARTISTS", None) is None:
        logger.debug("Not updating tracks because chosen artists is None")
        track_text = " archive.org 78rpm"
        TMB.scr.show_track(track_text, 1, color=(250, 128, 0), raw_text=True)
        return
    TMB.scr.show_track(current["TRACK_TITLE"], 0)
    if len(current["NEXT_TRACK_TITLE"]) > 0:
        TMB.scr.show_track(current["NEXT_TRACK_TITLE"], 1)
    else:
        track_text = current["ARTIST"] if current["ARTIST"] else " archive.org 78rpm"
        TMB.scr.show_track(track_text, 1, color=(250, 128, 0), raw_text=True)


def to_date(d):
    if not d:
        return d
    return datetime.datetime.fromisoformat(d)


@sequential
def refresh_venue(state):
    global venue_counter

    stream_only = False
    tape_color = (0, 255, 255)
    tape = state.player.tape
    if tape is not None:
        tape_id = tape.identifier.split("_")[-1]
        stream_only = tape.stream_only()
        tape_color = (255, 255, 255) if stream_only else (0, 0, 255)
    else:
        tape_id = None

    artist = config.ARTIST if config.ARTIST is not None else ""
    venue = config.VENUE if config.VENUE is not None else artist
    display_string = ""
    screen_width = 13
    n_fields = 2
    n_subfields = 5

    if tape_id is None:
        tape_id = config.ARTIST

    id_color = (0, 255, 255)

    if venue_counter[0] == 0:
        display_string = artist
    elif venue_counter[0] == 1:
        display_string = venue
    """
    elif venue_counter[0] == 2:
        id_color = tape_color
        display_string = tape_id
    """

    display_string = display_string.replace("78_", "")

    display_offset = min(max(0, len(display_string) - (screen_width - 1)), screen_width * venue_counter[1])
    if venue_counter[1] < n_subfields - 1:
        display_offset = 0 if (display_offset < screen_width) else display_offset
        TMB.scr.show_venue(display_string[display_offset:], color=id_color)
    else:
        TMB.scr.show_venue(display_string[-1 * (screen_width - 1) :], color=id_color)

    div, mod = divmod(venue_counter[1] + 1, n_subfields)
    venue_counter = (divmod(venue_counter[0] + div, n_fields)[1], mod)


def test_update(state):
    """ This function is run when the script has been updated. If it passes, then the code
        in the temporary folder may be moved to the working directory (and be used as the latest version).
        If this function fails, then the code should NOT be placed in the working directory """

    current = state.get_current()
    current["EXPERIENCE"] = False
    current["PLAY_STATE"] = config.PLAYING
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
            os.system(f"kill {parms.pid_to_kill}")
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


"""
def handle_artist_knobs(state, i_artist):
    logger.debug(F"handle_artist_knobs: i_artist is {i_artist}")
    choice = choose_artist(state)   # blocking.
    current = state.get_current()

    if choice is None:
        TMB.select_event.clear()
        TMB.scr.show_selected_date(current['DATE'], force=True)
        TMB.scr.show_staged_years(config.STAGED_DATE, force=True)
        return i_artist

    current = state.get_current()
    current['CHOSEN_ARTISTS'] = choice
    state.set(current)

    logger.debug(F"artist is now {chosen_artists}")
    i_artist = 0
    logger.debug(F"Number of chosen_artsts {len(current['CHOSEN_ARTISTS'])}")
    TMB.scr.show_staged_years(config.STAGED_DATE, force=True)
    return i_artist
"""


def event_loop(state, lock):
    global venue_counter
    config.OTHER_YEAR = None
    config.DATE_RANGE = None
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

    try:
        while not stop_loop_event.wait(timeout=0.001):
            if not free_event.wait(timeout=0.01):
                if lock.locked():
                    lock.release()
                continue
            lock.acquire()
            now = datetime.datetime.now()
            n_timer = n_timer + 1
            idle_seconds = (now - last_sdevent).seconds
            idle_second_hand = divmod(idle_seconds, max_second_hand)[1]
            current = retry_call(get_current, state)  # if this fails, try again
            default_start = config.optd["DEFAULT_START_TIME"]

            if TMB.screen_event.is_set():
                TMB.scr.refresh()
                TMB.screen_event.clear()
            if stagedate_event.is_set():
                logger.info(f"year is now {date_reader.date.year}")
                last_sdevent = now
                q_counter = True
                year = date_reader.date.year
                config.STAGED_DATE = sorted([year, config.OTHER_YEAR if config.OTHER_YEAR else year])
                TMB.scr.show_staged_years(config.STAGED_DATE, show_dash=TMB.y_event.is_set(), force=True)
                TMB.y_event.clear()
                stagedate_event.clear()
                TMB.scr.wake_up()
                TMB.screen_event.set()
            if choose_artist_event.is_set():
                # i_artist = handle_artist_knobs(state,i_artist)
                choose_artist_event.clear()
            if (current["PLAY_STATE"] in [config.ENDED, config.INIT, config.READY]) and current.get(
                "CHOSEN_ARTISTS", None
            ):
                logger.debug(
                    "\n\n\n *************************     Dealing with playlist  ************************** \n\n"
                )
                artist_tapes = artist_year_dict[current["CHOSEN_ARTISTS"][i_artist]]
                titles = [x.identifier.split("_")[1] for x in artist_tapes]
                artist_tapes = [
                    artist_tapes[i] for i in sorted([titles.index(x) for x in set(titles)])
                ]  # remove duplicate songs
                if len(artist_tapes) > MAX_TAPES_PER_ARTIST:
                    indices = sorted(random.sample(range(len(artist_tapes)), MAX_TAPES_PER_ARTIST))
                    artist_tapes = [artist_tapes[i] for i in indices]
                if i_tape >= len(artist_tapes):
                    i_tape = 0
                    i_artist = i_artist + 1
                    logger.debug(f"artist change to {i_artist} after i_tape is {i_tape}")
                    if i_artist >= len(current["CHOSEN_ARTISTS"]):  # we have reached the end of the playlist
                        logger.debug(f"artist {i_artist+1}/{len(current['CHOSEN_ARTISTS'])}")
                        i_tape = 0
                        i_artist = 0
                        logger.debug(
                            "\n\n\n *************** Playlist finished ************************* \n\n"
                        )
                        current["CHOSEN_ARTISTS"] = None
                        state.set(current)
                        TMB.scr.show_experience(text="\n archive.org 78rpm", color=(255, 100, 0), force=True)
                        if lock.locked():
                            lock.release()
                        continue
                    artist_tapes = artist_year_dict[current["CHOSEN_ARTISTS"][i_artist]]
                    logger.debug(f"artist tapes are now {artist_tapes}")
                else:
                    i_tape = i_tape + 1
                    logger.debug(f"next tape {i_tape}")
                    if ((i_tape + 1) % 5) == 0:  # flip every 5th song
                        logger.debug("inserting record flip")
                        artist_tapes[i_tape - 1].insert_breaks(breaks={"flip": [0]}, force=True)
                if (((i_artist + 1) % 4) == 0) & (i_tape == 0):  # flip every 4th record
                    logger.debug("changing record")
                    artist_tapes[i_tape - 1].insert_breaks(breaks={"record": [0]}, force=True)
                logger.debug(f"artist {i_artist+1}/{len(current['CHOSEN_ARTISTS'])}")
                logger.debug(f"tape number {i_tape}/{len(artist_tapes)}. tapes are {artist_tapes}")
                logger.debug(f"tracks are {artist_tapes[i_tape-1].tracks()}")
                logger.debug(
                    "\n\n\n *************************   Finished Dealing with playlist  ************************** \n\n"
                )
                select_tape(artist_tapes[i_tape - 1], state)
            if track_event.is_set():
                update_tracks(state)
                track_event.clear()
                TMB.screen_event.set()
            if TMB.select_event.is_set():
                # year = date_reader.date.year
                # config.DATE_RANGE = sorted([year, config.OTHER_YEAR if config.OTHER_YEAR else year])
                # config.STAGED_DATE = sorted([year, config.OTHER_YEAR if config.OTHER_YEAR else year])
                config.OTHER_YEAR = None
                current = state.get_current()
                TMB.scr.show_selected_date(current["DATE"])
                update_tracks(state)
                TMB.select_event.clear()
                TMB.scr.wake_up()
                TMB.screen_event.set()
            if playstate_event.is_set():
                TMB.scr.show_playstate()
                playstate_event.clear()
                TMB.screen_event.set()
            if q_counter and config.DATE_RANGE and idle_seconds > QUIESCENT_TIME:
                logger.debug(f"Reverting staged date back to selected date {idle_seconds}> {QUIESCENT_TIME}")
                TMB.scr.show_staged_years(config.DATE_RANGE)
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
                if (
                    current["PLAY_STATE"] != config.PLAYING
                ):  # deal with overnight pauses, which freeze the alsa player.
                    if (now - config.PAUSED_AT).seconds > SLEEP_AFTER_SECONDS and state.player.get_prop(
                        "audio-device"
                    ) not in ["null", "pulse"]:
                        logger.info(
                            f"Paused at {config.PAUSED_AT}, sleeping after {SLEEP_AFTER_SECONDS}, now {now}"
                        )
                        TMB.scr.sleep()
                        state.player._set_property("audio-device", "null")
                        state.player.wait_for_property("audio-device", lambda x: x == "null")
                        state.set(current)
                        playstate_event.set()
                    elif (now - current["WOKE_AT"]).seconds > SLEEP_AFTER_SECONDS:
                        TMB.scr.sleep()
                if idle_seconds > QUIESCENT_TIME:
                    if config.DATE:
                        year = config.DATE.year
                        TMB.scr.show_staged_years(
                            config.DATE_RANGE if config.DATE_RANGE else config.STAGED_DATE
                        )
                    try:
                        if current["PLAY_STATE"] > config.INIT:
                            refresh_venue(state)
                    except Exception as e:
                        raise e
                        logger.warning(f"event_loop, error refreshing venue {e}")
                else:
                    # year = date_reader.date.year
                    # TMB.scr.show_staged_years(config.STAGED_DATE)
                    if current["PLAY_STATE"] > config.INIT:
                        refresh_venue(state)
                TMB.screen_event.set()
            if lock.locked():
                lock.release()

    except KeyboardInterrupt as e:
        logger.warning(e)
        exit(0)
    #    except KeyError as e:
    except Exception as e:
        logger.warning(e)
        key_error_count = key_error_count + 1
        logger.warning(f"{key_error_count} key errors")
        if key_error_count > 3:
            return
        else:
            logger.warning("event_loop restarting")
            lock.release()
            event_loop(state, lock)
    finally:
        pass
        # lock.release()


def get_ip():
    cmd = "hostname -I"
    ip = subprocess.check_output(cmd, shell=True)
    ip = ip.decode().split(" ")[0]
    return ip


"""
while len(get_ip())==0:
    logger.info("Waiting for IP address")
    sleep(2)
"""

# parms.state_path = os.path.join(os.path.dirname(parms.state_path), F'{config.optd["COLLECTIONS"]}_{os.path.basename(parms.state_path)}')
config.PAUSED_AT = datetime.datetime.now()
config.WOKE_AT = datetime.datetime.now()

TMB = controls.Time_Machine_Board(mdy_bounds=None)
ip_address = get_ip()

TMB.scr.show_text("Time\n  Machine\n   Loading...", color=(0, 255, 255), force=False, clear=True)
TMB.scr.show_text(f"{ip_address}", loc=(0, 100), font=TMB.scr.smallfont, color=(255, 255, 255))

player = GD.GDPlayer()

reload_ids = False
if TMB.rewind.is_pressed:
    TMB.scr.show_text("Reloading\nfrom\narchive.org...", color=(0, 255, 255), force=True, clear=True)
    logger.info("Reloading from archive.org")
    # reload_ids = True
if TMB.stop.is_pressed:
    logger.info("Resetting to factory archive -- nyi")

if config.optd["PULSEAUDIO_ENABLE"]:
    logger.debug("Setting Audio device to pulse")
    player.set_audio_device("pulse")


@player.property_observer("playlist-pos")
def on_track_event(_name, value):
    logger.info(f"in track event callback {_name}, {value}")
    if value is None:
        config.PLAY_STATE = config.ENDED
        config.PAUSED_AT = datetime.datetime.now()
        try:
            select_button(TMB.select, state)
        except Exception:  # variable state not defined at startup, but is defined later.
            pass
    track_event.set()


@player.event_callback("file-loaded")
def my_handler(event):
    logger.debug("file-loaded")


def board_callbacks():
    global TMB
    TMB.m.when_rotated = lambda x: decade_knob(TMB.m, "month", artist_counter)
    TMB.d.when_rotated = lambda x: decade_knob(TMB.d, "day", artist_counter)

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
    TMB.scr.show_text("Powered by\n archive.org\n 78 RPM", color=(0, 255, 255), force=True)


try:
    kfile = open(knob_sense_path, "r")
    knob_sense = int(kfile.read())
    kfile.close()
except Exception:
    knob_sense = 7

# year_list = archive.year_list()
year_list = range(1898, datetime.datetime.now().year)
num_years = max(year_list) - min(year_list)

# get lenght of list of artists. Should I get max for a single year, or just total. Currently getting total.
# artists = archive.year_artists(min(year_list), max(year_list)).keys()
# artists = [item for sublist in artists for item in sublist]
# artists = sorted(list(set(artists)))

# TMB.setup_knobs(mdy_bounds=[(0, len(artists) // 10), (0, len(artists)), (0, num_years)])
TMB.setup_knobs(mdy_bounds=[(0, 1000), (0, 20000), (0, num_years)])
artist_counter = controls.decade_counter(TMB.m, TMB.d, bounds=(0, 20000))
date_reader = controls.artist_knob_reader(TMB.y, TMB.m, TMB.d)
# date_reader.set_date(*date_reader.next_show())

TMB.m.steps = 1
TMB.d.steps = 1
TMB.y.steps = 0

state = controls.state((date_reader, artist_counter), player)

board_callbacks()

# save_pid()


def main(parms_arg):
    global parms
    parms = parms_arg
    if parms.verbose or parms.debug or os.uname().nodename.startswith("deadstream"):
        set_logger_debug()

    lock = Lock()
    load_saved_state(state)

    eloop = threading.Thread(target=event_loop, args=[state, lock])
    # if config.optd['AUTO_UPDATE_ARCHIVE']:
    #    archive_updater = Archivary.Archivary_Updater(state, 3600, stop_update_event, scr=TMB.scr, lock=lock)
    #    archive_updater.start()
    eloop.run()
    exit()
