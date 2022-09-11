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
import time


#from timemachine.mpv import MPV
from mpv import MPV
from tenacity import retry
from tenacity.stop import stop_after_delay, stop_after_attempt
from tenacity.wait import wait_random
from tenacity.retry import retry_if_result
from typing import Callable, Optional

logging.basicConfig(format='%(asctime)s.%(msecs)03d %(levelname)s: %(name)s %(message)s', level=logging.INFO, datefmt='%Y-%m-%d %H:%M:%S')
logger = logging.getLogger(__name__)
ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
BIN_DIR = os.path.join(os.path.dirname(ROOT_DIR), 'bin')


@retry(stop=stop_after_delay(30))
def retry_call(callable: Callable, *args, **kwargs):
    """Retry a call."""
    return callable(*args, **kwargs)


def return_last_value(retry_state):
    """ return the result of the last call made in a tenacity retry """
    return retry_state.outcome.result()


@retry(stop=stop_after_attempt(7),
       wait=wait_random(min=1, max=2),
       retry=retry_if_result(lambda x: not x),
       retry_error_callback=return_last_value)
def retry_until_true(callable: Callable, *args, **kwargs):
    return callable(*args, **kwargs)


def memoize(f):
    memo = {}

    def helper(x):
        if x not in memo:
            memo[x] = f(x)
        return memo[x]
    return helper


# @memoize
def to_date(datestring): return datetime.datetime.fromisoformat(datestring)


def to_year(datestring):
    if type(datestring) == list:      # handle one bad case on 2009.01.10
        datestring = datestring[0]
    return to_date(datestring[:10]).year


def to_decade(datestring):
    if type(datestring) == list:      # handle one bad case on 2009.01.10
        datestring = datestring[0]
    return 10 * divmod(to_date(datestring[:10]).year, 10)[0]


