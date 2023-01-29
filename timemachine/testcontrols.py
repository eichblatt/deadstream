from timemachine import controls
from timemachine import config
import datetime
from threading import Event
from typing import Callable
import board
import digitalio
from adafruit_rgb_display.st7735 import ST7735R
from adafruit_rgb_display import color565
from gpiozero import RotaryEncoder, Button
from tenacity import retry
from tenacity.stop import stop_after_delay

controls.logger.setLevel(50)
d1 = "1977-05-08"
d1 = datetime.date(*(int(s) for s in d1.split("-")))
scr = controls.screen()
scr.clear()
scr.show_staged_date(d1)
d2 = "1979-11-02"
d2 = datetime.date(*(int(s) for s in d2.split("-")))
scr.show_selected_date(d2)
scr.show_text("Venue", (0, 30))


@retry(stop=stop_after_delay(10))
def retry_call(callable: Callable, *args, **kwargs):
    """Retry a call."""
    return callable(*args, **kwargs)


def twist_knob(screen_event: Event, knob: RotaryEncoder, label, date_reader: controls.date_knob_reader):
    if knob.is_active:
        print(f"Knob {label} steps={knob.steps} value={knob.value}")
    else:
        if knob.steps < knob.threshold_steps[0]:
            knob.steps = knob.threshold_steps[0]
        if knob.steps > knob.threshold_steps[1]:
            knob.steps = knob.threshold_steps[1]
        print(f"Knob {label} is inactive")
    date_reader.update()
    screen_event.set()


y = retry_call(RotaryEncoder, config.year_pins[1], config.year_pins[0], max_steps=0, threshold_steps=(0, 30))
m = retry_call(RotaryEncoder, config.month_pins[1], config.month_pins[0], max_steps=0, threshold_steps=(1, 12))
d = retry_call(RotaryEncoder, config.day_pins[1], config.day_pins[0], max_steps=0, threshold_steps=(1, 31))
y.steps = 1979 - 1965
m.steps = 11
d.steps = 2
date_reader = controls.date_knob_reader(y, m, d, None)
y.when_rotated = lambda x: twist_knob(screen_event, y, "year", date_reader)
m.when_rotated = lambda x: twist_knob(screen_event, m, "month", date_reader)
d.when_rotated = lambda x: twist_knob(screen_event, d, "day", date_reader)
y_button = retry_call(Button, config.year_pins[2])
m_button = retry_call(Button, config.month_pins[2])
d_button = retry_call(Button, config.day_pins[2])
select = retry_call(Button, config.select_pin, hold_time=2, hold_repeat=True)
play_pause = retry_call(Button, config.play_pause_pin, hold_time=5)
ffwd = retry_call(Button, config.ffwd_pin, hold_time=1, hold_repeat=True)
rewind = retry_call(Button, config.rewind_pin, hold_repeat=True)
stop = retry_call(Button, config.stop_pin)

play_state = config.PLAY_STATE
# state = ctl.state(date_reader)
# cfg = state.get_current()

config.PLAY_STATE = 1  # Ready

play_pause.when_pressed = lambda x: print(f"pressing {x}")
play_pause.when_held = lambda x: print("nyi")

select.when_pressed = lambda x: print(f"pressing {x}")
select.when_held = lambda x: print(f"long pressing {x}")

ffwd.when_released = lambda x: print(f"releasing {x}")
ffwd.when_held = lambda x: print(f"long pressing {x}")

stop_event = Event()
screen_event = Event()


try:
    while not stop_event.wait(timeout=0.001):
        if screen_event.is_set():
            scr.show_staged_date(date_reader.date)
            screen_event.clear()
except KeyboardInterrupt:
    exit(0)


if __name__ == "__main__":
    print("Initializing inputs and outputs")
    stop_event = Event()
    screen_event = Event()

    print("Initializing display")
    display = ST7735R(
        board.SPI(),
        rotation=90,
        width=128,
        height=160,
        cs=digitalio.DigitalInOut(board.CE0),
        dc=digitalio.DigitalInOut(board.D24),
        rst=digitalio.DigitalInOut(board.D25),
        baudrate=40000000,
    )

    display.fill(color565(0, 0, 0))

    print("Twist and press the knobs and buttons.")
    print("Press a knob for longer than 3 seconds or Ctrl-C to exit.")

    try:
        while not stop_event.wait(timeout=0.001):
            if screen_event.is_set():
                display.fill(color565(0, 0, 0))
                screen_event.clear()
    except KeyboardInterrupt:
        exit(0)

if __name__ == "__main__" and False:
    main(parms)
