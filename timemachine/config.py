import subprocess


def get_board_version():
    cmd = "$HOME/deadstream/bin/board_version.sh"
    raw = subprocess.check_output(cmd, shell=True)
    raw = raw.decode()
    if raw == 'version 2\n':
        return 2
    else:
        return 1


# State variables
INIT = 0
READY = 1
PAUSED = 2
STOPPED = 3
PLAYING = 4
ENDED = 5
PLAY_STATE = INIT
#PLAY_STATES = ['Init','Ready','Paused','Stopped','Playing']
SELECT_STAGED_DATE = False
DATE = None
VENUE = None
STAGED_DATE = None
PAUSED_AT = None

ON_TOUR = False
EXPERIENCE = False
TOUR_YEAR = None
TOUR_STATE = 0

# Hardware pins

if get_board_version() == 2:
    rewind_pin = 21
    year_pins = (16, 22, 23)   # cl, dt, sw
    month_pins = (12, 5, 6)
    day_pins = (13, 17, 27)
else:
    rewind_pin = 3
    year_pins = (22, 16, 23)   # cl, dt, sw
    month_pins = (5, 12, 6)
    day_pins = (17, 13, 27)
screen_led_pin = 19

select_pin = 4   # pin 4 ok w/ Sound card
play_pause_pin = 20  # pin 18 interferes with sound card
stop_pin = 2   # from the I2C bus (may need to connect to ground)
ffwd_pin = 26    # pin 26 ok with sound card.
