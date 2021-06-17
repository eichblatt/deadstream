from threading import Event

import tempfile
import unittest
from gpiozero import Button, RotaryEncoder
from tenacity import retry
from tenacity.stop import stop_after_delay
from typing import Callable

from timemachine import config, controls, GD

stop_event = Event()
knob_event = Event()


@retry(stop=stop_after_delay(10))
def retry_call(callable: Callable, *args, **kwargs):
    """Retry a call."""
    return callable(*args, **kwargs)


def stop_button(button):
    print("Stop button pressed")
    stop_event.set()


def twist_knob(knob: RotaryEncoder, label):
    print(f"Knob {label} steps={knob.steps} value={knob.value}")
    knob_event.set()


player = GD.GDPlayer()
y = retry_call(RotaryEncoder, config.year_pins[1], config.year_pins[0], max_steps=64, wrap=True)
m = retry_call(RotaryEncoder, config.month_pins[1], config.month_pins[0], max_steps=64, wrap=True)
d = retry_call(RotaryEncoder, config.day_pins[1], config.day_pins[0], max_steps=64, wrap=True)
y.when_rotated = lambda x: twist_knob(y, "year")
m.when_rotated = lambda x: twist_knob(m, "month")
d.when_rotated = lambda x: twist_knob(d, "day")
stop = retry_call(Button, config.stop_pin)
stop.when_pressed = lambda button: stop_button(button)

scr = controls.screen()
scr.clear()


class TestGD(unittest.TestCase):

    def test_create_set(self):
        set = GD.GDSet()
        self.assertGreater(len(set.set_data), 0)

    """
    def test_create_async_archive(self):
        with tempfile.TemporaryDirectory() as directory:
            GD.GDArchive(directory, sync=False)
    """

    def _test_tape_downloader(self, downloader):
        tapes = downloader.get_tapes([1970])
        frac_id = len([x for x in tapes if "identifier" in x]) / len(tapes)
        self.assertGreaterEqual(len(tapes), 200, msg="1970 has many tapes")
        self.assertEqual(frac_id, 1.0, msg="All tapes have an identifier")

    def test_async_tape_downloader(self):
        downloader = GD.AsyncTapeDownloader()
        self._test_tape_downloader(downloader)


class TestControls(unittest.TestCase):

    def test_knob(self):
        scr.clear()
        scr.show_text("Testing Screen\nTurn any knob", color=(0, 255, 255), force=True)
        passed_test = False
        if knob_event.wait(10):
            knob_event.clear()
            passed_test = True
        scr.clear()
        self.assertTrue(passed_test, msg="A knob was turned")

    def test_stop_button(self):
        scr.clear()
        scr.show_text("Press Stop\nButton", color=(0, 255, 255), force=True)
        passed_test = False
        if stop_event.wait(10):
            stop_event.clear()
            passed_test = True
        scr.clear()
        self.assertTrue(passed_test, msg="Stop button pressed")


if __name__ == '__main__':
    unittest.main()
