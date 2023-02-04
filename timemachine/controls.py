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
import logging
import os
import string
import subprocess
from bisect import bisect
from threading import BoundedSemaphore, Event
from time import sleep
from typing import Callable

import adafruit_rgb_display.st7735 as st7735
import board
import digitalio
import pkg_resources
from adafruit_rgb_display import color565
from gpiozero import LED, Button, RotaryEncoder
from PIL import Image, ImageDraw, ImageFont
from tenacity import retry
from tenacity.stop import stop_after_delay

from timemachine import Archivary, config

logging.basicConfig(
    format="%(asctime)s.%(msecs)03d %(levelname)s: %(name)s %(message)s",
    level=logging.DEBUG,
    datefmt="%Y-%m-%d %H:%M:%S",
)
VERBOSE = 5
logging.addLevelName(VERBOSE, "VERBOSE")
logger = logging.getLogger(__name__)

ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
FONTS_DIR = os.path.join(ROOT_DIR, "fonts")

screen_semaphore = BoundedSemaphore(1)
state_semaphore = BoundedSemaphore(1)
QUIESCENT_TIME = 20


@retry(stop=stop_after_delay(10))
def retry_call(callable: Callable, *args, **kwargs):
    """Retry a call."""
    return callable(*args, **kwargs)


def with_state_semaphore(func):
    def inner(*args, **kwargs):
        try:
            acquired = state_semaphore.acquire(timeout=5)
            if not acquired:
                logger.warning("State semaphore not acquired after 5 seconds!")
                raise Exception("state semaphore not acquired")
            func(*args, **kwargs)
        except BaseException:
            raise
        finally:
            state_semaphore.release()

    return inner


def with_semaphore(func):
    def inner(*args, **kwargs):
        try:
            acquired = screen_semaphore.acquire(timeout=5)
            if not acquired:
                logger.warning("Screen semaphore not acquired after 5 seconds!")
                raise Exception("screen semaphore not acquired")
            func(*args, **kwargs)
        except BaseException:
            raise
        finally:
            screen_semaphore.release()

    return inner


OS_VERSION = None


def get_os_version():
    global OS_VERSION  # cache the value of os version
    if OS_VERSION is None:
        try:
            cmd = "cat /etc/os-release"
            lines = subprocess.check_output(cmd, shell=True)
            lines = lines.decode().split("\n")
            for line in lines:
                split_line = line.split("=")
                if split_line[0] == "VERSION_ID":
                    OS_VERSION = int(split_line[1].strip('"'))
        except Exception:
            logger.warning("Failed to get OS Version")
    return OS_VERSION


class artist_knob_reader:
    """A set of knobs to read the year, and the artist"""

    def __init__(self, y: RotaryEncoder, m: RotaryEncoder, d: RotaryEncoder, archive=None):
        self.date = None
        self.shownum = 0
        self.archive = archive
        if isinstance(archive, int):
            self.year_baseline = archive
        elif archive is None:
            self.year_baseline = 1898
        else:
            self.year_baseline = min(archive.year_list())
        self.y = y
        self.m = m
        self.d = d
        self._update()

    def __str__(self):
        return self.__repr__()

    def __repr__(self):
        avail = ""
        shows = self.shows_available()
        if len(shows) > 0:
            avail = f"{shows} shows Available. Now at {shows[self.shownum]}"
        return f'Date Knob Says: {self.date.strftime("%Y-%m-%d")}. {avail}'

    def update(self):
        self.shownum = 0
        self._update()

    def _update(self):
        m_val = self.m.steps
        d_val = self.d.steps
        y_val = self.y.steps + self.year_baseline
        logger.debug(f"updating date reader. m:{m_val},d:{d_val},y:{y_val}")
        self.date = datetime.date(y_val, 1, 1)
        logger.debug(f"date reader date {self.date}")

    def set_date(self, date, shownum=0):
        new_month, new_day, new_year = (date.month, date.day, date.year)
        self.m.steps = new_month
        self.d.steps = new_day
        self.y.steps = new_year - min((self.archive).year_list())
        self.shownum = divmod(shownum, max(1, len(self.shows_available())))[1]
        self._update()

    def fmtdate(self):
        if self.date is None:
            return None
        return self.date.strftime("%Y-%m-%d")

    def venue(self):
        if self.tape_available():
            try:
                t = self.archive.best_tape(self.fmtdate(), resort=False)
                return t.venue()
            except Exception:
                return ""
        return ""

    def shows_available(self):
        if self.archive is None:
            return []
        self._update()
        if self.fmtdate() in self.archive.tape_dates.keys():
            shows = [t.artist for t in self.archive.tape_dates[self.fmtdate()]]
            return list(dict.fromkeys(shows))
        else:
            return []

    def tape_available(self):
        return len(self.shows_available()) > 0

    def next_show(self):
        if self.archive is None:
            return None
        self._update()
        if self.shownum < len(self.shows_available()) - 1:
            return (self.date, self.shownum + 1)
        else:
            return (self.next_date(), 0)

    def next_date(self):
        if self.archive is None:
            return None
        self._update()
        for d in self.archive.dates:
            if d > self.fmtdate():
                return datetime.datetime.fromisoformat(d).date()
        return self.date


