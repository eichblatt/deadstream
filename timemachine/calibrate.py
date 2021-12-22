import datetime
import json
import logging
import optparse
import os
import re
import string
import subprocess
import sys
from threading import Event
from time import sleep

from gpiozero import RotaryEncoder, Button
from tenacity import retry
from tenacity.stop import stop_after_delay
from typing import Callable

from timemachine import config, controls


parser = optparse.OptionParser()
parser.add_option('--knob_sense_path',
                  dest='knob_sense_path',
                  type="string",
                  default=os.path.join(os.getenv('HOME'), ".knob_sense"),
                  help="path to file describing knob directions [default %default]")
parser.add_option('-d', '--debug',
                  dest='debug',
                  type="int",
                  default=0,
                  help="If > 0, don't run the main script on loading [default %default]")
parser.add_option('--options_path',
                  dest='options_path',
                  default=os.path.join(os.getenv('HOME'), '.timemachine_options.txt'),
                  help="path to options file [default %default]")
parser.add_option('--test',
                  dest='test',
                  action="store_true",
                  default=False,
                  help="Force reconnection (for testing) [default %default]")
parser.add_option('--sleep_time',
                  dest='sleep_time',
                  type="int",
                  default=10,
                  help="how long to sleep before checking network status [default %default]")
parser.add_option('-v', '--verbose',
                  dest='verbose',
                  action="store_true",
                  default=False,
                  help="Print more verbose information [default %default]")
parms, remainder = parser.parse_args()

logging.basicConfig(format='%(asctime)s.%(msecs)03d %(levelname)s: %(name)s %(message)s', level=logging.INFO, datefmt='%Y-%m-%d %H:%M:%S')
logger = logging.getLogger(__name__)
controlsLogger = logging.getLogger('timemachine.controls')
if parms.verbose:
    logger.setLevel(logging.DEBUG)
    controlsLogger.setLevel(logging.DEBUG)
else:
    logger.setLevel(logging.DEBUG)
    controlsLogger.setLevel(logging.INFO)

for k in parms.__dict__.keys():
    print(F"{k:20s} : {parms.__dict__[k]}")

button_event = Event()
rewind_event = Event()
done_event = Event()   # stop button
ffwd_event = Event()
play_pause_event = Event()
select_event = Event()
m_event = Event()
d_event = Event()
y_event = Event()
m_knob_event = Event()
d_knob_event = Event()
y_knob_event = Event()


@retry(stop=stop_after_delay(10))
def retry_call(callable: Callable, *args, **kwargs):
    """Retry a call."""
    return callable(*args, **kwargs)


class decade_counter():
    def __init__(self, tens: RotaryEncoder, ones: RotaryEncoder, bounds=(None, None)):
        self.bounds = bounds
        self.tens = tens
        self.ones = ones
        self.set_value(tens.steps, ones.steps)

    def set_value(self, tens_val, ones_val):
        self.value = tens_val*10 + ones_val
        if self.bounds[0] is not None:
            self.value = max(self.value, self.bounds[0])
        if self.bounds[1] is not None:
            self.value = min(self.value, self.bounds[1])
        self.tens.steps, self.ones.steps = divmod(self.value, 10)
        return self.value

    def get_value(self):
        return self.value


def decade_knob(knob: RotaryEncoder, label, counter: decade_counter):
    if knob.is_active:
        print(f"Knob {label} steps={knob.steps} value={knob.value}")
    else:
        if knob.steps < knob.threshold_steps[0]:
            if label == "year" and d.steps > d.threshold_steps[0]:
                knob.steps = knob.threshold_steps[1]
                d.steps = max(d.threshold_steps[0], d.steps - 1)
            else:
                knob.steps = knob.threshold_steps[0]
        if knob.steps > knob.threshold_steps[1]:
            if label == "year" and d.steps < d.threshold_steps[1]:
                knob.steps = knob.threshold_steps[0]
                d.steps = min(d.threshold_steps[1], d.steps + 1)
            else:
                knob.steps = knob.threshold_steps[1]
        print(f"Knob {label} is inactive")
    counter.set_value(d.steps, y.steps)
    if label == "month":
        m_knob_event.set()
    if label == "day":
        d_knob_event.set()
    if label == "year":
        y_knob_event.set()


