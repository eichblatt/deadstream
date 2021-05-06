#!/usr/bin/python3
import optparse,random,logging,os,datetime
import threading
from timemachine import GD
from timemachine import controls
from timemachine import config
from time import sleep
from threading import Event
from typing import Callable
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

stagedate_event = Event()
select_event = Event()
track_event = Event()
playstate_event = Event()
stop_event = Event()


@retry(stop=stop_after_delay(10))
def retry_call(callable: Callable, *args, **kwargs):
    """Retry a call."""
    return callable(*args, **kwargs)

def twist_knob(knob: RotaryEncoder, label, date_reader:controls.date_knob_reader):
    if knob.is_active:
      logger.debug(f"Knob {label} steps={knob.steps} value={knob.value}")
    else:
      if knob.steps<knob.threshold_steps[0]: knob.steps = knob.threshold_steps[0]
      if knob.steps>knob.threshold_steps[1]: knob.steps = knob.threshold_steps[1]
      logger.debug(f"Knob {label} is inactive")
    date_reader.update()
    stagedate_event.set()

if parms.verbose:
  logger.debug (F"Setting logger levels to {logging.DEBUG}")
  logger.setLevel(logging.DEBUG)
  GDLogger.setLevel(logging.DEBUG)
  controlsLogger.setLevel(logging.DEBUG)

def select_tape(tape,state):
   current = state.get_current()
   current['PLAY_STATE'] = config.READY  #  eject current tape, insert new one in player
   current['TAPE_ID'] = tape.identifier
   logger.info(F"Set TAPE_ID to {current['TAPE_ID']}")
   current['TRACK_NUM'] = -1
   current['DATE'] = state.date_reader.date
   current['VENUE'] = state.date_reader.venue()
   state.player.insert_tape(tape)
   state.set(current)

def select_button(button,state):
   logger.debug ("pressing select")
   current = state.get_current()
   if current['EXPERIENCE']: return 
   if not state.date_reader.tape_available(): return 
   date_reader = state.date_reader
   tapes = date_reader.archive.tape_dates[date_reader.fmtdate()]
   state.set(current)
   sleep(button._hold_time)
   if button.is_pressed: return
   if button.is_held: return
   else: 
     logger.debug ("pressing, not holding select")
     tape = tapes[0] 
     select_tape(tape,state)
     select_event.set()

def select_button_longpress(button,state,scr):
   logger.debug ("long pressing select")
   stop_event.set()
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
         if not button.is_held: break
   scr.show_venue(tape_id,color=id_color)
   tape = tapes[itape] 
   select_tape(tape,state)
   select_event.set()
   stop_event.clear()

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
      state.player.play()   # this is a blocking call. I could move the "wait_until_playing" to the event handler.
   state.set(current)
   playstate_event.set()

def play_pause_button_longpress(button,state):
   logger.debug (" longpress of play_pause -- choose random date and play it")
   stop_event.set()
   current = state.get_current()
   if current['EXPERIENCE']: 
     current['EXPERIENCE'] = False
   new_date = random.choice(state.date_reader.archive.dates)
   tape = state.date_reader.archive.best_tape(new_date)
   current['DATE'] = to_date(new_date)
   state.date_reader.set_date(current['DATE'])
   current['VENUE'] = state.date_reader.venue()

   if current['PLAY_STATE'] in [config.PLAYING,config.PAUSED]:
     state.player.stop()
   state.player.insert_tape(tape)
   current['PLAY_STATE'] = config.PLAYING
   state.player.play()   # this is a blocking call. I could move the "wait_until_playing" to the event handler.

   state.set(current)
   select_event.set()
   stagedate_event.set()
   playstate_event.set()
   stop_event.clear()

def stop_button(button,state):
   current = state.get_current()
   if current['EXPERIENCE']: return 
   if current['PLAY_STATE'] in [config.READY,config.INIT,config.STOPPED]: return 
   state.player.stop()
   current['PLAY_STATE'] = config.STOPPED
   state.set(current)
   playstate_event.set()

def stop_button_longpress(button,state):
   logger.debug (F" longpress of {button.name} -- nyi")