class date_knob_reader:
    def __init__(self, y: RotaryEncoder, m: RotaryEncoder, d: RotaryEncoder, archive=None):
        self.date = None
        self.shownum = 0
        self.archive = archive
        self.y = y
        self.m = m
        self.d = d
        self.maxd = [31, 29, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]  # max days in a month.
        self.year_baseline = 1965 if archive is None else min(archive.year_list())
        self._update()

    def __str__(self):
        return self.__repr__()

    def __repr__(self):
        avail = ""
        shows = self.shows_available()
        if len(shows) > 0:
            avail = f"{shows} shows Available. Now at {shows[self.shownum]}"
        return f'Date Knob Says: {self.date.strftime("%Y-%m-%d")}. {avail}'

    def update(self):
        self.shownum = 0
        self._update()

    def _update(self):
        m_val = self.m.steps
        d_val = self.d.steps
        y_val = self.y.steps + self.year_baseline
        logger.debug(f"updating date reader. m:{m_val},d:{d_val},y:{y_val}")
        if d_val > self.maxd[m_val - 1]:
            self.d.steps = self.maxd[m_val - 1]
            d_val = self.d.steps
        try:
            self.date = datetime.date(y_val, m_val, d_val)
        except ValueError:
            self.d.steps = self.d.steps - 1
            d_val = d_val - 1
            self.date = datetime.date(y_val, m_val, d_val)
        logger.debug(f"date reader date {self.date}")

    def set_date(self, date, shownum=0):
        new_month, new_day, new_year = (date.month, date.day, date.year)
        self.m.steps = new_month
        self.d.steps = new_day
        self.y.steps = new_year - min((self.archive).year_list())
        self.shownum = divmod(shownum, max(1, len(self.shows_available())))[1]
        self._update()

    def fmtdate(self):
        if self.date is None:
            return None
        return self.date.strftime("%Y-%m-%d")

    def venue(self):
        if self.tape_available():
            try:
                t = self.archive.best_tape(self.fmtdate(), resort=False)
                return t.venue()
            except Exception:
                return ""
        return ""

    def shows_available(self):
        if self.archive is None:
            return []
        self._update()
        if self.fmtdate() in self.archive.tape_dates.keys():
            shows = [t.artist for t in self.archive.tape_dates[self.fmtdate()]]
            return list(dict.fromkeys(shows))
        else:
            return []

    def tape_available(self):
        return len(self.shows_available()) > 0

    def next_show_by_artist(self, artist):
        if self.archive is None:
            return None
        self._update()
        current_index = bisect(self.archive.dates, self.fmtdate())
        for d in self.archive.dates[current_index:] + self.archive.dates[:current_index]:
            artists = [t.artist for t in self.archive.tape_dates[d]]
            artists = list(dict.fromkeys(artists))  # make it the unique set
            if not artist in artists:
                continue
            shownum = artists.index(artist)
            logger.debug(f" artist is {artist}. artists: {artists}. date {d}. Shownum {shownum}")
            return (datetime.datetime.fromisoformat(d).date(), shownum)
        return None

    def next_show(self):
        if self.archive is None:
            return None
        self._update()
        if self.shownum < len(self.shows_available()) - 1:
            return (self.date, self.shownum + 1)
        else:
            return (self.next_date(), 0)

    def next_date(self):
        if self.archive is None:
            return None
        self._update()
        current_index = bisect(self.archive.dates, self.fmtdate())
        for d in self.archive.dates[current_index:] + self.archive.dates[:current_index]:
            return datetime.datetime.fromisoformat(d).date()
        return self.date


class decade_counter:
    def __init__(self, tens: RotaryEncoder, ones: RotaryEncoder, bounds=(None, None)):
        self.bounds = bounds
        self.tens = tens
        self.ones = ones
        self.set_value(tens.steps, ones.steps)

    def set_value(self, tens_val, ones_val):
        self.value = tens_val * 10 + ones_val
        if self.bounds[0] is not None:
            self.value = max(self.value, self.bounds[0])
        if self.bounds[1] is not None:
            self.value = min(self.value, self.bounds[1])
        self.tens.steps, self.ones.steps = divmod(self.value, 10)
        return self.value

    def get_value(self):
        return self.value


