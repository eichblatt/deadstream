
# State variables
INIT = 0
READY = 1
PAUSED = 2
STOPPED = 3
PLAYING = 4
PLAY_STATES = ['Init','Ready','Paused','Stopped','Playing']
SELECT_DATE = False
PLAY_STATE = INIT
DATE = None

# Hardware pins

year_pins = (16,22,23)   # cl, dt, sw
month_pins = (12,5,6)
day_pins = (13,17,27)

