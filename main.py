#!/usr/bin/python3
import optparse
from timemachine import GD
from timemachine import controls
from timemachine import config
from time import sleep
import logging
from threading import Event
from typing import Callable
import os
import datetime
from gpiozero import RotaryEncoder, Button
from tenacity import retry
from tenacity.stop import stop_after_delay
import pkg_resources

parser = optparse.OptionParser()
parser.add_option('--box',dest='box',type="string",default='v1',help="v0 box has screen at 270. [default %default]")
parser.add_option('--dbpath',dest='dbpath',type="string",default=os.path.join(os.getenv('HOME'),'projects/deadstream/metadata'),help="path to database [default %default]")
parser.add_option('-d','--debug',dest='debug',type="int",default=1,help="If > 0, don't run the main script on loading [default %default]")
parser.add_option('-v','--verbose',dest='verbose',action="store_true",default=False,help="Print more verbose information [default %default]")
parms,remainder = parser.parse_args()

logging.basicConfig(format='%(asctime)s.%(msecs)03d %(levelname)s: %(name)s %(message)s', level=logging.INFO,datefmt='%Y-%m-%d %H:%M:%S')
logger = logging.getLogger(__name__)
GDLogger = logging.getLogger('timemachine.GD')
controlsLogger = logging.getLogger('timemachine.controls')

@retry(stop=stop_after_delay(10))
def retry_call(callable: Callable, *args, **kwargs):
    """Retry a call."""
    return callable(*args, **kwargs)

def twist_knob(screen_event: Event, knob: RotaryEncoder, label, date_reader:controls.date_knob_reader):
    if knob.is_active:
      print(f"Knob {label} steps={knob.steps} value={knob.value}")
    else:
      if knob.steps<knob.threshold_steps[0]: knob.steps = knob.threshold_steps[0]
      if knob.steps>knob.threshold_steps[1]: knob.steps = knob.threshold_steps[1]
      print(f"Knob {label} is inactive")
    date_reader.update()
    screen_event.set()

if parms.verbose:
  logger.debug (F"Setting logger levels to {logging.DEBUG}")
  logger.setLevel(logging.DEBUG)
  GDLogger.setLevel(logging.DEBUG)
  controlsLogger.setLevel(logging.DEBUG)

def select_tape(tape,state,scr):
   current = state.get_current()
   current['PLAY_STATE'] = config.READY  #  eject current tape, insert new one in player
   current['TAPE_ID'] = tape.identifier
   logger.info(F"Set TAPE_ID to {current['TAPE_ID']}")
   current['TRACK_NUM'] = -1
   current['DATE'] = state.date_reader.date
   scr.show_selected_date(current['DATE'])
   state.player.insert_tape(tape)
   state.set(current)

def select_button(button,state,scr):
   logger.debug ("pressing select")
   if not state.date_reader.tape_available(): return 
   date_reader = state.date_reader
   current = state.get_current()
   tapes = date_reader.archive.tape_dates[date_reader.fmtdate()]
   state.set(current)
   sleep(button._hold_time)
   if button.is_pressed: return
   else: 
     tape = tapes[0] 
     select_tape(tape,state,scr)

def select_button_longpress(button,state,scr):
   logger.debug ("long pressing select")
   if not state.date_reader.tape_available(): return 
   current = state.get_current()
   date_reader = state.date_reader
   tapes = date_reader.archive.tape_dates[date_reader.fmtdate()]
   itape = -1
   while button.is_held:
      itape = divmod(itape + 1,len(tapes))[1]
      tape_id = tapes[itape].identifier
      sbd = tapes[itape].stream_only()
      id_color = (0,255,255) if sbd else (0,0,255)
      logger.info (F"Selecting Tape: {tape_id}, the {itape}th of {len(tapes)} choices. SBD:{sbd}")
      if len(tape_id)<16: scr.show_venue(tape_id,color=id_color)
      else:
        for i in range(0,max(1,len(tape_id)),2):
          scr.show_venue(tape_id[i:],color=id_color)
   scr.show_venue(tape_id,color=id_color)
   tape = tapes[itape] 
   select_tape(tape,state,scr)

def play_pause_button(button,state,scr):
   current = state.get_current()
   if current['EXPERIENCE']: return 
   if not current['PLAY_STATE'] in [config.READY,config.PLAYING,config.PAUSED,config.STOPPED]: return 
   logger.debug ("pressing play_pause")
   if current['PLAY_STATE'] == config.PLAYING: 
      logger.info("Pausing on player") 
      state.player.pause()
      current['PLAY_STATE'] = config.PAUSED
   elif current['PLAY_STATE'] in [config.PAUSED,config.STOPPED,config.READY]: 
      current['PLAY_STATE'] = config.PLAYING
      scr.show_playstate(staged_play=True) # show that we've registered the button-press before blocking call.
      state.player.play()   # this is a blocking call
   state.set(current)
   scr.show_playstate()