class Time_Machine_Board:
    """TMB class describes and addresses the hardware of the Time Machine Board"""

    def __init__(self, mdy_bounds=[(0, 9), (0, 9), (0, 9)], upside_down=False):
        self.events = []
        self.setup_events()
        self.clear_events()
        self.setup_knobs(mdy_bounds)
        self.setup_buttons()
        self.setup_screen(upside_down)

    def setup_knobs(self, mdy_bounds):
        if mdy_bounds is None:
            return
        knob_sense = self.get_knob_sense()
        self.m = retry_call(
            RotaryEncoder,
            config.month_pins[knob_sense & 1],
            config.month_pins[~knob_sense & 1],
            max_steps=0,
            threshold_steps=mdy_bounds[0],
        )
        self.d = retry_call(
            RotaryEncoder,
            config.day_pins[(knob_sense >> 1) & 1],
            config.day_pins[~(knob_sense >> 1) & 1],
            max_steps=0,
            threshold_steps=mdy_bounds[1],
        )
        self.y = retry_call(
            RotaryEncoder,
            config.year_pins[(knob_sense >> 2) & 1],
            config.year_pins[~(knob_sense >> 2) & 1],
            max_steps=0,
            threshold_steps=mdy_bounds[2],
        )

    def setup_buttons(self):
        self.m_button = retry_call(Button, config.month_pins[2])
        self.d_button = retry_call(Button, config.day_pins[2], hold_time=0.3, hold_repeat=False)
        self.y_button = retry_call(Button, config.year_pins[2], hold_time=0.5)

        self.rewind = retry_call(Button, config.rewind_pin)
        self.ffwd = retry_call(Button, config.ffwd_pin)
        self.play_pause = retry_call(Button, config.play_pause_pin)
        self.select = retry_call(Button, config.select_pin, hold_time=2, hold_repeat=True)
        self.stop = retry_call(Button, config.stop_pin)

    def setup_screen(self, upside_down=False):
        self.scr = screen(upside_down)

    def setup_events(self):
        self.button_event = Event()
        self.knob_event = Event()
        self.screen_event = Event()
        self.rewind_event = Event()
        self.stop_event = Event()  # stop button
        self.ffwd_event = Event()
        self.play_pause_event = Event()
        self.select_event = Event()
        self.m_event = Event()
        self.d_event = Event()
        self.y_event = Event()
        self.m_knob_event = Event()
        self.d_knob_event = Event()
        self.y_knob_event = Event()
        self.events = [
            self.button_event,
            self.knob_event,
            self.screen_event,
            self.rewind_event,
            self.stop_event,
            self.ffwd_event,
            self.play_pause_event,
            self.select_event,
            self.m_event,
            self.d_event,
            self.y_event,
            self.m_knob_event,
            self.d_knob_event,
            self.y_knob_event,
        ]

    def clear_events(self):
        _ = [x.clear() for x in self.events]

    def twist_knob(self, knob: RotaryEncoder, label, date_reader: date_knob_reader):
        if knob.is_active:
            logger.debug(f"Knob {label} steps={knob.steps} value={knob.value}")
        else:
            if knob.steps < knob.threshold_steps[0]:
                knob.steps = knob.threshold_steps[0]
            if knob.steps > knob.threshold_steps[1]:
                knob.steps = knob.threshold_steps[1]
            logger.debug(f"Knob {label} is inactive")
        date_reader.update()

    def decade_knob(self, knob: RotaryEncoder, label, counter: decade_counter):
        if knob.is_active:
            print(f"Knob {label} steps={knob.steps} value={knob.value}")
        else:
            if knob.steps < knob.threshold_steps[0]:
                if label in ["year", "ones"] and counter.tens.steps > counter.tens.threshold_steps[0]:
                    knob.steps = knob.threshold_steps[1]
                    counter.tens.steps = max(counter.tens.threshold_steps[0], counter.tens.steps - 1)
                else:
                    knob.steps = knob.threshold_steps[0]
            if knob.steps > knob.threshold_steps[1]:
                if label in ["year", "ones"] and counter.tens.steps < counter.tens.threshold_steps[1]:
                    knob.steps = knob.threshold_steps[0]
                    counter.tens.steps = min(counter.tens.threshold_steps[1], counter.tens.steps + 1)
                else:
                    knob.steps = knob.threshold_steps[1]
            print(f"Knob {label} is inactive")
        counter.set_value(counter.tens.steps, counter.ones.steps)
        if label == "month":
            self.m_knob_event.set()
        if label == "day":
            self.d_knob_event.set()
        if label == "year":
            self.y_knob_event.set()

    def get_knob_sense(self):
        knob_sense_path = os.path.join(os.getenv("HOME"), ".knob_sense")
        try:
            kfile = open(knob_sense_path, "r")
            knob_sense = int(kfile.read())
            if knob_sense > 7 or knob_sense < 0:
                raise ValueError
            kfile.close()
        except Exception as e:
            logger.warning(f"error in get_knob_sense {e}. Setting knob_sense to 0")
            knob_sense = 0
        finally:
            return knob_sense

    def rewind_button(self, button):
        logger.debug("pressing or holding rewind")
        self.button_event.set()
        self.rewind_event.set()

    def select_button(self, button):
        logger.debug("pressing select")
        self.button_event.set()
        self.select_event.set()

    def stop_button(self, button):
        logger.debug("pressing stop")
        self.button_event.set()
        self.stop_event.set()

    def ffwd_button(self, button):
        logger.debug("pressing ffwd")
        self.button_event.set()
        self.ffwd_event.set()

    def play_pause_button(self, button):
        logger.debug("pressing play_pause")
        self.button_event.set()
        self.play_pause_event.set()

    def month_button(self, button):
        logger.debug("pressing or holding rewind")
        self.button_event.set()
        self.m_event.set()

    def day_button(self, button):
        logger.debug("pressing or holding rewind")
        self.button_event.set()
        self.d_event.set()

    def year_button(self, button):
        logger.debug("pressing or holding rewind")
        self.button_event.set()
        self.y_event.set()


