from timemachine import controls as ctl
from timemachine import config
import datetime
from time import sleep
import threading

ctl.logger.setLevel(10) # DEBUG
d1 = '1977-05-08'
d1 =  datetime.date(*(int(s) for s in d1.split('-')))

s = ctl.screen()
s.clear()

s.show_staged_date(d1)

d2 = '1979-11-02'
d2 =  datetime.date(*(int(s) for s in d2.split('-')))
s.show_selected_date(d2)

s.show_text("Venue",(0,30))

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

play_state = config.PLAY_STATE
date_knob = ctl.date_knob_reader(y,m,d,None)
state = ctl.state(date_knob)
cfg = state.get_current()


config.PLAY_STATE = 1   # Ready

def callback(item):
   print (F"in callback for item {item.name}")
   print (F"-- press:{item.press} -- longpress:{item.longpress}")
   item.active = False
   item.press = False
   item.longpress = False
   if item.name in ['year','month','date']:
     date_knob.update()
     item.turn = False
     print (F"-- date is:{date_knob.date}")

buttons = threading.Thread(target=ctl.controlLoop,name="controlLoop",args=([select,play_pause,ffwd,rewind,stop],callback),kwargs={})
knobs = threading.Thread(target=ctl.controlLoop,name="knobs_controlLoop",args=([y,m,d],callback),kwargs={})
buttons.start()
knobs.start()

"""
#venue_thread.start()
#s.venue_name ="Fillmore West, San Francisco, CA"
venue_name ="Fillmore West, San Francisco, CA"

s.show_venue(venue_name)
s.show_experience("Press Month to\nExit Experience")
for i in range(4):
  config.PLAY_STATE = i
  s.show_playstate()
  s.show_playstate(sbd=True)
  sleep(1)

  s.show_soundboard(True)

while True:
    date_knob.update()
    s.show_staged_date(date_knob.date)
    if config.FSEEK:
        print ("calling player.seek(1)")
        config.FSEEK = False
    if config.FFWD: 
        print ("calling player.next()")
        config.FFWD = False
    sleep(0.001)

"""