def rewind_button(button):
    logger.debug("pressing or holding rewind")
    button_event.set()
    rewind_event.set()


def select_button(button):
    logger.debug("pressing select")
    select_event.set()


def stop_button(button):
    logger.debug("pressing stop")
    button_event.set()
    done_event.set()


def ffwd_button(button):
    logger.debug("pressing ffwd")
    ffwd_event.set()


def play_pause_button(button):
    logger.debug("pressing ffwd")
    play_pause_event.set()


def month_button(button):
    logger.debug("pressing or holding rewind")
    m_event.set()


def day_button(button):
    logger.debug("pressing or holding rewind")
    d_event.set()


def year_button(button):
    logger.debug("pressing or holding rewind")
    y_event.set()


max_choices = len(string.printable)
m = retry_call(RotaryEncoder, config.month_pins[1], config.month_pins[0], max_steps=0, threshold_steps=(0, 9))
d = retry_call(RotaryEncoder, config.day_pins[1], config.day_pins[0], max_steps=0, threshold_steps=(0, 1+divmod(max_choices-1, 10)[0]))
y = retry_call(RotaryEncoder, config.year_pins[1], config.year_pins[0], max_steps=0, threshold_steps=(0, 9))
counter = decade_counter(d, y, bounds=(0, 100))

m_button = retry_call(Button, config.month_pins[2])
d_button = retry_call(Button, config.day_pins[2], hold_time=0.3, hold_repeat=False)
y_button = retry_call(Button, config.year_pins[2], hold_time=0.5)

m.when_rotated = lambda x: decade_knob(m, "month", counter)
d.when_rotated = lambda x: decade_knob(d, "day", counter)
y.when_rotated = lambda x: decade_knob(y, "year", counter)

rewind = retry_call(Button, config.rewind_pin)
ffwd = retry_call(Button, config.ffwd_pin)
play_pause = retry_call(Button, config.play_pause_pin)
select = retry_call(Button, config.select_pin, hold_time=2, hold_repeat=True)
stop = retry_call(Button, config.stop_pin)

rewind.when_pressed = lambda x: rewind_button(x)
rewind.when_held = lambda x: rewind_button(x)
ffwd.when_pressed = lambda x: ffwd_button(x)
play_pause.when_pressed = lambda x: play_pause_button(x)
y_button.when_pressed = lambda x: year_button(x)
m_button.when_pressed = lambda x: month_button(x)
d_button.when_pressed = lambda x: day_button(x)
select.when_pressed = lambda x: select_button(x)
stop.when_pressed = lambda x: stop_button(x)

scr = controls.screen(upside_down=False)
scr.clear()


def get_knob_orientation(knob, label):
    m_knob_event.clear()
    d_knob_event.clear()
    y_knob_event.clear()
    knob.steps = 0
    before_value = knob.steps
    scr.show_text("Calibrating knobs", font=scr.smallfont, force=False, clear=True)
    scr.show_text(F"Rotate {label}\nclockwise", loc=(0, 40), font=scr.boldsmall, color=(0, 255, 255), force=True)
    if label == "month":
        m_knob_event.wait()
    elif label == "day":
        d_knob_event.wait()
    elif label == "year":
        y_knob_event.wait()
    after_value = knob.steps
    return after_value > before_value


def save_knob_sense(parms):
    knob_senses = [get_knob_orientation(knob, label) for knob, label in [(m, "month"), (d, "day"), (y, "year")]]
    knob_sense = 0
    for i in range(len(knob_senses)):
        knob_sense += 1 << i if knob_senses[i] else 0
    f = open(parms.knob_sense_path, 'w')
    f.write(str(knob_sense))
    f.close()
    scr.show_text("Knobs\nCalibrated", font=scr.boldsmall, color=(0, 255, 255), force=False, clear=True)
    scr.show_text(F"      {knob_sense}", font=scr.boldsmall, loc=(0, 60), force=True)