def rewind_button(button,state):
   current = state.get_current()
   if current['EXPERIENCE']: return 
   sleep(button._hold_time)
   if button.is_pressed: return # the button is being "held"
   if current['TRACK_NUM']<len(state.player.playlist): state.player.prev()

def rewind_button_longpress(button,state):
   logger.debug ("longpress of rewind")
   stop_event.set()
   while button.is_held:
     state.player.fseek(-30)
   stop_event.clear()

def ffwd_button(button,state):
   current = state.get_current()
   if current['EXPERIENCE']: return 
   sleep(button._hold_time)
   if button.is_pressed: return # the button is being "held"
   if current['TRACK_NUM']<len(state.player.playlist): state.player.next()

def ffwd_button_longpress(button,state):
   logger.debug ("longpress of ffwd")
   stop_event.set()
   while button.is_held:
     state.player.fseek(30)
   stop_event.clear()

def month_button(button,state):
   current = state.get_current()
   if current['EXPERIENCE']: 
     current['EXPERIENCE'] = False
   else:
     current['EXPERIENCE'] = True
   state.set(current)
   track_event.set()

def month_button_longpress(button,state):
   logger.debug (F" longpress of {button.name} -- nyi")

def day_button(button,state):
   current = state.get_current()
   if current['EXPERIENCE']: return 
   new_date = state.date_reader.next_date() 
   state.date_reader.set_date(new_date)
   stagedate_event.set()
 
def day_button_longpress(button,state):
   logger.debug (F"long pressing {button.name}")

def year_button(button,state):
   current = state.get_current()
   if current['EXPERIENCE']: return 
   today = datetime.date.today(); now_m = today.month; now_d = today.day
   m = state.date_reader.date.month; d = state.date_reader.date.day; y = state.date_reader.date.year

   if m == now_m and d == now_d:   # move to the next year where there is a tape available
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
        state.date_reader.set_date(datetime.date(tapedate.year,now_m,now_d))
   else:
     state.date_reader.set_date(datetime.date(y,now_m,now_d))
   stagedate_event.set()
 
def year_button_longpress(button,state):
   logger.debug (F"long pressing {button.name} -- nyi")

def update_tracks(state,scr):
   current = state.get_current()
   if current['EXPERIENCE']: 
      scr.show_experience()
   else:
     scr.show_track(current['TRACK_TITLE'],0)
     scr.show_track(current['NEXT_TRACK_TITLE'],1)

def fast_timer(state,scr):
   current = state.get_current()
   if current['EXPERIENCE']: return
   scr.show_track(current['TRACK_TITLE'],0)  ## This should be a player callback.
   scr.show_track(current['NEXT_TRACK_TITLE'],1)
    
def to_date(d): return datetime.datetime.strptime(d,'%Y-%m-%d').date()

def play_tape(tape,player):
    logger.info(F"Playing tape {tape}")
    player.insert_tape(tape)
    player.play()
    return player

def event_loop(state,scr):
    date_reader = state.date_reader
    last_sdevent = datetime.datetime.now()
    q_counter = False
    n_timer = 0
    last_idle_second_hand = None
    clear_stagedate = False
    try:
        while True:
            if stop_event.wait(timeout=0.001): continue
            now = datetime.datetime.now()
            n_timer = n_timer + 1
            idle_seconds = (now-last_sdevent).seconds 
            idle_second_hand = divmod(idle_seconds,20)[1]

            if stagedate_event.is_set():
                #sleep(0.5)
                last_sdevent = now; q_counter = True
                scr.show_staged_date(date_reader.date)
                scr.show_venue(date_reader.venue())
                if clear_stagedate: stagedate_event.clear()
                clear_stagedate = not clear_stagedate   # only clear stagedate event after updating twice
            if track_event.is_set():
                update_tracks(state,scr)
                track_event.clear()
            if select_event.is_set():
                current = state.get_current()
                scr.show_selected_date(current['DATE'])
                update_tracks(state,scr)
                select_event.clear()
            if playstate_event.is_set():
                scr.show_playstate()
                playstate_event.clear()
            if q_counter and config.DATE and idle_seconds > config.QUIESCENT_TIME:
                logger.debug(F"Reverting staged date back to selected date {idle_seconds}> {config.QUIESCENT_TIME}")
                scr.show_staged_date(config.DATE)
                scr.show_venue(config.VENUE)
                q_counter = False
            if idle_second_hand in [4,9,14,19] and idle_second_hand != last_idle_second_hand:  
                last_idle_second_hand = idle_second_hand
                logger.debug(F"idle second hand from {idle_seconds}> {idle_second_hand}")
                track_event.set()
                playstate_event.set()
                #stagedate_event.set()         # NOTE: this would set the q_counter, etc. But it SHOULD work.
                #scr.show_staged_date(date_reader.date)
                if idle_seconds > config.QUIESCENT_TIME:
                  if idle_second_hand in [9]:
                    if 'tape' in vars(state.player).keys():
                      sbd = state.player.tape.stream_only()
                      id_color = (0,255,255) if sbd else (0,0,255)
                      scr.show_venue(state.player.tape.identifier,color=id_color)
                  elif idle_second_hand in [19]:
                    if config.VENUE: scr.show_venue(config.VENUE)
                else:
                  scr.show_staged_date(date_reader.date)
                  scr.show_venue(date_reader.venue())
    except KeyboardInterrupt:
        exit(0)

