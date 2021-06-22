#!/usr/bin/python3
import datetime
import functools
import logging
from time import sleep
from threading import BoundedSemaphore

import adafruit_rgb_display.st7735 as st7735
import board
import digitalio
from adafruit_rgb_display import color565
from gpiozero import Button, LED, RotaryEncoder
from PIL import Image, ImageDraw, ImageFont

from . import config
import pkg_resources

logging.basicConfig(format='%(asctime)s.%(msecs)03d %(levelname)s: %(name)s %(message)s', level=logging.DEBUG, datefmt='%Y-%m-%d %H:%M:%S')
logger = logging.getLogger(__name__)
print(F"Name of controls logger is {__name__}")

screen_semaphore = BoundedSemaphore(1)
state_semaphore = BoundedSemaphore(1)


def with_state_semaphore(func):
    def inner(*args, **kwargs):
        try:
            acquired = state_semaphore.acquire(timeout=5)
            if not acquired:
                logger.warn("State semaphore not acquired after 5 seconds!")
                raise Exception('state semaphore not acquired')
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
                logger.warn("Screen semaphore not acquired after 5 seconds!")
                raise Exception('screen semaphore not acquired')
            func(*args, **kwargs)
        except BaseException:
            raise
        finally:
            screen_semaphore.release()
    return inner


class date_knob_reader:
    def __init__(self, y: RotaryEncoder, m: RotaryEncoder, d: RotaryEncoder, archive=None):
        self.date = None
        self.archive = archive
        self.y = y
        self.m = m
        self.d = d
        self.update()

    def __str__(self):
        return self.__repr__()

    def __repr__(self):
        avail = "Tape Available" if self.tape_available() else ""
        return F'Date Knob Says: {self.date.strftime("%Y-%m-%d")}. {avail}'

    def update(self):
        maxd = [31, 29, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]  # max days in a month.
        m_val = self.m.steps
        d_val = self.d.steps
        y_val = self.y.steps + 1965
        if d_val > maxd[m_val-1]:
            self.d.steps = maxd[m_val-1]
            d_val = self.d.steps
        try:
            self.date = datetime.date(y_val, m_val, d_val)
        except ValueError:
            self.d.steps = self.d.steps - 1
            d_val = d_val-1
            self.date = datetime.date(y_val, m_val, d_val)

    def set_date(self, date):
        new_month, new_day, new_year = (date.month, date.day, date.year)
        self.m.steps = new_month
        self.d.steps = new_day
        self.y.steps = new_year - 1965
        self.update()

    def fmtdate(self):
        if self.date is None:
            return None
        return self.date.strftime('%Y-%m-%d')

    def venue(self):
        if self.tape_available():
            t = self.archive.best_tape(self.fmtdate())
            return t.venue()
        return ""

    def tape_available(self):
        if self.archive is None:
            return False
        self.update()
        return self.fmtdate() in self.archive.dates

    def next_date(self):
        if self.archive is None:
            return None
        self.update()
        for d in self.archive.dates:
            if d > self.fmtdate():
                return datetime.datetime.strptime(d, '%Y-%m-%d').date()
        return self.date


class Bbox:
    def __init__(self, x0, y0, x1, y1):
        self.corners = (x0, y0, x1, y1)
        self.x0, self.y0, self.x1, self.y1 = self.corners

    def __str__(self):
        return self.__repr__()

    def __repr__(self):
        return F"Bbox: x0 {self.x0},y0 {self.y0},x1 {self.x1},y1 {self.y1}"

    def width(self): return self.x1 - self.x0
    def height(self): return self.y1 - self.y0
    def origin(self): return (self.x0, self.y0)
    def topright(self): return (self.x1, self.y1)
    def size(self): return (int(self.height()), int(self.width()))
    def center(self): return (int((self.x0+self.x1)/2), int((self.y0+self.y1)/2))
    def shift(self, d): return Bbox(self.x0-d.x0, self.y0-d.y0, self.x1-d.x1, self.y1-d.y1)


