#!/usr/bin/python3
import optparse
from timemachine import GD
from timemachine import controls as ctl
from timemachine import config
from time import sleep
import logging
import threading
import signal
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

#meInterrupt = False
#def meCustomHandler(signum,stack_frame):
#   global meInterrupt
#   print('encountered ctrl+C - here before the process exists')
#   meInterrupt= True

#signal.signal(signal.SIGINT, meCustomHandler)

def to_date(d): return datetime.datetime.strptime(d,'%Y-%m-%d').date()

def get_module_dict(module_name): 
    module = globals().get(module_name,None)
    d = {}
    if module:
      d = {key: value for key,value in module.__dict__.items() if (not key.startswith('_')) and key.isupper()}
    return d

def play_tape(tape,player):
    logger.info(F"Playing tape {tape}")
    player.insert_tape(tape)
    player.play()
    return player

def date_knob_changes(state,changes,current,scr,tape,quiescent,q_counter):
      sbd = None;
      if 'DATE_READER' in changes.keys():  # Date knobs changed
         logger.info (F"DATE: {config.DATE}, SELECT_STAGED_DATE: {config.SELECT_STAGED_DATE}, PLAY_STATE: {config.PLAY_STATE}. quiescent {quiescent}")
         if state.date_reader.tape_available(): 
            scr.show_venue(state.date_reader.venue())
         else:
            scr.clear_area(scr.venue_bbox,now=True) # erase the venue
         scr.show_staged_date(current['DATE_READER'])
         quiescent = 0; q_counter = True
      if current['TIH']:   # Year Button was Pushed, set Month and Date to Today in History
         m.value = datetime.date.today().month; d.value = datetime.date.today().day
         current['TIH'] = False
         quiescent = 0; q_counter = True
         state.set(current)
      if current['NEXT_DATE']:   # Day Button was Pushed, set date to next date with tape available
         new_date = state.date_reader.next_date() 
         y.value = new_date.year; m.value = new_date.month; d.value = new_date.day;
         current['NEXT_DATE'] = False
         quiescent = 0; q_counter = True
         # state.set(current)
      if state.date_reader.tape_available():
         tapes = state.date_reader.archive.tape_dates[state.date_reader.fmtdate()]
         itape = -1
         while current['NEXT_TAPE']:   # Select Button was Pushed and Held
           itape = divmod(itape + 1,len(tapes))[1]
           tape_id = tapes[itape].identifier
           sbd = tapes[itape].stream_only()
           id_color = (0,255,255) if sbd else (0,0,255)
           logger.info (F"In NEXT_TAPE. Choosing {tape_id}, the {itape}th of {len(tapes)} choices. SBD:{sbd}")
           #scr.show_soundboard(sbd)
           if len(tape_id)<16: scr.show_venue(tape_id,color=id_color)
           else:
             for i in range(0,max(1,len(tape_id)),2):
               scr.show_venue(tape_id[i:],color=id_color)
               if not current['NEXT_TAPE']: 
                 scr.show_venue(tape_id,color=id_color)
                 break 
         itape = max(0,itape) 
         if current['SELECT_STAGED_DATE']:   # Select Button was Pushed and Released
           current['DATE'] = state.date_reader.date 
           logger.info(F"Set DATE to {current['DATE']}")
           current['PLAY_STATE'] = config.READY  #  eject current tape, insert new one in player
           tape = tapes[itape] 
           current['TAPE_ID'] = tape.identifier
           logger.info(F"Set TAPE_ID to {current['TAPE_ID']}")
           current['TRACK_NUM'] = -1
           sbd = tape.stream_only()
           #scr.show_soundboard(sbd)
           scr.show_selected_date(current['DATE'])
      current['SELECT_STAGED_DATE'] = False
      current['NEXT_TAPE'] = False
      return (current,tape,sbd,quiescent,q_counter)

  
def update_tracks(state,current,changes,scr):
    if not current['PLAY_STATE'] in [config.PLAYING,config.PAUSED]: return
    if current['TRACK_NUM'] == None :        # this happens when the tape has ended (at least).
      current['PLAY_STATE'] = config.INIT   # NOTE Not quite working
      return

    if current['TRACK_ID'] in changes.keys():
      title = state.player.tape.tracks()[current['TRACK_NUM']].title
      scr.show_track(title,0)
      print (F"show title {title}")
      if (current['TRACK_NUM']+1)<len(state.player.playlist):
         next_track = current['TRACK_NUM']+1 
         next_title = state.player.tape.tracks()[next_track].title
         scr.show_track(next_title,1)
      else: scr.show_track('',1)
      scr.show_playstate()