def select_option(TMB, counter, message, chooser):
    if type(chooser) == type(lambda: None):
        choices = chooser()
    else:
        choices = chooser
    scr = TMB.scr
    scr.clear()
    counter.set_value(0, 0)
    selected = None
    screen_height = 5
    screen_width = 14
    update_now = scr.update_now
    scr.update_now = False
    TMB.stop_event.clear()
    TMB.rewind_event.clear()
    TMB.select_event.clear()

    scr.show_text(message, loc=(0, 0), font=scr.smallfont, color=(0, 255, 255), force=True)
    (text_width, text_height) = scr.smallfont.getsize(message)

    text_height = text_height + 1
    y_origin = text_height * (1 + message.count("\n"))
    selection_bbox = Bbox(0, y_origin, 160, 128)

    while not TMB.select_event.is_set():
        if TMB.rewind_event.is_set():
            if type(chooser) == type(lambda: None):
                choices = chooser()
            else:
                choices = chooser
            TMB.rewind_event.clear()
        scr.clear_area(selection_bbox, force=False)
        x_loc = 0
        y_loc = y_origin
        step = divmod(counter.value, len(choices))[1]

        text = "\n".join(choices[max(0, step - int(screen_height / 2)) : step])
        (text_width, text_height) = scr.smallfont.getsize(text)
        scr.show_text(text, loc=(x_loc, y_loc), font=scr.smallfont, force=False)
        y_loc = y_loc + text_height * (1 + text.count("\n"))

        if len(choices[step]) > screen_width:
            text = ">" + ".." + choices[step][-13:]
        else:
            text = ">" + choices[step]
        (text_width, text_height) = scr.smallfont.getsize(text)
        scr.show_text(text, loc=(x_loc, y_loc), font=scr.smallfont, color=(0, 0, 255), force=False)
        y_loc = y_loc + text_height

        text = "\n".join(choices[step + 1 : min(step + screen_height, len(choices))])
        (text_width, text_height) = scr.smallfont.getsize(text)
        scr.show_text(text, loc=(x_loc, y_loc), font=scr.smallfont, force=True)

        sleep(0.01)
    TMB.select_event.clear()
    selected = choices[step]
    # scr.show_text(F"So far: \n{selected}",loc=selected_bbox.origin(),color=(255,255,255),font=scr.smallfont,force=True)

    logger.info(f"word selected {selected}")
    scr.update_now = update_now
    return selected