def play_pause_button_longpress(button,state,scr):
   logger.debug (" longpress of play_pause -- nyi")

def stop_button(button,state,scr):
   current = state.get_current()
   if current['EXPERIENCE']: return 
   if current['PLAY_STATE'] in [config.READY,config.INIT,config.STOPPED]: return 
   state.player.stop()
   current['PLAY_STATE'] = config.STOPPED
   state.set(current)
   scr.show_playstate()
   state.set(current)

def stop_button_longpress(button,state,scr):
   logger.debug (F" longpress of {button.name} -- nyi")

def rewind_button(button,state,scr):
   current = state.get_current()
   if current['EXPERIENCE']: return 
   sleep(button._hold_time)
   if button.is_pressed: return # the button is being "held"
   if current['TRACK_NUM']<len(state.player.playlist): state.player.next()

def rewind_button_longpress(button,state,scr):
   logger.debug ("longpress of rewind")
   state.player.seek(3)

def ffwd_button(button,state,scr):
   current = state.get_current()
   if current['EXPERIENCE']: return 
   sleep(button._hold_time)
   if button.is_pressed: return # the button is being "held"
   if current['TRACK_NUM']<len(state.player.playlist): state.player.next()

def ffwd_button_longpress(button,state,scr):
   logger.debug ("longpress of ffwd")
   state.player.seek(3)

def month_button(button,state,scr):
   current = state.get_current()
   if button.longpress: month_button_longpress(button,state)  
   if button.press: 
     if current['EXPERIENCE']: 
       current['EXPERIENCE'] = False
       scr.show_experience("") 
     else:
       current['EXPERIENCE'] = True
       scr.show_experience("Press Month to\nExit Experience") 
     state.set(current)

def month_button_longpress(button,state):
   logger.debug (F" longpress of {button.name} -- nyi")

def day_button(button,state,scr):
   current = state.get_current()
   if current['EXPERIENCE']: return 
   if button.longpress: day_button_longpress(button,state)  
   if button.press: 
      new_date = state.date_reader.next_date() 
      state.date_reader.y.value = new_date.year; 
      state.date_reader.m.value = new_date.month; 
      state.date_reader.d.value = new_date.day;
 
def day_button_longpress(button,state):
   logger.debug (F"long pressing {button.name}")

def year_button(button,state,scr):
   current = state.get_current()
   if current['EXPERIENCE']: return 
   if button.longpress: year_button_longpress(button,state)  
   if button.press:
      m = state.date_reader.m; d = state.date_reader.d
      today = datetime.date.today(); now_m = today.month; now_d = today.day
      if m.value == now_m and d.value == now_d:   # move to the next year where there is a tape available
         tihstring = F"{m.value:0>2d}-{d.value:0>2d}"
         tih_tapedates = [to_date(d) for d in state.date_reader.archive.dates if d.endswith(tihstring)]
         if len(tih_tapedates) > 0:
            cut = 0
            for i,dt in enumerate(tih_tapedates):
               if dt.year > y.value:
                 cut = i 
                 break
            tapedate = (tih_tapedates[cut:]+tih_tapedates[:cut])[0]
            logger.debug(F"tapedate is {tapedate}")
            y.value = tapedate.year
      else:
         m.value = now_m; d.value = now_d
 
def year_button_longpress(button,state):
   logger.debug (F"long pressing {button.name} -- nyi")

def update_screen(button,state,scr):
   logger.debug (F"in slow timer")
   current = state.get_current()
   if current['DATE']:
     scr.show_staged_date(current['DATE'])
     scr.show_venue(state.player.tape.venue())
   if current['EXPERIENCE']: return
   scr.show_track(current['TRACK_TITLE'],0)
   scr.show_track(current['NEXT_TRACK_TITLE'],1)

def fast_timer(state,scr):
   current = state.get_current()
   if current['EXPERIENCE']: return
   scr.show_track(current['TRACK_TITLE'],0)  ## This should be a player callback.
   scr.show_track(current['NEXT_TRACK_TITLE'],1)
    