def test_buttons(event, label):
    event.clear()
    scr.show_text("Testing Buttons", font=scr.smallfont, force=False, clear=True)
    scr.show_text(F"Press {label}", loc=(0, 40), font=scr.boldsmall, color=(0, 255, 255), force=True)
    event.wait()


def default_options():
    d = {}
    d['COLLECTIONS'] = 'GratefulDead'
    d['SCROLL_VENUE'] = 'true'
    d['FAVORED_TAPER'] = 'miller'
    d['AUTO_UPDATE_ARCHIVE'] = 'false'
    d['DEFAULT_START_TIME'] = '15:00:00'
    d['TIMEZONE'] = 'America/New_York'
    return d


def configure_collections(parms):
    """ is this a GratefulDead or a Phish Time Machine? """
    collection = select_option("Collection\nTurn Year, Select", ['GratefulDead', 'Phish', 'GratefulDead,Phish', 'other'])
    if collection == 'other':
        collection = select_chars("Collection?\nSelect. Stop to end", character_set=string.printable[36:62])
    scr.show_text(f"Collection:\n{collection}", font=scr.smallfont, force=True, clear=True)
    #envs = get_envs()
    sleep(2)
    tmpd = default_options()
    try:
        tmpd = json.load(open(parms.options_path, 'r'))
    except Exception as e:
        logger.warning(F"Failed to read options from {parms.options_path}. Using defaults")
    tmpd['COLLECTIONS'] = collection
    try:
        with open(parms.options_path, 'w') as outfile:
            optd = json.dump(tmpd, outfile, indent=1)
    except Exception as e:
        logger.warning(F"Failed to write options to {parms.options_path}")


def test_sound(parms):
    """ test that sound works """
    try:
        cmd = f'mpv --really-quiet ~/test_sound.ogg &'
        os.system(cmd)
    except Exception as e:
        logger.warning("Failed to play sound file ~/test_sound.ogg")


def test_all_buttons(parms):
    """ test that every button on the board works """
    _ = [test_buttons(e, l) for e, l in
         [(done_event, "stop"), (rewind_event, "rewind"), (ffwd_event, "ffwd"), (select_event, "select"),
          (play_pause_event, "play/pause"), (m_event, "month"), (d_event, "day"), (y_event, "year")]]
    scr.show_text("Testing Buttons\nSucceeded!", font=scr.smallfont, force=True, clear=True)


def select_option(message, chooser):
    if type(chooser) == type(lambda: None): choices = chooser()
    else:
        choices = chooser
    scr.clear()
    counter.set_value(0, 0)
    selected = None
    screen_height = 5
    screen_width = 14
    update_now = scr.update_now
    scr.update_now = False
    done_event.clear()
    rewind_event.clear()
    select_event.clear()

    scr.show_text(message, loc=(0, 0), font=scr.smallfont, color=(0, 255, 255), force=True)
    (text_width, text_height) = scr.smallfont.getsize(message)

    text_height = text_height + 1
    y_origin = text_height*(1+message.count('\n'))
    selection_bbox = controls.Bbox(0, y_origin, 160, 128)

    while not select_event.is_set():
        if rewind_event.is_set():
            if type(chooser) == type(lambda: None): choices = chooser()
            else:
                choices = chooser
            rewind_event.clear()
        scr.clear_area(selection_bbox, force=False)
        x_loc = 0
        y_loc = y_origin
        step = divmod(counter.value, len(choices))[1]

        text = '\n'.join(choices[max(0, step-int(screen_height/2)):step])
        (text_width, text_height) = scr.smallfont.getsize(text)
        scr.show_text(text, loc=(x_loc, y_loc), font=scr.smallfont, force=False)
        y_loc = y_loc + text_height*(1+text.count('\n'))

        if len(choices[step]) > screen_width:
            text = '>' + '..' + choices[step][-13:]
        else:
            text = '>' + choices[step]
        (text_width, text_height) = scr.smallfont.getsize(text)
        scr.show_text(text, loc=(x_loc, y_loc), font=scr.smallfont, color=(0, 0, 255), force=False)
        y_loc = y_loc + text_height

        text = '\n'.join(choices[step+1:min(step+screen_height, len(choices))])
        (text_width, text_height) = scr.smallfont.getsize(text)
        scr.show_text(text, loc=(x_loc, y_loc), font=scr.smallfont, force=True)

        sleep(0.01)
    select_event.clear()
    selected = choices[step]
    # scr.show_text(F"So far: \n{selected}",loc=selected_bbox.origin(),color=(255,255,255),font=scr.smallfont,force=True)

    logger.info(F"word selected {selected}")
    scr.update_now = update_now
    return selected


