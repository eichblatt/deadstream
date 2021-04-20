import datetime

# State variables
INIT = 0
READY = 1
PAUSED = 2
STOPPED = 3
PLAYING = 4
PLAY_STATE = INIT
#PLAY_STATES = ['Init','Ready','Paused','Stopped','Playing']
SELECT_STAGED_DATE = False
NEXT_TAPE = False
DATE = None
STAGED_DATE = None

ON_TOUR = False
EXPERIENCE = False
TIH = False

_today = datetime.date.today()
TIH_YEAR = None
TIH_MONTH = _today.month
TIH_DAY = _today.day

NEXT_DATE = False

FFWD = False
FSEEK = False
REWIND = False
RSEEK = False

# Hardware pins

year_pins = (16,22,23)   # cl, dt, sw
month_pins = (12,5,6)
day_pins = (13,17,27)

select_pin = 4   # pin 4 ok w/ Sound card
play_pause_pin = 20 # pin 18 interferes with sound card
rewind_pin = 3  # from the I2C bus (may need to connect to ground)
stop_pin = 2   # from the I2C bus (may need to connect to ground) 
ffwd_pin = 26    # pin 26 ok with sound card.

# Options

FADE_AWAY = "NOT"  # or "WEST_LA"
QUIESCENT_TIME = 3000 # -- cycles to wait until reverting staged date