def callback(item,state=None,scr=None):
   #logger.debug(F"in callback for item {item.name}.State is {state}")
   if item == None: return fast_timer(state,scr)
   try:
     if item.name == 'select':     select_button(item,state,scr)
     if item.name == 'play_pause': play_pause_button(item,state,scr)
     if item.name == 'stop':       stop_button(item,state,scr)
     if item.name == 'rewind':     rewind_button(item,state,scr)
     if item.name == 'ffwd':       ffwd_button(item,state,scr)
     if item.name == 'screen':     update_screen(item,state,scr)
     if item.name in ['year','month','day']:
       state.date_reader.update()
       if item.turn:
         item.turn = False
         print (F"-- date is:{state.date_reader.date}")
       else:
         if item.name == 'month': month_button(item,state,scr)
         if item.name == 'day':   day_button(item,state,scr)
         if item.name == 'year':  year_button(item,state,scr)
       state.date_reader.update()
       scr.show_staged_date(state.date_reader.date)
       scr.show_venue(state.date_reader.venue())
   finally:
     item.active = False
     item.press = False
     item.turn = False
     item.longpress = False

def to_date(d): return datetime.datetime.strptime(d,'%Y-%m-%d').date()

def play_tape(tape,player):
    logger.info(F"Playing tape {tape}")
    player.insert_tape(tape)
    player.play()
    return player

def main(parms):
    screen_event = Event()
    stop_event = Event()
    if parms.box == 'v0': 
       upside_down=True
       os.system("amixer sset 'Headphone' 100%")
    else: 
       upside_down = False
    scr = controls.screen(upside_down=upside_down)
    scr.clear()
    scr.show_text("(\);} \n  Time\n   Machine\n     Loading...",color=(0,255,255))
    archive = GD.GDArchive(parms.dbpath)
    player = GD.GDPlayer()

    y = retry_call(RotaryEncoder, config.year_pins[1], config.year_pins[0],max_steps = 0,threshold_steps = (0,30))
    m = retry_call(RotaryEncoder, config.month_pins[1], config.month_pins[0],max_steps = 0,threshold_steps = (1,12))
    d = retry_call(RotaryEncoder, config.day_pins[1], config.day_pins[0],max_steps = 0,threshold_steps = (1,31))
    y.steps = 1979-1965; m.steps = 11; d.steps = 2;
    date_reader = controls.date_knob_reader(y,m,d,archive)
    state = controls.state(date_reader,player)
    y.when_rotated = lambda x: twist_knob(screen_event, y, "year",date_reader)
    m.when_rotated = lambda x: twist_knob(screen_event, m, "month",date_reader)
    d.when_rotated = lambda x: twist_knob(screen_event, d, "day",date_reader)
    y_button = retry_call(Button, config.year_pins[2])
    m_button = retry_call(Button, config.month_pins[2])
    d_button = retry_call(Button, config.day_pins[2])
    select = retry_call(Button, config.select_pin,hold_time = 0.5,hold_repeat = False)
    play_pause = retry_call(Button, config.play_pause_pin,hold_time = 5)
    ffwd = retry_call(Button, config.ffwd_pin,hold_time = 0.5,hold_repeat = True)
    rewind = retry_call(Button, config.rewind_pin,hold_time = 0.5,hold_repeat = True)
    stop = retry_call(Button, config.stop_pin,hold_time = 5)

    play_pause.when_pressed = lambda button: play_pause_button(button,state,scr)
    play_pause.when_held = lambda button: play_pause_button_longpress(button,state,scr) 

    select.when_pressed = lambda button: select_button(button,state,scr)
    select.when_held = lambda button: select_button_longpress(button,state,scr)

    ffwd.when_pressed = lambda button: ffwd_button(button,state,scr)
    ffwd.when_held = lambda button: ffwd_button_longpress(button,state,scr)

    rewind.when_pressed = lambda button: rewind_button(button,state,scr)
    rewind.when_held = lambda button: rewind_button_longpress(button,state,scr)

    stop.when_pressed = lambda button: stop_button(button,state,scr)
    stop.when_held = lambda button: stop_button_longpress(button,state,scr)

    scr.clear()
    scr.show_staged_date(date_reader.date)
    try:
        while not stop_event.wait(timeout=0.001):
            if screen_event.is_set():
                scr.show_staged_date(date_reader.date)
                screen_event.clear()
    except KeyboardInterrupt:
        exit(0)


    [x.cleanup() for x in [y,m,d]] ## redundant, only one cleanup is needed!

#parser.print_help()
for k in parms.__dict__.keys(): print (F"{k:20s} : {parms.__dict__[k]}")
if __name__ == "__main__" and parms.debug==0:
  main(parms)