def select_chars(message, message2="So Far", character_set=string.printable):
    scr.clear()
    selected = ''
    counter.set_value(0, 1)
    screen_width = 12
    update_now = scr.update_now
    scr.update_now = False
    done_event.clear()
    select_event.clear()

    scr.show_text(message, loc=(0, 0), font=scr.smallfont, color=(0, 255, 255), force=True)
    (text_width, text_height) = scr.smallfont.getsize(message)

    y_origin = text_height*(1+message.count('\n'))
    selection_bbox = controls.Bbox(0, y_origin, 160, y_origin+22)
    selected_bbox = controls.Bbox(0, y_origin+21, 160, 128)

    while not done_event.is_set():
        while not select_event.is_set() and not done_event.is_set():
            scr.clear_area(selection_bbox, force=False)
            # scr.draw.rectangle((0,0,scr.width,scr.height),outline=0,fill=(0,0,0))
            x_loc = 0
            y_loc = y_origin

            text = 'DEL'
            (text_width, text_height) = scr.oldfont.getsize(text)
            if counter.value == 0:  # we are deleting
                scr.show_text(text, loc=(x_loc, y_loc), font=scr.oldfont, color=(0, 0, 255), force=False)
                scr.show_text(character_set[:screen_width], loc=(x_loc + text_width, y_loc), font=scr.oldfont, force=True)
                continue
            scr.show_text(text, loc=(x_loc, y_loc), font=scr.oldfont, force=False)
            x_loc = x_loc + text_width

            # print the white before the red, if applicable
            text = character_set[max(0, -1+counter.value-int(screen_width/2)):-1+counter.value]
            for x in character_set[94:]:
                text = text.replace(x, u'\u25A1')
            (text_width, text_height) = scr.oldfont.getsize(text)
            scr.show_text(text, loc=(x_loc, y_loc), font=scr.oldfont, force=False)
            x_loc = x_loc + text_width

            # print the red character
            text = character_set[-1+min(counter.value, len(character_set))]
            if text == ' ':
                text = "SPC"
            elif text == '\t':
                text = "\\t"
            elif text == '\n':
                text = "\\n"
            elif text == '\r':
                text = "\\r"
            elif text == '\x0b':
                text = "\\v"
            elif text == '\x0c':
                text = "\\f"
            (text_width, text_height) = scr.oldfont.getsize(text)
            scr.show_text(text, loc=(x_loc, y_loc), font=scr.oldfont, color=(0, 0, 255), force=False)
            x_loc = x_loc + text_width

            # print the white after the red, if applicable
            text = character_set[counter.value:min(-1+counter.value+screen_width, len(character_set))]
            for x in character_set[94:]:
                text = text.replace(x, u'\u25A1')
            (text_width, text_height) = scr.oldfont.getsize(text)
            scr.show_text(text, loc=(x_loc, y_loc), font=scr.oldfont, force=True)
            x_loc = x_loc + text_width

            sleep(0.1)
        select_event.clear()
        if done_event.is_set():
            continue
        if counter.value == 0:
            selected = selected[:-1]
            scr.clear_area(selected_bbox, force=False)
        else:
            selected = selected + character_set[-1+counter.value]
        scr.clear_area(selected_bbox, force=False)
        scr.show_text(F"{message2}:\n{selected[-screen_width:]}", loc=selected_bbox.origin(), color=(255, 255, 255), font=scr.oldfont, force=True)

    logger.info(F"word selected {selected}")
    scr.update_now = update_now
    return selected