def select_chars(TMB, counter, message, message2="So Far", character_set=string.printable):
    scr = TMB.scr
    scr.clear()
    selected = ""
    counter.set_value(0, 1)
    screen_width = 12
    update_now = scr.update_now
    scr.update_now = False
    TMB.stop_event.clear()
    TMB.select_event.clear()

    scr.show_text(message, loc=(0, 0), font=scr.smallfont, color=(0, 255, 255), force=True)
    (text_width, text_height) = scr.smallfont.getsize(message)

    y_origin = text_height * (1 + message.count("\n"))
    selection_bbox = Bbox(0, y_origin, 160, y_origin + 22)
    selected_bbox = Bbox(0, y_origin + 21, 160, 128)

    while not TMB.stop_event.is_set():
        while not TMB.select_event.is_set() and not TMB.stop_event.is_set():
            scr.clear_area(selection_bbox, force=False)
            # scr.draw.rectangle((0,0,scr.width,scr.height),outline=0,fill=(0,0,0))
            x_loc = 0
            y_loc = y_origin

            text = "DEL"
            (text_width, text_height) = scr.oldfont.getsize(text)
            if counter.value == 0:  # we are deleting
                scr.show_text(text, loc=(x_loc, y_loc), font=scr.oldfont, color=(0, 0, 255), force=False)
                scr.show_text(
                    character_set[:screen_width], loc=(x_loc + text_width, y_loc), font=scr.oldfont, force=True
                )
                continue
            scr.show_text(text, loc=(x_loc, y_loc), font=scr.oldfont, force=False)
            x_loc = x_loc + text_width

            # print the white before the red, if applicable
            text = character_set[max(0, -1 + counter.value - int(screen_width / 2)) : -1 + counter.value]
            for x in character_set[94:]:
                text = text.replace(x, "\u25A1")
            (text_width, text_height) = scr.oldfont.getsize(text)
            scr.show_text(text, loc=(x_loc, y_loc), font=scr.oldfont, force=False)
            x_loc = x_loc + text_width

            # print the red character
            text = character_set[-1 + min(counter.value, len(character_set))]
            if text == " ":
                text = "SPC"
            elif text == "\t":
                text = "\\t"
            elif text == "\n":
                text = "\\n"
            elif text == "\r":
                text = "\\r"
            elif text == "\x0b":
                text = "\\v"
            elif text == "\x0c":
                text = "\\f"
            (text_width, text_height) = scr.oldfont.getsize(text)
            scr.show_text(text, loc=(x_loc, y_loc), font=scr.oldfont, color=(0, 0, 255), force=False)
            x_loc = x_loc + text_width

            # print the white after the red, if applicable
            text = character_set[counter.value : min(-1 + counter.value + screen_width, len(character_set))]
            for x in character_set[94:]:
                text = text.replace(x, "\u25A1")
            (text_width, text_height) = scr.oldfont.getsize(text)
            scr.show_text(text, loc=(x_loc, y_loc), font=scr.oldfont, force=True)
            x_loc = x_loc + text_width

            sleep(0.1)
        TMB.select_event.clear()
        if TMB.stop_event.is_set():
            continue
        if counter.value == 0:
            selected = selected[:-1]
            scr.clear_area(selected_bbox, force=False)
        else:
            selected = selected + character_set[-1 + counter.value]
        scr.clear_area(selected_bbox, force=False)
        scr.show_text(
            f"{message2}:\n{selected[-screen_width:]}",
            loc=selected_bbox.origin(),
            color=(255, 255, 255),
            font=scr.oldfont,
            force=True,
        )

    logger.info(f"word selected {selected}")
    scr.update_now = update_now
    return selected


def get_version():
    __version__ = "v1.0"
    try:
        latest_tag_path = pkg_resources.resource_filename("timemachine", ".latest_tag")
        with open(latest_tag_path, "r") as tag:
            __version__ = tag.readline()
        __version__ = __version__.strip()
        return __version__
    except Exception as e:
        logging.warning(f"get_version error {e}")
    finally:
        return __version__


class Bbox:
    def __init__(self, x0, y0, x1, y1):
        self.corners = (x0, y0, x1, y1)
        self.x0, self.y0, self.x1, self.y1 = self.corners

    def __str__(self):
        return self.__repr__()

    def __repr__(self):
        return f"Bbox: x0 {self.x0},y0 {self.y0},x1 {self.x1},y1 {self.y1}"

    def width(self):
        return self.x1 - self.x0

    def height(self):
        return self.y1 - self.y0

    def origin(self):
        return (self.x0, self.y0)

    def topright(self):
        return (self.x1, self.y1)

    def size(self):
        return (int(self.height()), int(self.width()))

    def center(self):
        return (int((self.x0 + self.x1) / 2), int((self.y0 + self.y1) / 2))

    def shift(self, d):
        return Bbox(self.x0 - d.x0, self.y0 - d.y0, self.x1 - d.x1, self.y1 - d.y1)


