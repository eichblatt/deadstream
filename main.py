#!/usr/bin/python3
import optparse
from deadstream import GD
from deadstream import controls as ctl
import config
from time import sleep
import logging
import signal

logging.basicConfig(format='%(levelname)s:%(message)s', level=logging.INFO)

parser = optparse.OptionParser()
parser.add_option('--debug',dest='debug',default=True)
parser.add_option('--verbose',dest='verbose',default=False)
parms,remainder = parser.parse_args()

meInterrupt = False
def meCustomHandler(signum,stack_frame):
   global meInterrupt
   print('encountered ctrl+C - here before the process exists')
   meInterrupt= True

signal.signal(signal.SIGINT, meCustomHandler)

def meLoop(knobs,a,scr):
    y,m,d = knobs
    play_state = config.PLAY_STATE
    d0 = (ctl.date_knob_reader(y,m,d,a)).date
    player = None

    while True:
      staged_date = ctl.date_knob_reader(y,m,d,a)
      if staged_date.date != d0: 
        logging.info (F"DATE: {config.DATE}, SELECT_DATE: {config.SELECT_DATE}, PLAY_STATE: {config.PLAY_STATE}")
        print (staged_date)
        d0 = staged_date.date
        scr.show_date(staged_date.date,tape=staged_date.tape_available())
    #    if staged_date.tape_available(): 
    #      venue = staged_date.venue()
    #      scr.show_text(venue)
    #    else:
    #      scr.draw.rectangle((0,0,160,32),outline=0,fill=(0,0,0)) # erase the venue
    #      scr.disp.image(scr.image)
      if config.SELECT_DATE:
        if staged_date.tape_available():
           config.DATE = staged_date.date 
           date_fmt = config.DATE.strftime('%Y-%m-%d')
           logging.info(F"Setting DATE to {date_fmt}")
           tape = a.best_tape(date_fmt)
           player = GD.GDPlayer(tape)
           scr.show_date(config.DATE,loc=(85,0),size=10,color=(255,255,255),stack=True,tape=True)
        config.SELECT_DATE = False
      if config.PLAY_STATE and not play_state:  # start playing
         try:
           date_fmt = config.DATE.strftime('%Y-%m-%d')
           logging.info(F"Playing {date_fmt} on player")
           player.play()
           scr.show_playstate('playing')
         except AttributeError:
           logging.info(F"Cannot play date {config.DATE}")
           config.PLAY_STATE = play_state
           pass
         except:
           logging.info(F"Unexpected Error: {sys.exc_info()[0]}")
           config.PLAY_STATE = play_state
           raise 
      if not config.PLAY_STATE and play_state:  # pause playing
         try:
           logging.info(F"Pausing {date_fmt} on player")
           player.pause()
           scr.show_playstate('paused')
         except:
           logging.info(F"Unexpected Error: {sys.exc_info()[0]}")
           config.PLAY_STATE = play_state
           raise 
      play_state = config.PLAY_STATE
      if meInterrupt: return
      sleep(.1)

def main(parms):
    y = ctl.knob((16,22,23),"year",range(1965,1996),1979)   # cl, dt, sw
    m = ctl.knob((13,17,27),"month",range(1,13),11)
    d = ctl.knob((12,5,6)  ,"day",range(1,32),2,bouncetime=100)

    _ = [x.setup() for x in [y,m,d]]

    logging.info ("Loading GD Archive")
    a = GD.GDArchive('/home/steve/projects/deadstream/metadata')
    #a = None
    logging.info ("Done ")

    staged_date = ctl.date_knob_reader(y,m,d,a)
    print (staged_date)

    scr = ctl.screen()
    scr.clear()
    scr.show_date(staged_date.date,tape=staged_date.tape_available())
    #scr.show_text(staged_date.venue())
    try:
      meLoop((y,m,d),a,scr)
    finally:
      print("In Finally")
      [x.cleanup() for x in [y,m,d]] ## redundant, only one cleanup is needed!