class GDPlayer(MPV):
    """ A media player to play a GDTape """

    def __init__(self, tape=None):
        super().__init__()
        # self._set_property('prefetch-playlist','yes')
        # self._set_property('cache-dir','/home/steve/cache')
        # self._set_property('cache-on-disk','yes')
        self._set_property('audio-buffer', 10.0)  # This allows to play directly from the html without a gap!
        self._set_property('cache', 'yes')
        self.tape = None
        self.download_when_possible = False

        self.set_audio_device()

        if tape is not None:
            self.insert_tape(tape)

    def __str__(self):
        return self.__repr__()

    def __repr__(self):
        retstr = str(self.playlist)
        return retstr

    def set_audio_device(self, audio_device=None):
        # check to see if pulse audio daemon is running system-wide before setting audio device
        if audio_device == 'pulse' and os.path.exists('/etc/systemd/system/pulseaudio.service'):
            self.default_audio_device = 'pulse'
        else:
            self.default_audio_device = 'auto'
        self._set_property('audio-device', self.default_audio_device)

        if self.default_audio_device == 'pulse':
            self.restart_pulse_audio()
        else:
            self.stop_pulse_audio()

    def insert_tape(self, tape):
        self.tape = tape
        self.create_playlist()

    def eject_tape(self):
        self.stop()
        self.tape = None
        self.playlist_clear()

    def extract_urls(self, tape):  # NOTE this should also give a list of backup URL's.
        tape.get_metadata()
        urls = []
        playable_formats = tape._playable_formats
        preferred_format = playable_formats[0]
        for track_files in [x.files for x in tape.tracks()]:
            best_track = None
            candidates = []
            for f in track_files:
                if f['format'] == preferred_format:
                    best_track = f['url']
                elif f['format'] in playable_formats:
                    candidates.append(f['url'])
            if best_track is None and len(candidates) > 0:
                best_track = candidates[0]
            urls.append(best_track)
        return urls

    def create_playlist(self):
        self.playlist_clear()
        urls = self.extract_urls(self.tape)
        if len(urls) == 0:
            self.tape._remove_from_archive = True
        self.command('loadfile', urls[0])
        if len(urls) > 1:
            _ = [self.command('loadfile', x, 'append') for x in urls[1:]]
        self.playlist_pos = 0
        self.pause()
        logger.info(F"Playlist {self.playlist}")
        return

    def stop_pulse_audio(self):
        cmd = "sudo service pulseaudio stop"
        os.system(cmd)
        return

    def restart_pulse_audio(self):
        logger.info("Restarting the pulseaudio service")
        cmd = "sudo service pulseaudio restart"
        os.system(cmd)
        return

    def reset_audio_device(self, kwarg=None):
        logger.info("in reset_audio_device")
        if self.get_prop('audio-device') == 'null':
            logger.info(F"changing audio-device to {self.default_audio_device}")
            audio_device = self.default_audio_device
            if audio_device == 'pulse':
                self.restart_pulse_audio()
            else:
                self.stop_pulse_audio()
            self._set_property('audio-device', audio_device)
            self.wait_for_property('audio-device', lambda v: v == audio_device)
            if self.get_prop('current-ao') is None:
                logger.warning("Current-ao is None")
                # self.stop()
                return False
            # self.pause()
            # self._set_property('pause', False)
            # self.wait_until_playing()
            # self.pause()
        return True

    def play(self, wait=True):
        if not retry_until_true(self.reset_audio_device, None):
            logger.warning("Failed to reset audio device when playing")
        logger.debug("playing")
        self._set_property('pause', False)
        if wait:
            self.wait_until_playing()   # blocking occasionally here.

    def pause(self, wait=True):
        logger.debug("pausing")
        self._set_property('pause', True)
        if wait:
            self.wait_until_paused()

    def stop(self):
        self.playlist_pos = 0
        self.pause()

    def next(self, blocking=False):
        pos = self.get_prop('playlist-pos')
        if pos is None or pos + 1 == len(self.playlist):
            return
        self.command('playlist-next')
        if blocking:
            self.wait_for_event('file-loaded')

    def prev(self):
        pos = self.get_prop('playlist-pos')
        if pos is None or pos == 0:
            return
        self.command('playlist-prev')

    def time_remaining(self):
        icounter = 0
        self.wait_for_property('time-remaining', lambda v: v is not None)
        time_remaining = self.get_prop('time-remaining')
        while time_remaining is None and icounter < 20:
            logger.info(F'time-remaining is {time_remaining},icounter:{icounter},playlist:{self.playlist}')
            time.sleep(1)
            icounter = icounter + 1
            time_remaining = self.get_prop('time-remaining')
            self.status()
        logger.debug(F'time-remaining is {time_remaining}')
        return time_remaining

    def seek_in_tape_to(self, destination, ticking=True, threshold=1):
        """ Seek to a time position in a tape. Since this can take some
            time, the ticking option allows to take into account the time
            required to seek (the slippage).
            destination -- seconds from current tape location (from beginning?)
        """
        logger.debug(F'seek_in_tape_to {destination}')

        start_tick = datetime.datetime.now()
        slippage = 0
        skipped = 0
        dest_orig = destination
        time_remaining = self.time_remaining()
        playlist_pos = self.get_prop('playlist-pos')
        logger.debug(F'seek_in_tape_to dest:{destination},time-remainig:{time_remaining},playlist-pos:{playlist_pos}')
        while (destination > time_remaining) and self.get_prop('playlist-pos') + 1 < len(self.playlist):
            duration = self.get_prop('duration')
            logger.debug(F'seek_in_tape_to dest:{destination},time-remainig:{time_remaining},playlist-pos:{playlist_pos}, duration: {duration}, slippage {slippage}')
            self.next(blocking=True)
            skipped = skipped + time_remaining
            destination = dest_orig - skipped
            time_remaining = self.time_remaining()
            if ticking:
                now_tick = datetime.datetime.now()
                slippage = (now_tick - start_tick).seconds
                destination = destination + slippage
            playlist_pos = self.get_prop('playlist-pos')
        self.seek(destination)
        self.status()
        self.play()
        return

    def seek_to(self, track_no, destination=0.0, threshold=1):
        logger.debug(F'seek_to {track_no},{destination}')
        try:
            if track_no < 0 or track_no > len(self.playlist):
                raise Exception(F'seek_to track {track_no} out of bounds')
            paused = self.get_prop('pause')
            current_track = self.get_prop('playlist-pos')
            self.status()
            if current_track != track_no:
                self._set_property('playlist-pos', track_no)
                # self.wait_for_event('file-loaded')   # NOTE: this could wait forever!
                time.sleep(5)
            duration = self.get_prop('duration')
            if destination < 0:
                destination = duration + destination
            if (destination > duration) or (destination < 0):
                raise Exception(F'seek_to destination {destination} out of bounds (0,{duration})')

            self.seek(destination, reference='absolute')
            if not paused:
                self.play()
            time_pos = self.get_prop('time-pos')
            if abs(time_pos - destination) > threshold:
                raise Exception(F'Not close enough: time_pos {time_pos} - destination ({time_pos - destination})>{threshold}')
        except Exception as e:
            logger.warning(e)
        finally:
            pass

    def fseek(self, jumpsize=30, sleeptime=2):
        try:
            logger.debug(F'seeking {jumpsize}')

            current_track = self.get_prop('playlist-pos')
            time_pos = self.get_prop('time-pos')
            if time_pos is None:
                time_pos = 0
            time_pos = max(0, time_pos)
            duration = self.get_prop('duration')
            # self.wait_for_property('duration', lambda v: v is not None)

            destination = time_pos + jumpsize

            logger.debug(F'destination {destination} time_pos {time_pos} duration {duration}')

            if destination < 0:
                if abs(destination) < abs(sleeptime * 5):
                    destination = destination - sleeptime * 5
                self.seek_to(current_track - 1, destination)
            if destination > duration:
                self.seek_to(current_track + 1, destination - duration)
            else:
                self.seek_to(current_track, destination)
        except Exception as e:
            logger.warning(F'exception in seeking {e}')
        finally:
            time.sleep(sleeptime)

    def get_prop(self, property_name):
        return retry_call.retry_with(stop=stop_after_attempt(20))(self._get_property, property_name)

    def status(self):
        if self.playlist_pos is None:
            logger.info("Playlist not started")
            return None
        playlist_pos = self.get_prop('playlist-pos')
        paused = self.get_prop('pause')
        logger.info(F"Playlist at track {playlist_pos}, Paused {paused}")
        if self.raw.time_pos is None:
            logger.info("Track not started")
            return None
        duration = self.get_prop('duration')
        logger.info(F"duration: {duration}. time: {datetime.timedelta(seconds=int(self.raw.time_pos))}, time remaining: {datetime.timedelta(seconds=int(self.raw.time_remaining))}")
        return int(self.raw.time_remaining)

    def close(self): self.terminate()