class screen:
    def __init__(self, upside_down=False, name="screen"):
        cs_pin = digitalio.DigitalInOut(board.CE0)
        dc_pin = digitalio.DigitalInOut(board.D24)
        reset_pin = digitalio.DigitalInOut(board.D25)
        BAUDRATE = 40000000
        spi = board.SPI()
        self.name = name
        self.active = False
        rotation_angle = 90 if not upside_down else 270
        self.disp = st7735.ST7735R(spi, rotation=rotation_angle, cs=cs_pin, dc=dc_pin, rst=reset_pin, baudrate=BAUDRATE)

        self.bgcolor = color565(0, 0, 0)
        self.led = LED(config.screen_led_pin, initial_value=True)
        # --- swap width/height, if
        if self.disp.rotation % 180 == 90:
            height, width = self.disp.width, self.disp.height
        else:
            width, height = self.disp.width, self.disp.height
        self.width, self.height = width, height
        logger.debug(f" ---> disp {self.disp.width},{self.disp.height}")
        self.boldfont = ImageFont.truetype(
            pkg_resources.resource_filename("timemachine.fonts", "DejaVuSansMono-Bold.ttf"), 33
        )
        self.boldsmall = ImageFont.truetype(
            pkg_resources.resource_filename("timemachine.fonts", "DejaVuSansMono-Bold.ttf"), 22
        )
        self.font = ImageFont.truetype(pkg_resources.resource_filename("timemachine.fonts", "ariallgt.ttf"), 30)
        self.smallfont = ImageFont.truetype(pkg_resources.resource_filename("timemachine.fonts", "ariallgt.ttf"), 20)
        self.oldfont = ImageFont.truetype(pkg_resources.resource_filename("timemachine.fonts", "FreeMono.ttf"), 20)
        self.largefont = ImageFont.truetype(pkg_resources.resource_filename("timemachine.fonts", "FreeMono.ttf"), 30)
        self.hugefont = ImageFont.truetype(pkg_resources.resource_filename("timemachine.fonts", "FreeMono.ttf"), 40)

        self.image = Image.new("RGB", (width, height))
        self.draw = ImageDraw.Draw(self.image)  # draw using this object. Display image when complete.

        self.staged_years = (-1, -1)
        self.staged_date = None
        self.selected_date = None

        self.staged_date_bbox = Bbox(0, 0, 160, 31)
        self.selected_date_bbox = Bbox(0, 100, 160, 128)
        self.venue_bbox = Bbox(0, 31, 160, 56)
        self.nevents_bbox = Bbox(148, 31, 160, 56)
        self.track1_bbox = Bbox(0, 55, 160, 77)
        self.track2_bbox = Bbox(0, 78, 160, 100)
        self.playstate_bbox = Bbox(130, 100, 160, 128)
        self.sbd_bbox = Bbox(155, 100, 160, 108)
        self.exp_bbox = Bbox(0, 55, 160, 100)

        self.update_now = True
        self.sleeping = False

    @with_semaphore
    def refresh(self, force=True):
        if self.sleeping:
            return
        if self.update_now or force:
            self.disp.image(self.image)

    def clear_area(self, bbox, force=False):
        self.draw.rectangle(bbox.corners, outline=0, fill=(0, 0, 0))
        if force or self.update_now:
            self.refresh(True)

    def clear(self):
        self.draw.rectangle((0, 0, self.width, self.height), outline=0, fill=(0, 0, 0))
        self.refresh(True)

    def sleep(self):
        self.led.off()
        pixels = self.image.tobytes()
        self.clear()
        self.sleeping = True
        self.image.frombytes(pixels)

    def wake_up(self):
        config.WOKE_AT = datetime.datetime.now()
        self.sleeping = False
        self.led.on()
        if self.update_now:
            self.refresh(force=False)

    def show_text(self, text, loc=(0, 0), font=None, color=(255, 255, 255), stroke_width=0, force=False, clear=False):
        if text is None:
            text = " "
        if font is None:
            font = self.font
        (text_width, text_height) = font.getsize(text)
        logger.debug(f" show_text {text}. text_size {text_height},{text_width}")
        if clear:
            self.clear()
        self.draw.text(loc, text, font=font, stroke_width=stroke_width, fill=color)
        if force or self.update_now:
            self.refresh(True)

    def scroll_venue(self, color=(0, 255, 255), stroke_width=0, inc=15):
        """This function can be called in a thread from the main.
        eg.
        venue_thread = threading.Thread(target=s.scroll_venue,name="venue_scroll",args=(),kwargs={'stroke_width':0,'inc':10})
        venue_thread.start()
        s.venue_name ="Fillmore West, San Francisco, CA"

        It works, but eats a lot of cycles. I'm not ready to go in this direction yet
        """
        bbox = self.venue_bbox
        font = self.boldsmall
        self.clear_area(bbox)
        while True:
            text = self.venue_name
            (text_width, text_height) = font.getsize(text)
            excess = text_width - bbox.width()
            self.draw.text(bbox.origin(), text, font=font, fill=color, stroke_width=stroke_width)
            if excess > 0:
                self.show_text(text, bbox.origin(), font=font, color=color, stroke_width=stroke_width)
                sleep(2)
                for i in range(int(excess / inc) + 2):
                    # logger.debug(F"scrolling excess {excess}, inc: {inc}, i:{i}")
                    if self.venue_name != text:
                        break
                    # sleep(0.005)
                    self.clear_area(bbox)
                    self.show_text(
                        text,
                        bbox.shift(Bbox(inc * i, 0, 0, 0)).origin(),
                        font=font,
                        color=color,
                        stroke_width=stroke_width,
                    )
                sleep(1)
                self.clear_area(bbox)

    def show_experience(self, text="Press Month to\nExit Experience", color=(255, 255, 255), force=False):
        self.clear_area(self.exp_bbox)
        self.show_text(text, self.exp_bbox.origin(), font=self.smallfont, color=color, stroke_width=1, force=force)

    def show_nevents(self, num_events, color=(255, 100, 0), force=False):
        self.clear_area(self.nevents_bbox)
        self.show_text(str(num_events), self.nevents_bbox.origin(), font=self.boldsmall, color=color, force=force)

    def show_venue(self, arg, color=(0, 255, 255), force=False):
        self.clear_area(self.venue_bbox)
        self.show_text(arg, self.venue_bbox.origin(), font=self.boldsmall, color=color, force=force)

    def show_staged_years(self, years, color=(0, 255, 255), show_dash=False, force=False):
        if isinstance(years, datetime.date):
            self.staged_date = years
            years = [years.year, years.year]
        if len(years) != 2:
            logger.warning("show_staged_years: Cannot pass years list longer than 2")
            return
        if years[0] is None:
            return
        if min(years) < 1800:
            logger.warning("show_staged_years: min year less than 1800")
            return
        years = sorted(years)
        if (years == self.staged_years) and not force:
            return
        self.clear_area(self.staged_date_bbox)
        start_year = str(years[0])
        end_year = str(years[1] % 100).rjust(2, "0")
        if years[0] < years[1]:
            if years[1] // 100 > years[0] // 100:  # different century
                text = f"{start_year}-'{end_year}"
            else:
                text = f"{start_year}-{end_year}"
        else:
            if show_dash:  # waiting for input
                text = f"{start_year}-"
            else:
                text = f"{start_year}"
        logger.debug(f"staged date string {text}")
        self.show_text(text, self.staged_date_bbox.origin(), self.boldfont, color=color, force=force)
        self.staged_years = years

    def show_staged_year(self, date, color=(0, 255, 255), force=False):
        if (date == self.staged_date) and not force:
            return
        self.clear_area(self.staged_date_bbox)
        text = f"{date.year}"
        logger.debug(f"staged date string {text}")
        self.show_text(text, self.staged_date_bbox.origin(), self.boldfont, color=color, force=force)
        self.staged_date = date

    def show_staged_date(self, date, color=(0, 255, 255), force=False):
        if date == self.staged_date:
            return
        self.clear_area(self.staged_date_bbox)
        month = str(date.month).rjust(2)
        day = str(date.day).rjust(2)
        year = str(date.year % 100).rjust(2, "0")
        text = month + "-" + day + "-" + year
        logger.debug(f"staged date string {text}")
        self.show_text(text, self.staged_date_bbox.origin(), self.boldfont, color=color, force=force)
        self.staged_date = date

    def show_selected_date(self, date, color=(255, 255, 255), force=False):
        if (date == self.selected_date) and not force:
            return
        self.clear_area(self.selected_date_bbox)
        month = str(date.month).rjust(2)
        day = str(date.day).rjust(2)
        year = str(date.year).rjust(4)
        text = month + "-" + day + "-" + year
        self.show_text(text, self.selected_date_bbox.origin(), self.boldsmall, color=color, force=force)
        self.selected_date = date

    def show_track(self, text, trackpos, color=(120, 0, 255), raw_text=False, force=False):
        text = text if raw_text else " ".join(x.capitalize() for x in text.split())
        bbox = self.track1_bbox if trackpos == 0 else self.track2_bbox
        self.clear_area(bbox)
        self.draw.text(bbox.origin(), text, font=self.smallfont, fill=color, stroke_width=1)
        if force or self.update_now:
            self.refresh(True)

    def show_playstate(self, staged_play=False, color=(0, 100, 255), sbd=None, force=False):
        logger.debug(f"showing playstate {config.PLAY_STATE}")
        bbox = self.playstate_bbox
        self.clear_area(bbox)
        if staged_play:
            self.draw.regular_polygon((bbox.center(), 10), 3, rotation=30, fill=color)
            self.draw.regular_polygon((bbox.center(), 8), 3, rotation=30, fill=(0, 0, 0))
            if force or self.update_now:
                self.refresh(True)
            return
        if config.PLAY_STATE == config.PLAYING:
            self.draw.regular_polygon((bbox.center(), 10), 3, rotation=30, fill=color)
        elif config.PLAY_STATE == config.PAUSED:
            self.draw.line([(bbox.x0 + 10, bbox.y0 + 4), (bbox.x0 + 10, bbox.y0 + 20)], width=4, fill=color)
            self.draw.line([(bbox.x0 + 20, bbox.y0 + 4), (bbox.x0 + 20, bbox.y0 + 20)], width=4, fill=color)
        elif config.PLAY_STATE == config.STOPPED:
            self.draw.regular_polygon((bbox.center(), 10), 4, rotation=0, fill=color)
        elif config.PLAY_STATE in [config.INIT, config.READY, config.ENDED]:
            pass
        if sbd:
            self.show_soundboard(sbd)
        if force or self.update_now:
            self.refresh(True)

    def show_soundboard(self, sbd, color=(255, 255, 255)):
        if not sbd:
            self.draw.regular_polygon((self.sbd_bbox.center(), 3), 4, rotation=45, fill=(0, 0, 0))
            return
        logger.debug("showing soundboard status")
        self.draw.regular_polygon((self.sbd_bbox.center(), 3), 4, rotation=45, fill=color)


