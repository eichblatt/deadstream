
# State variables
READY = 0
PAUSED = 1
STOPPED = 2
PLAYING = 3
PLAY_STATES = ['Ready','Paused','Stopped','Playing']
SELECT_DATE = False
PLAY_STATE = READY
DATE = None

# Hardware pins

year_pins = (16,22,23)   # cl, dt, sw
month_pins = (12,5,6)
day_pins = (13,17,27)