class screen:
    def __init__(self, upside_down=False, name='screen'):
        cs_pin = digitalio.DigitalInOut(board.CE0)
        dc_pin = digitalio.DigitalInOut(board.D24)
        reset_pin = digitalio.DigitalInOut(board.D25)
        #BAUDRATE= 2400000
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
        logger.debug(F" ---> disp {self.disp.width},{self.disp.height}")
        self.boldfont = ImageFont.truetype(pkg_resources.resource_filename("timemachine", "DejaVuSansMono-Bold.ttf"), 33)
        self.boldsmall = ImageFont.truetype(pkg_resources.resource_filename("timemachine", "DejaVuSansMono-Bold.ttf"), 22)
        self.font = ImageFont.truetype(pkg_resources.resource_filename("timemachine", "ariallgt.ttf"), 30)
        self.smallfont = ImageFont.truetype(pkg_resources.resource_filename("timemachine", "ariallgt.ttf"), 20)
        self.oldfont = ImageFont.truetype(pkg_resources.resource_filename("timemachine", "FreeMono.ttf"), 20)
        self.largefont = ImageFont.truetype(pkg_resources.resource_filename("timemachine", "FreeMono.ttf"), 30)
        self.hugefont = ImageFont.truetype(pkg_resources.resource_filename("timemachine", "FreeMono.ttf"), 40)

        self.image = Image.new("RGB", (width, height))
        self.draw = ImageDraw.Draw(self.image)       # draw using this object. Display image when complete.

        self.staged_date = None
        self.selected_date = None

        self.staged_date_bbox = Bbox(0, 0, 160, 31)
        #self.selected_date_bbox = Bbox(0,100,130,128)
        self.selected_date_bbox = Bbox(0, 100, 160, 128)
        self.venue_bbox = Bbox(0, 31, 160, 56)
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
        self.refresh(force)

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
        self.refresh(force=False)

    def show_text(self, text, loc=(0, 0), font=None, color=(255, 255, 255), stroke_width=0, force=False, clear=False):
        if font is None:
            font = self.font
        (text_width, text_height) = font.getsize(text)
        logger.debug(F' show_text {text}. text_size {text_height},{text_width}')
        if clear:
            self.clear()
        self.draw.text(loc, text, font=font, stroke_width=stroke_width, fill=color)
        self.refresh(force)

    def scroll_venue(self, color=(0, 255, 255), stroke_width=0, inc=15):
        """ This function can be called in a thread from the main.
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
                for i in range(int(excess/inc)+2):
                    #logger.debug(F"scrolling excess {excess}, inc: {inc}, i:{i}")
                    if self.venue_name != text:
                        break
                    # sleep(0.005)
                    self.clear_area(bbox)
                    self.show_text(text, bbox.shift(Bbox(inc*i, 0, 0, 0)).origin(), font=font, color=color, stroke_width=stroke_width)
                sleep(1)
                self.clear_area(bbox)

    def show_experience(self, text="Press Month to\nExit Experience", color=(255, 255, 255), force=False):
        self.clear_area(self.exp_bbox)
        self.show_text(text, self.exp_bbox.origin(), font=self.smallfont, color=color, stroke_width=1, force=force)

    def show_venue(self, text, color=(0, 255, 255), force=False):
        self.clear_area(self.venue_bbox)
        self.show_text(text, self.venue_bbox.origin(), font=self.boldsmall, color=color, force=force)

    def show_staged_date(self, date, color=(0, 255, 255), force=False):
        if date == self.staged_date:
            return
        self.clear_area(self.staged_date_bbox)
        month = str(date.month).rjust(2)
        day = str(date.day).rjust(2)
        year = str(divmod(date.year, 100)[1]).rjust(2)
        text = month + '-' + day + '-' + year
        logger.debug(F"staged date string {text}")
        self.show_text(text, self.staged_date_bbox.origin(), self.boldfont, color=color, force=force)
        self.staged_date = date

    def show_selected_date(self, date, color=(255, 255, 255), force=False):
        if date == self.selected_date:
            return
        self.clear_area(self.selected_date_bbox)
        month = str(date.month).rjust(2)
        day = str(date.day).rjust(2)
        year = str(date.year).rjust(4)
        text = month + '-' + day + '-' + year
        self.show_text(text, self.selected_date_bbox.origin(), self.boldsmall, color=color, force=force)
        self.selected_date = date

    def show_track(self, text, trackpos, color=(120, 0, 255), force=False):
        bbox = self.track1_bbox if trackpos == 0 else self.track2_bbox
        self.clear_area(bbox)
        self.draw.text(bbox.origin(), text, font=self.smallfont, fill=color, stroke_width=1)
        self.refresh(force)

    def show_playstate(self, staged_play=False, color=(0, 100, 255), sbd=None, force=False):
        logger.debug(F"showing playstate {config.PLAY_STATE}")
        bbox = self.playstate_bbox
        self.clear_area(bbox)
        size = bbox.size()
        if staged_play:
            self.draw.regular_polygon((bbox.center(), 10), 3, rotation=30, fill=color)
            self.draw.regular_polygon((bbox.center(), 8), 3, rotation=30, fill=(0, 0, 0))
            self.refresh(force)
            return
        if config.PLAY_STATE == config.PLAYING:
            self.draw.regular_polygon((bbox.center(), 10), 3, rotation=30, fill=color)
        elif config.PLAY_STATE == config.PAUSED:
            self.draw.line([(bbox.x0+10, bbox.y0+4), (bbox.x0+10, bbox.y0+20)], width=4, fill=color)
            self.draw.line([(bbox.x0+20, bbox.y0+4), (bbox.x0+20, bbox.y0+20)], width=4, fill=color)
        elif config.PLAY_STATE == config.STOPPED:
            self.draw.regular_polygon((bbox.center(), 10), 4, rotation=0, fill=color)
        elif config.PLAY_STATE in [config.INIT, config.READY, config.ENDED]:
            pass
        if sbd:
            self.show_soundboard(sbd)
        self.refresh(force)

    def show_soundboard(self, sbd, color=(255, 255, 255)):
        if not sbd:
            self.draw.regular_polygon((self.sbd_bbox.center(), 3), 4, rotation=45, fill=(0, 0, 0))
            return
        logger.debug("showing soundboard status")
        self.draw.regular_polygon((self.sbd_bbox.center(), 3), 4, rotation=45, fill=color)


class state:
    def __init__(self, date_reader, player=None):
        self.module_name = 'config'
        self.date_reader = date_reader
        self.player = player
        self.dict = self.get_current()

    def __str__(self):
        return self.__repr__()

    def __repr__(self):
        return F"state is {self.dict}"

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
        previous = self.dict   # do this first!
        current = self.get_current()
        return self.dict_diff(previous, current)

    @with_state_semaphore
    def set(self, new_state):
        for k in new_state.keys():
            config.__dict__[k] = new_state[k]   # NOTE This directly names config, which I'd like to be a variable.

    def get_current(self):
        module = globals().get(self.module_name, None)
        self.dict = {}
        if module:
            self.dict = {key: value for key, value in module.__dict__.items() if (not key.startswith('_')) and key.isupper()}
        self.date_reader.update()
        self.dict['DATE_READER'] = self.date_reader.date
        try:
            self.dict['TRACK_NUM'] = self.player._get_property('playlist-pos')
            self.dict['TAPE_ID'] = self.player.tape.identifier
            self.dict['TRACK_TITLE'] = self.player.tape.tracks()[self.dict['TRACK_NUM']].title
            if (self.dict['TRACK_NUM']+1) < len(self.player.playlist):
                next_track = self.dict['TRACK_NUM']+1
                self.dict['NEXT_TRACK_TITLE'] = self.player.tape.tracks()[next_track].title
            else:
                self.dict['NEXT_TRACK_TITLE'] = ''
        except BaseException:
            self.dict['TRACK_NUM'] = -1
            self.dict['TAPE_ID'] = ''
            self.dict['TRACK_TITLE'] = ''
            self.dict['NEXT_TRACK_TITLE'] = ''
        self.dict['TRACK_ID'] = self.dict['TAPE_ID'] + "_track_" + str(self.dict['TRACK_NUM'])
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
        if (time_since_active > config.optd['QUIESCENT_TIME']) and not refreshed:
            callback(scr, state, scr)
            refreshed = True
        if (now - last_timer).seconds > 5:
            last_timer = now
            callback(None, state, scr)
        sleep(0.01)
