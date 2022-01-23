import json
import logging
import optparse
import os
import string
import subprocess
import sys
from time import sleep

from tenacity import retry
from tenacity.stop import stop_after_delay
from typing import Callable

from timemachine import controls


parser = optparse.OptionParser()
parser.add_option('--wpa_path',
                  dest='wpa_path',
                  type="string",
                  default='/etc/wpa_supplicant/wpa_supplicant.conf',
                  help="path to wpa_supplicant file [default %default]")
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

knob_sense_path = os.path.join(os.getenv('HOME'), ".knob_sense")

CALIBRATED = os.path.exists(knob_sense_path)

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


@retry(stop=stop_after_delay(10))
def retry_call(callable: Callable, *args, **kwargs):
    """Retry a call."""
    return callable(*args, **kwargs)


max_choices = len(string.printable)

TMB = controls.Time_Machine_Board(mdy_bounds=[(0, 9), (0, 1+divmod(max_choices-1, 10)[0]), (0, 9)])

TMB.rewind.when_pressed = lambda x: TMB.rewind_button(x)
TMB.rewind.when_held = lambda x: TMB.rewind_button(x)
TMB.ffwd.when_pressed = lambda x: TMB.ffwd_button(x)
TMB.play_pause.when_pressed = lambda x: TMB.play_pause_button(x)
TMB.y_button.when_pressed = lambda x: TMB.year_button(x)
TMB.m_button.when_pressed = lambda x: TMB.month_button(x)
TMB.d_button.when_pressed = lambda x: TMB.day_button(x)
TMB.select.when_pressed = lambda x: TMB.select_button(x)
TMB.stop.when_pressed = lambda x: TMB.stop_button(x)

counter = controls.decade_counter(TMB.d, TMB.y, bounds=(0, 100))
TMB.m.when_rotated = lambda x: TMB.decade_knob(TMB.m, "month", counter)
TMB.d.when_rotated = lambda x: TMB.decade_knob(TMB.d, "day", counter)
TMB.y.when_rotated = lambda x: TMB.decade_knob(TMB.y, "year", counter)


def get_knob_orientation(knob, label):
    TMB.m_knob_event.clear()
    TMB.d_knob_event.clear()
    TMB.y_knob_event.clear()
    bounds = knob.threshold_steps
    initial_value = knob.steps = int((bounds[0]+bounds[1])/2)
    TMB.scr.show_text("Calibrating knobs", font=TMB.scr.smallfont, force=False, clear=True)
    TMB.scr.show_text(F"Rotate {label}\nclockwise", loc=(0, 40), font=TMB.scr.boldsmall, color=(0, 255, 255), force=True)
    if label == "month":
        TMB.m_knob_event.wait()
    elif label == "day":
        TMB.d_knob_event.wait()
    elif label == "year":
        TMB.y_knob_event.wait()
    TMB.m_knob_event.clear()
    TMB.d_knob_event.clear()
    TMB.y_knob_event.clear()
    logger.info(f'AFTER: knob {label} is {knob.steps}, initial_value {initial_value}. {knob.steps > initial_value}')
    return knob.steps > initial_value


def save_knob_sense(save_calibration=True):
    knob_senses = [get_knob_orientation(knob, label) for knob, label in [(TMB.m, "month"), (TMB.d, "day"), (TMB.y, "year")]]
    knob_sense_orig = TMB.get_knob_sense()
    knob_sense = 0
    for i in range(len(knob_senses)):
        knob_sense += 1 << i if knob_senses[i] else 0
    new_knob_sense = 7 & ~(knob_sense ^ knob_sense_orig)
    TMB.scr.show_text("Knobs\nCalibrated", font=TMB.scr.boldsmall, color=(0, 255, 255), force=False, clear=True)
    TMB.scr.show_text(F"      {new_knob_sense}", font=TMB.scr.boldsmall, loc=(0, 60), force=True)
    if save_calibration:
        f = open(knob_sense_path, 'w')
        f.write(str(new_knob_sense))
        f.close()
    else:
        TMB.scr.show_text(F"{new_knob_sense}", font=TMB.scr.boldsmall, loc=(0, 60), force=True)
        sleep(1)


def test_buttons(event, label):
    event.clear()
    TMB.scr.show_text("Testing Buttons", font=TMB.scr.smallfont, force=False, clear=True)
    TMB.scr.show_text(F"Press {label}", loc=(0, 40), font=TMB.scr.boldsmall, color=(0, 255, 255), force=True)
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
    collection = controls.select_option(TMB, counter, "Collection\nTurn Year, Select", ['GratefulDead', 'Phish', 'GratefulDead,Phish', 'no change', 'other'])
    if collection == 'other':
        collection = controls.select_chars(TMB, counter, "Collection?\nSelect. Stop to end", character_set=string.printable[36:62])
    TMB.scr.show_text(f"Collection:\n{collection}", font=TMB.scr.smallfont, force=True, clear=True)
    if collection == '' or collection == 'no change':
        return collection
    sleep(2)
    tmpd = default_options()
    try:
        tmpd = json.load(open(parms.options_path, 'r'))
    except Exception as e:
        logger.warning(F"Failed to read options from {parms.options_path}. Using defaults")
    tmpd['COLLECTIONS'] = collection
    try:
        with open(parms.options_path, 'w') as outfile:
            json.dump(tmpd, outfile, indent=1)
    except Exception as e:
        logger.warning(F"Failed to write options to {parms.options_path}")

    return collection


