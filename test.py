#!/usr/bin/python3
import optparse
from deadstream import GD
from deadstream import controls as ctl
import config
from time import sleep
import logging
import threading
import signal

parser = optparse.OptionParser()
parser.add_option('-d','--debug',dest='debug',type="int",default=1,help="If > 0, don't run the main script on loading")
parser.add_option('-v','--verbose',dest='verbose',action="store_true",default=False,help="Print more verbose information")
parms,remainder = parser.parse_args()

logLevel = 0 if parms.verbose else logging.INFO
logging.basicConfig(format='%(asctime)s.%(msecs)03d %(levelname)s: %(message)s', level=logLevel,datefmt='%Y-%m-%d %H:%M:%S')

meInterrupt = False
def meCustomHandler(signum,stack_frame):
   global meInterrupt
   print('encountered ctrl+C - here before the process exists')
   meInterrupt= True

signal.signal(signal.SIGINT, meCustomHandler)

def play_tape(tape,player):
    logging.info(F"Playing tape {tape}")
    player.insert_tape(tape)
    player.play()
    return player

def runLoop(knobs,a,scr,player,maxN=None):
    global meInterrupt
    y,m,d = knobs
    play_state = config.PLAY_STATE
    d0 = (ctl.date_knob_reader(y,m,d,a)).date
    N = 0

    while N<=maxN if maxN != None else True:
      staged_date = ctl.date_knob_reader(y,m,d,a)
      if meInterrupt: break   ## not working (yet)
      # deal with DATE changes
      N = N+1
      if staged_date.date != d0:  # Date knobs changed
         logging.info (F"DATE: {config.DATE}, SELECT_DATE: {config.SELECT_DATE}, PLAY_STATE: {config.PLAY_STATE}")
         print (staged_date)
         d0 = staged_date.date
         if staged_date.tape_available(): 
    #        venue = staged_date.venue()
            venue = "Venue, City, State"
            scr.show_text(venue,(0,30))
         else:
            scr.clear_area((0,30,160,30)) # erase the venue
         scr.show_staged_date(staged_date.date)
      if config.SELECT_DATE:   # Year Button was Pushed
         if staged_date.tape_available():
            config.DATE = staged_date.date 
            logging.info(F"Setting DATE to {config.DATE}")
            config.PLAY_STATE = config.READY  #  eject current tape, insert new one in player
            scr.show_selected_date(config.DATE)
         config.SELECT_DATE = False

      # Deal with PLAY_STATE changes

      #PLAY_STATE = config.PLAY_STATE

      if (config.PLAY_STATE == play_state): sleep(0.1); continue
      if (config.PLAY_STATE == config.READY):  #  A new tape to be inserted
         player.eject_tape()
         tape = a.best_tape(config.DATE.strftime('%Y-%m-%d'))
         player.insert_tape(tape)
         config.PLAY_STATE = config.PLAYING
      if (config.PLAY_STATE == config.PLAYING):  # Play tape 
         try:
           logging.info(F"Playing {config.DATE} on player")
           tape = a.best_tape(config.DATE.strftime('%Y-%m-%d'))
           if len(player.playlist) == 0: player = play_tape(tape,player)  ## NOTE required?
           else: player.play()
           play_state = config.PLAYING
           scr.show_playstate()
         except AttributeError:
           logging.info(F"Cannot play date {config.DATE}")
           pass
         except:
           raise 
         finally:
           config.PLAY_STATE = play_state
      if config.PLAY_STATE == config.PAUSED: 
         logging.info(F"Pausing {config.DATE.strftime('%Y-%m-%d')} on player") 
         player.pause()
      if config.PLAY_STATE == config.STOPPED:
         player.stop()
         scr.show_playstate()
      play_state = config.PLAY_STATE
      scr.show_playstate()
      sleep(.1)

def main(parms):
    player = GD.GDPlayer()

    y = ctl.knob(config.year_pins,"year",range(1965,1996),1979)   # cl, dt, sw
    m = ctl.knob(config.month_pins,"month",range(1,13),11)
    d = ctl.knob(config.day_pins,"day",range(1,32),2,bouncetime=100)

    _ = [x.setup() for x in [y,m,d]]

    logging.info ("Loading GD Archive")
    a = GD.GDArchive('/home/steve/projects/deadstream/metadata')
    logging.info ("Done ")

    staged_date = ctl.date_knob_reader(y,m,d,a)
    print (staged_date)

    scr = ctl.screen()
    scr.clear()
    scr.show_staged_date(staged_date.date)
    #scr.show_text(staged_date.venue())
    loop = threading.Thread(target=runLoop,name="deadstream loop",args=((y,m,d),a,scr,player),kwargs={'maxN':None})
    loop.start()

    loop.join()
    [x.cleanup() for x in [y,m,d]] ## redundant, only one cleanup is needed!

print(F"parms: {parms}")
if __name__ == "__main__" and parms.debug==0:
  main(parms)