def playstate_static(state,changes,current,scr,tape):
    if current['FFWD']:
       state.player.next()
       current['FFWD'] = False
    else: 
       while current['FSEEK']:
         state.player.seek(1)
    if current['REWIND']:
       state.player.prev()
       current['REWIND'] = False
    else: 
       while current['RSEEK']:
         state.player.seek(-1)
    if current['PLAY_STATE'] == config.INIT:
       scr.show_track('',0)
       scr.show_track('',1)
       scr.show_playstate()
    if (current['PLAY_STATE'] in [config.INIT,config.READY, config.STOPPED]) and 'TAPE_ID' in changes.keys():
       scr.show_track('',0)
       scr.show_track('',1)
       scr.show_playstate()
       if current['PLAY_STATE'] == config.READY:
         logger.info(F"PLAY_STATE is {config.PLAY_STATE}. Inserting new tape")
         state.player.eject_tape()
         state.player.insert_tape(tape)
    return current

def playstate_changes(state,changes,current,scr,tape):
    if (current['PLAY_STATE'] == config.READY):  #  A new tape to be inserted
       logger.info(F"PLAY_STATE is {config.PLAY_STATE}. Inserting new tape")
       state.player.eject_tape()
       state.player.insert_tape(tape)
    if (current['PLAY_STATE'] == config.PLAYING):  # Play tape 
       try:
         logger.info(F"Playing {current['DATE']} on player")
         scr.show_playstate(staged_play=True) # show an empty triangle, to register the button press.
         #tape = archive.best_tape(config.DATE.strftime('%Y-%m-%d'))
         if len(state.player.playlist) == 0: state.player = play_tape(tape,state.player)  ## NOTE required?
         else: state.player.play()
         scr.show_venue(state.date_reader.venue())
         scr.show_playstate()
       except AttributeError:
         logger.info(F"Cannot play date {current['DATE']}")
         pass
       except:
         raise 
       finally:
         pass
    if current['PLAY_STATE'] == config.PAUSED: 
       logger.info(F"Pausing {current['DATE'].strftime('%Y-%m-%d')} on player") 
       state.player.pause()
       scr.show_playstate()
    if current['PLAY_STATE'] == config.STOPPED:
       state.player.stop()
       scr.show_playstate()
    return current

def runLoop(state,scr,maxN=None):

    N = 0; 
    scr.refresh()
    tape = None; sbd = None;
    quiescent = 0; q_counter = False

    while N<=maxN if maxN != None else True:
      N = N+1; 
      if q_counter: quiescent = quiescent + 1
      changes,previous,current = state.snap()

      if quiescent > config.QUIESCENT_TIME and current['PLAY_STATE'] in [config.PAUSED,config.PLAYING]: # the dates have not been changed in a while -- revert staged_date to date
         logger.info (F"quiescent: {quiescent}")
         quiescent = 0; q_counter = False
         scr.show_staged_date(to_date(state.player.tape.date))
         scr.show_venue(state.player.tape.venue())

      update_tracks(state,current,changes,scr)

      if len(changes) == 0:
         sleep(.02)
         continue

      logger.info (F"change keys {changes.keys()}")
      if 'EXPERIENCE' in changes.keys():
         if current['EXPERIENCE']:   
           frozen_config = current.copy()
           frozen_config['EXPERIENCE'] = False
           scr.show_experience("Press Month to\nExit Experience") 
         if not current['EXPERIENCE']:  # we have exited EXPERIENCE mode
           state.set(frozen_config)
           scr.show_experience("") 

      if current['EXPERIENCE']: 
         continue

      current,tape,sbd,quiescent,q_counter = date_knob_changes(state,changes,current,scr,tape,quiescent,q_counter)

      update_tracks(state,current,changes,scr)

      if 'PLAY_STATE' in changes.keys():   
        current = playstate_changes(state,changes,current,scr,tape) 
      else:
        current = playstate_static(state,changes,current,scr,tape) 
      
      #import pdb; pdb.set_trace()
      state.set(current)
      sleep(.02); 



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
       #os.system("amixer sset 'Headphone' 100%")
    scr = ctl.screen(upside_down=upside_down)
    scr.clear()
    scr.show_text("Grateful\n  Dead\n   Streamer\n     Loading...",color=(0,255,255))

    logger.info ("Loading GD Archive")
    a = GD.GDArchive(parms.dbpath)
    logger.info ("Done ")
    
    scr.clear()
    date_reader = ctl.date_knob_reader(y,m,d,a)
    logger.info(date_reader)

    scr.show_staged_date(date_reader.date)
    scr.show_venue(date_reader.venue())
    state = ctl.state(date_reader,player)
    # runLoop((y,m,d),a,scr,player)
    # runLoop(state,scr)
    loop = threading.Thread(target=runLoop,name="timemachine loop",args=(state,scr),kwargs={'maxN':None})
    loop.start()

    loop.join()
    [x.cleanup() for x in [y,m,d]] ## redundant, only one cleanup is needed!

#parser.print_help()
for k in parms.__dict__.keys(): print (F"{k:20s} : {parms.__dict__[k]}")
if __name__ == "__main__" and parms.debug==0:
  main(parms)
