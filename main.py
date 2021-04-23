#!/usr/bin/python3
import optparse
from timemachine import GD
from timemachine import controls as ctl
from timemachine import config
from time import sleep
import logging
import threading
import os
import datetime

parser = optparse.OptionParser()
parser.add_option('--box',dest='box',type="string",default='v1',help="v0 box has screen at 270. [default %default]")
parser.add_option('--dbpath',dest='dbpath',type="string",default=os.path.join(os.getenv('HOME'),'projects/deadstream/metadata'),help="path to database [default %default]")
parser.add_option('-d','--debug',dest='debug',type="int",default=1,help="If > 0, don't run the main script on loading [default %default]")
parser.add_option('-v','--verbose',dest='verbose',action="store_true",default=False,help="Print more verbose information [default %default]")
parms,remainder = parser.parse_args()

logging.basicConfig(format='%(asctime)s.%(msecs)03d %(levelname)s: %(name)s %(message)s', level=logging.INFO,datefmt='%Y-%m-%d %H:%M:%S')
logger = logging.getLogger(__name__)
GDLogger = logging.getLogger('GD')
controlsLogger = logging.getLogger('controls')
if parms.verbose:
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

def select_button(item,state,scr):
   if not state.date_reader.tape_available(): return 
   date_reader = state.date_reader
   current = state.get_current()
   tapes = date_reader.archive.tape_dates[date_reader.fmtdate()]
   state.set(current)

   if item.longpress: select_button_longpress(item,state,scr,tapes)  
   if item.press: 
      logger.debug (F"pressing {item.name}")
      tape = tapes[0] 
      select_tape(tape,state,scr)

def select_button_longpress(item,state,scr,tapes):
   logger.debug (F"long pressing {item.name}")
   current = state.get_current()
   itape = -1
   while item.longpress:
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

def play_pause_button(item,state,scr):
   current = state.get_current()
   if current['EXPERIENCE']: return 
   if not current['PLAY_STATE'] in [config.READY,config.PLAYING,config.PAUSED,config.STOPPED]: return 
   if item.longpress: play_pause_button_longpress(item,state)  
   if item.press: 
     logger.debug (F"pressing {item.name}")
     if current['PLAY_STATE'] == config.PLAYING: 
        logger.info(F"Pausing  on player") 
        state.player.pause()
        current['PLAY_STATE'] = config.PAUSED
     elif current['PLAY_STATE'] in [config.PAUSED,config.STOPPED,config.READY]: 
        current['PLAY_STATE'] = config.PLAYING
        scr.show_playstate(staged_play=True) # show that we've registered the button-press before blocking call.
        state.player.play()   # this is a blocking call
     state.set(current)
     scr.show_playstate()

def play_pause_button_longpress(item,state):
   logger.debug (F" longpress of {item.name} -- nyi")

def stop_button(item,state,scr):
   current = state.get_current()
   if current['EXPERIENCE']: return 
   if current['PLAY_STATE'] in [config.READY,config.INIT,config.STOPPED]: return 
   if item.longpress: stop_button_longpress(item,state)  
   if item.press: 
      state.player.stop()
      current['PLAY_STATE'] = config.STOPPED
      state.set(current)
      scr.show_playstate()
   state.set(current)

def stop_button_longpress(item,state):
   logger.debug (F" longpress of {item.name} -- nyi")

def rewind_button(item,state,scr):
   current = state.get_current()
   if current['EXPERIENCE']: return 
   if item.longpress: rewind_button_longpress(item,state)  
   if item.press: 
      if current['TRACK_NUM']>0: state.player.prev()

def rewind_button_longpress(item,state):
   while item.longpress:
      logger.debug (F" longpress of {item.name} ")
      state.player.seek(-1)
      sleep(0.05) ## maximum speed is 1/0.05 = 20x

def ffwd_button(item,state,scr):
   current = state.get_current()
   if current['EXPERIENCE']: return 
   if item.longpress: ffwd_button_longpress(item,state)  
   if item.press: 
      if current['TRACK_NUM']<len(state.player.playlist): state.player.next()

def ffwd_button_longpress(item,state):
   while item.longpress:
      logger.debug (F" longpress of {item.name} -- nyi")
      state.player.seek(1)
      sleep(0.05) ## maximum speed is 1/0.05 = 20x

def month_button(item,state,scr):
   current = state.get_current()
   if item.longpress: month_button_longpress(item,state)  
   if item.press: 
     if current['EXPERIENCE']: 
       current['EXPERIENCE'] = False
       scr.show_experience("") 
     else:
       current['EXPERIENCE'] = True
       scr.show_experience("Press Month to\nExit Experience") 
     state.set(current)

def month_button_longpress(item,state):
   logger.debug (F" longpress of {item.name} -- nyi")

def day_button(item,state,scr):
   current = state.get_current()
   if current['EXPERIENCE']: return 
   if item.longpress: day_button_longpress(item,state)  
   if item.press: 
      new_date = state.date_reader.next_date() 
      state.date_reader.y.value = new_date.year; 
      state.date_reader.m.value = new_date.month; 
      state.date_reader.d.value = new_date.day;
 
def day_button_longpress(item,state):
   logger.debug (F"long pressing {item.name}")

def year_button(item,state,scr):
   current = state.get_current()
   if current['EXPERIENCE']: return 
   if item.longpress: year_button_longpress(item,state)  
   if item.press:
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
 
def year_button_longpress(item,state):
   logger.debug (F"long pressing {item.name} -- nyi")

def update_screen(item,state,scr):
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
    player = GD.GDPlayer()

    y = ctl.knob(config.year_pins,"year",range(1965,1996),1979)   # cl, dt, sw
    m = ctl.knob(config.month_pins,"month",range(1,13),11)
    d = ctl.knob(config.day_pins,"day",range(1,32),2,bouncetime=100)
    _ = [x.setup() for x in [y,m,d]]
 
    select = ctl.button(config.select_pin,"select")
    play_pause = ctl.button(config.play_pause_pin,"play_pause")
    ffwd = ctl.button(config.ffwd_pin,"ffwd")
    rewind = ctl.button(config.rewind_pin,"rewind")
    stop = ctl.button(config.stop_pin,"stop")
    _ = [x.setup() for x in [select,play_pause,ffwd,rewind,stop]]

    if parms.box == 'v0': upside_down=True
    else: 
       upside_down = False
       os.system("amixer sset 'Headphone' 100%")
    scr = ctl.screen(upside_down=upside_down)
    scr.clear()
    #scr.show_text("Grateful Dead\n  Time\n   Machine\n     Loading...",color=(0,255,255))
    scr.show_text("(\);} \n  Time\n   Machine\n     Loading...",color=(0,255,255))

    logger.info ("Loading GD Archive")
    a = GD.GDArchive(parms.dbpath)
    logger.info ("Done ")
    
    scr.clear()
    date_reader = ctl.date_knob_reader(y,m,d,a)
    logger.info(date_reader)

    scr.show_staged_date(date_reader.date)
    scr.show_venue(date_reader.venue())
    state = ctl.state(date_reader,player)

    controls = threading.Thread(target=ctl.controlLoop,name="controlLoop",args=([select,play_pause,ffwd,rewind,stop,scr,y,m,d],callback),kwargs={'state':state,'scr':scr})
    controls.start()

    #controls.join()

    [x.cleanup() for x in [y,m,d]] ## redundant, only one cleanup is needed!

#parser.print_help()
for k in parms.__dict__.keys(): print (F"{k:20s} : {parms.__dict__[k]}")
if __name__ == "__main__" and parms.debug==0:
  main(parms)