def test_sound(parms):
    """ test that sound works """
    try:
        cmd = 'mpv --really-quiet ~/test_sound.ogg &'
        os.system(cmd)
    except Exception as e:
        logger.warning("Failed to play sound file ~/test_sound.ogg")


def test_all_buttons(parms):
    """ test that every button on the board works """
    _ = [test_buttons(e, l) for e, l in
         [(TMB.stop_event, "stop"), (TMB.rewind_event, "rewind"), (TMB.ffwd_event, "ffwd"), (TMB.select_event, "select"),
          (TMB.play_pause_event, "play/pause"), (TMB.m_event, "month"), (TMB.d_event, "day"), (TMB.y_event, "year")]]
    TMB.scr.show_text("Testing Buttons\nSucceeded!", font=TMB.scr.smallfont, force=True, clear=True)


def exit_success(status=0, sleeptime=0):
    TMB.scr.show_text("Please\n Stand By\n     . . . ", color=(0, 255, 255), force=True, clear=True)
    sleep(sleeptime)
    if status == 0:
        os.system(f'kill {os.getpid()}')  # Killing the process like this will leave the message on the screen.
    else:
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
    new_env = controls.select_option(TMB, counter, "Select an environment to use", envs)
    if new_env == envs[0]:
        return
    if new_env == '.factory_env':
        factory_dir = os.path.join(home, new_env)
        # new_factory = f'env_{datetime.datetime.now().strftime("%Y%m%d.%H%M%S")}'
        new_factory_tmp = 'env_recent_copy_tmp'    # Create a tmp dir, in case reboot occurs during the copy.
        new_factory = 'env_recent_copy'    # by using a static name I avoid cleaning up old directories.
        new_dir_tmp = os.path.join(home, new_factory_tmp)
        new_dir = os.path.join(home, new_factory)
        TMB.scr.show_text("Resetting Factory\nenvironment", font=TMB.scr.smallfont, force=True, clear=True)
        os.system(f'rm -rf {new_dir_tmp}')
        cmd = f'cp -r {factory_dir} {new_dir_tmp}'
        fail = os.system(cmd)
        if fail != 0:
            TMB.scr.show_text("Failed to\nReset Factory\nenvironment", font=TMB.scr.smallfont, force=True, clear=True)
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
    TMB.scr.show_text("Failed to\nReset Factory\nenvironment", font=TMB.scr.smallfont, force=True, clear=True)
    return


def welcome_alternatives():
    TMB.scr.show_text("  Welcome", color=(0, 0, 255), force=True, clear=True)
    if CALIBRATED:
        TMB.scr.show_text("to recalibrate\n press play/pause", loc=(0, 30), font=TMB.scr.smallfont, force=False)
        TMB.scr.show_text("  spertilo.net/faq", loc=(0, 100), font=TMB.scr.smallfont, color=(0, 200, 200), force=True)
    TMB.scr.show_text(f"{controls.get_version()}", loc=(10, 75), font=TMB.scr.smallfont, color=(255, 100, 0), stroke_width=1, force=True)
    check_factory_build()
    TMB.button_event.wait(parms.sleep_time)
    if TMB.rewind_event.is_set():
        TMB.clear_events()
        # remove wpa_supplicant.conf file
        remove_wpa = controls.select_option(TMB, counter, "Forget WiFi?", ["No", "Yes"])
        if remove_wpa == "Yes":
            cmd = F"sudo rm {parms.wpa_path}"
            _ = subprocess.check_output(cmd, shell=True)
        return True
    if TMB.stop_event.is_set():
        TMB.clear_events()
        change_environment()
        return True
    if TMB.button_event.is_set():
        TMB.clear_events()
        TMB.scr.show_text("recalibrating ", font=TMB.scr.font, force=True, clear=True)
        return True
    return False


def unblock_wifi():
    cmd = "sudo rfkill unblock wifi"
    os.system(cmd)
    cmd = "sudo ifconfig wlan0 up"
    os.system(cmd)


def main():
    try:
        recalibrate = welcome_alternatives()
        unblock_wifi()

        if recalibrate or parms.test or not os.path.exists(knob_sense_path):
            try:
                test_sound(parms)
                test_all_buttons(parms)
                collection = configure_collections(parms)
                save_knob_sense(collection != '')

                os.system('killall mpv')
            except Exception:
                logger.info("Failed to save knob sense...continuing")
    except Exception:
        sys.exit(-1)

    exit_success()


if __name__ == "__main__" and parms.debug == 0:
    main()