def exit_success(status=0, sleeptime=5):
    sleep(sleeptime)
    scr.clear()
    sys.exit(status)


def check_factory_build():
    home = os.getenv('HOME')
    envs = get_envs()
    if '.factory_env' not in envs:   # create one
        logger.info("creating factory build")
        srcdir = os.path.join(home, envs[0])
        destdir = os.path.join(home, '.factory_env')
        cmd = f'cp -r {srcdir} {destdir}'
        os.system(cmd)
    else:
        logger.info("factory build present")
    return


def get_envs():
    home = os.getenv('HOME')
    current_env = os.path.basename(os.readlink(os.path.join(home, 'timemachine')))
    envs = [x for x in os.listdir(home) if os.path.isdir(os.path.join(home, x)) and (x.startswith('env_') or x == '.factory_env')]
    envs = sorted(envs, reverse=True)
    envs.insert(0, envs.pop(envs.index(current_env)))    # put current_env first in the list.
    return envs


def change_environment():
    home = os.getenv('HOME')
    envs = get_envs()
    new_env = select_option("Select an environment to use", envs)
    if new_env == envs[0]:
        return
    if new_env == '.factory_env':
        factory_dir = os.path.join(home, new_env)
        # new_factory = f'env_{datetime.datetime.now().strftime("%Y%m%d.%H%M%S")}'
        new_factory_tmp = 'env_recent_copy_tmp'    # Create a tmp dir, in case reboot occurs during the copy.
        new_factory = 'env_recent_copy'    # by using a static name I avoid cleaning up old directories.
        new_dir_tmp = os.path.join(home, new_factory_tmp)
        new_dir = os.path.join(home, new_factory)
        scr.show_text("Resetting Factory\nenvironment", font=scr.smallfont, force=True, clear=True)
        os.system(f'rm -rf {new_dir_tmp}')
        cmd = f'cp -r {factory_dir} {new_dir_tmp}'
        fail = os.system(cmd)
        if fail != 0:
            scr.show_text("Failed to\nReset Factory\nenvironment", font=scr.smallfont, force=True, clear=True)
            return
        cmd = f'rm -rf {new_dir}'
        os.system(cmd)
        cmd = f'mv {new_dir_tmp} {new_dir}'
        os.system(cmd)
    else:
        new_dir = os.path.join(home, new_env)
    if os.path.isdir(new_dir):
        make_link_cmd = f"ln -sfn {new_dir} {os.path.join(home,'timemachine')}"
        fail = os.system(make_link_cmd)
        if fail == 0:
            cmd = "sudo reboot"
            os.system(cmd)
            sys.exit(-1)
    scr.show_text("Failed to\nReset Factory\nenvironment", font=scr.smallfont, force=True, clear=True)
    return


def welcome_alternatives():
    scr.show_text("\n Welcome", color=(0, 0, 255), force=True, clear=True)
    check_factory_build()
    button = button_event.wait(0.2*parms.sleep_time)
    button_event.clear()
    if rewind_event.is_set():
        rewind_event.clear()
        # remove wpa_supplicant.conf file
        return True
    if ffwd_event.is_set():
        scr.show_text("recalibrating ", font=scr.font, force=True, clear=True)
        return True
    if done_event.is_set():
        change_environment()
        done_event.clear()
    return False


def main():
    try:
        scr.show_text("Booting\nUp ...", font=scr.font, force=True, clear=True)
        cmd = "sudo rfkill unblock wifi"
        os.system(cmd)
        cmd = "sudo ifconfig wlan0 up"
        os.system(cmd)
        reconnect = welcome_alternatives()

        if reconnect or (parms.test) or not os.path.exists(parms.knob_sense_path):
            try:
                test_sound(parms)
                test_all_buttons(parms)
                configure_collections(parms)
                save_knob_sense(parms)

                cmd = f'killall mpv'
                os.system(cmd)
            except Exception:
                logger.info("Failed to save knob sense...continuing")
    except Exception:
        sys.exit(-1)
    finally:
        scr.clear()

    exit_success(sleeptime=0)


if __name__ == "__main__" and parms.debug == 0:
    main()
