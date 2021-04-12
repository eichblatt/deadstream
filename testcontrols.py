from deadstream import controls as ctl
import config
import datetime,time

d1 = '1977-05-08'
d1 =  datetime.date(*(int(s) for s in d1.split('-')))

s = ctl.screen()
s.clear()

s.show_staged_date(d1)

d2 = '1979-11-02'
d2 =  datetime.date(*(int(s) for s in d2.split('-')))
s.show_selected_date(d2)

s.show_text("Venue",(0,30))
for i in [d1,d2,d1,d2,d1,d2,d1,d2,d1,d2]: s.show_staged_date(i)
for i in [d1,d2,d1,d2,d1,d2,d1,d2,d1,d2]: s.show_selected_date(i)

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
 
config.PLAY_STATE = 1   # Ready

while True:
    date_knob.update(y,m,d)
    s.show_staged_date(date_knob.date)
    if config.FSEEK:
        print ("calling player.seek(1)")
        config.FSEEK = False
    if config.FFWD: 
        print ("calling player.next()")
        config.FFWD = False
    time.sleep(0.001)
"""
while True:
    date_knob.update(y,m,d)
    s.show_staged_date(date_knob.date)
    if config.FFWD:
       seeking = False
       time.sleep(0.5)
       while not config.FFWD_RELEASED:
          seeking = True
          print ("calling player.seek(1)")
          time.sleep(0.1)
       if not seeking: print ("calling player.next()")
       config.FFWD = False
       config.FFWD_RELEASED = False
    time.sleep(0.001)
"""