def main(parms):
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
    @player.property_observer('playlist-pos')
    def on_track_event(_name, value):
      track_event.set()
      logger.debug(F'in track event callback {_name}, {value}')

    @player.event_callback('file-loaded')
    def my_handler(event):
      logger.debug('file-loaded')

    y = retry_call(RotaryEncoder, config.year_pins[1], config.year_pins[0],max_steps = 0,threshold_steps = (0,30))
    m = retry_call(RotaryEncoder, config.month_pins[1], config.month_pins[0],max_steps = 0,threshold_steps = (1,12))
    d = retry_call(RotaryEncoder, config.day_pins[1], config.day_pins[0],max_steps = 0,threshold_steps = (1,31))
    y.steps = 1979-1965; m.steps = 11; d.steps = 2;
    date_reader = controls.date_knob_reader(y,m,d,archive)
    state = controls.state(date_reader,player)
    y.when_rotated = lambda x: twist_knob(y, "year",date_reader)
    m.when_rotated = lambda x: twist_knob(m, "month",date_reader)
    d.when_rotated = lambda x: twist_knob(d, "day",date_reader)
    y_button = retry_call(Button, config.year_pins[2])
    m_button = retry_call(Button, config.month_pins[2])
    d_button = retry_call(Button, config.day_pins[2])
    select = retry_call(Button, config.select_pin,hold_time = 0.5,hold_repeat = False)
    play_pause = retry_call(Button, config.play_pause_pin,hold_time = 5)
    ffwd = retry_call(Button, config.ffwd_pin,hold_time = 0.5,hold_repeat = False)
    rewind = retry_call(Button, config.rewind_pin,hold_time = 0.5,hold_repeat = False)
    stop = retry_call(Button, config.stop_pin,hold_time = 5)

    play_pause.when_pressed = lambda button: play_pause_button(button,state,scr)
    play_pause.when_held = lambda button: play_pause_button_longpress(button,state) 

    select.when_pressed = lambda button: select_button(button,state)
    select.when_held = lambda button: select_button_longpress(button,state,scr)

    ffwd.when_pressed = lambda button: ffwd_button(button,state)
    ffwd.when_held = lambda button: ffwd_button_longpress(button,state)

    rewind.when_pressed = lambda button: rewind_button(button,state)
    rewind.when_held = lambda button: rewind_button_longpress(button,state)

    stop.when_pressed = lambda button: stop_button(button,state)
    stop.when_held = lambda button: stop_button_longpress(button,state)
 
    m_button.when_pressed = lambda button: month_button(button,state)
    d_button.when_pressed = lambda button: day_button(button,state)
    y_button.when_pressed = lambda button: year_button(button,state)

    scr.clear()
    scr.show_text("Powered by\n archive.org",color=(0,255,255))

    event_loop(state,scr)

    [x.cleanup() for x in [y,m,d]] ## redundant, only one cleanup is needed!

#parser.print_help()
for k in parms.__dict__.keys(): print (F"{k:20s} : {parms.__dict__[k]}")
if __name__ == "__main__" and parms.debug==0:
  main(parms)