class state:
    def __init__(self, date_reader, player=None):
        self.module_name = "config"
        if type(date_reader) == tuple:
            self.date_reader = date_reader[0]
            self.artist_counter = date_reader[1]
        else:
            self.date_reader = date_reader
        self.player = player
        self.dict = self.get_current()

    def __str__(self):
        return self.__repr__()

    def __repr__(self):
        return f"state is {self.dict}"

    @staticmethod
    def dict_diff(d1, d2):
        changes = {}
        for k in d2.keys():
            if d1[k] != d2[k]:
                changes[k] = (d1[k], d2[k])
        return changes

    def snap(self):
        previous = self.dict.copy()
        current = self.get_current()
        changes = self.dict_diff(previous, current)
        return (changes, previous, current)

    def get_changes(self):
        previous = self.dict  # do this first!
        current = self.get_current()
        return self.dict_diff(previous, current)

    @with_state_semaphore
    def set(self, new_state):
        for k in new_state.keys():
            config.__dict__[k] = new_state[k]  # NOTE This directly names config, which I'd like to be a variable.

    def get_current(self):
        module = globals().get(self.module_name, None)
        self.dict = {}
        if module:
            self.dict = {
                key: value for key, value in module.__dict__.items() if (not key.startswith("_")) and key.isupper()
            }
        self.date_reader._update()
        self.dict["DATE_READER"] = self.date_reader.date
        self.dict["VOLUME"] = 100.0
        self.dict["TRACK_NUM"] = -1
        self.dict["TAPE_ID"] = ""
        self.dict["TRACK_TITLE"] = ""
        self.dict["NEXT_TRACK_TITLE"] = ""
        self.dict["PLAY_STATE"] = self.dict.get("PLAY_STATE", 0)
        self.dict["VENUE"] = self.dict.get("VENUE", "")
        try:
            self.dict["VOLUME"] = self.player.get_prop("volume")
            self.dict["TRACK_NUM"] = self.player._get_property("playlist-pos")
            if not isinstance(self.player.tape, type(None)):  # needs to cover all archive types
                self.dict["TAPE_ID"] = self.player.tape.identifier
                self.dict["VENUE"] = self.player.tape.venue()
                if (self.dict["TRACK_NUM"]) < len(self.player.playlist):
                    self.dict["TRACK_TITLE"] = self.player.tape.tracks()[self.dict["TRACK_NUM"]].title
                if (self.dict["TRACK_NUM"] + 1) < len(self.player.playlist):
                    next_track = self.dict["TRACK_NUM"] + 1
                    self.dict["NEXT_TRACK_TITLE"] = self.player.tape.tracks()[next_track].title
                else:
                    self.dict["NEXT_TRACK_TITLE"] = ""
        except Exception:
            # logger.debug('Exception getting current state. Using some defaults')
            pass
        self.dict["TRACK_ID"] = f"{self.dict['TAPE_ID']}_track_{self.dict['TRACK_NUM']}"
        return self.dict


def controlLoop(item_list, callback, state=None, scr=None):
    last_active = datetime.datetime.now()
    last_timer = last_active
    refreshed = False
    while True:
        now = datetime.datetime.now()
        for item in item_list:
            if item.active:
                callback(item, state, scr)
                last_active = now
                refreshed = False
        time_since_active = (now - last_active).seconds
        if (time_since_active > QUIESCENT_TIME) and not refreshed:
            callback(scr, state, scr)
            refreshed = True
        if (now - last_timer).seconds > 5:
            last_timer = now
            callback(None, state, scr)
        sleep(0.01)
