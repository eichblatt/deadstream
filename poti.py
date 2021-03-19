#!/usr/bin/python3

from RPi import GPIO
from time import sleep

cl0,dt0,sw0= 23,22,24   # GPIO numbers
dt1,sw1= 27,17   # GPIO numbers
dt2,sw2= 18,15   # GPIO numbers

backward = False
year = 1966; month = 3; day = 19;

channel_dict = {24:'year',17:'month',15:'day'}
dir_dict = {GPIO.RISING:'RISING',GPIO.FALLING:'FALLING',GPIO.BOTH:'BOTH'}

GPIO.setmode(GPIO.BCM)
[GPIO.setup(x,GPIO.IN,pull_up_down=GPIO.PUD_DOWN) for x in [cl0,dt0,sw0,dt1,sw1,dt2,sw2]]

swtype = GPIO.BOTH
def sw_callback(channel):
    print(F"this is an sw edge event {dir_dict[swtype]} callback. Pushed {channel_dict[channel]} Button ({channel})")

GPIO.add_event_detect(sw0,GPIO.BOTH, callback = sw_callback, bouncetime = 300)
GPIO.add_event_detect(sw1,GPIO.BOTH, callback = sw_callback, bouncetime = 300)
GPIO.add_event_detect(sw2,GPIO.BOTH, callback = sw_callback, bouncetime = 300)

dttype = GPIO.BOTH
def dt_callback(channel):
    global year; global month; global day;
    print(F"this is an dt edge {dir_dict[dttype]} event callback {channel}")
    print(F"backward is {backward}")
    if channel == 22: year = 1965 + divmod(year-1965 + (-1 if backward else 1),31)[1]
    if channel == 27: month = 1 + divmod(month-1 + (-1 if backward else 1),12)[1]
    if channel == 18: day = day + (-1 if backward else 1) 
    print(F"Date set to {year},{month},{day}")
    sleep(0.1)

GPIO.add_event_detect(dt0,dttype, callback = dt_callback, bouncetime = 300)
GPIO.add_event_detect(dt1,dttype, callback = dt_callback, bouncetime = 300)
GPIO.add_event_detect(dt2,dttype, callback = dt_callback, bouncetime = 300)

cltype = GPIO.FALLING
def cl_callback(channel):
    global backward 
    backward = False
    print(F"this is an cl edge event {dir_dict[cltype]} callback {channel}")
    sleep(1)
    backward = True
    
GPIO.add_event_detect(cl0,cltype, callback = cl_callback, bouncetime = 300)

"""

oCtr,ctr= 1965,1965
cl0State,dt0State,sw0State= GPIO.input(cl0),GPIO.input(dt0),GPIO.input(sw0)
ocl0,odt0,osw0= cl0State,dt0State,sw0State
print (' --> 0 ',cl0State,dt0State,sw0State)

try:

        while True:
                cl0State,dt0State,sw0State= GPIO.input(cl0),GPIO.input(dt0),GPIO.input(sw0)

                if osw0==1 and sw0State==0:
                  if ctr==1965: ctr= 1995
                  else:
                        if ctr==1995: ctr= 1965
                        else:
                              ctr= 1965
                  print()

                if cl0State!=ocl0 or dt0State!=odt0:
                  if ocl0==1 and odt0==1 and cl0State==1 and dt0State==0: ctr -= 1
                  if ocl0==1 and odt0==1 and cl0State==0 and dt0State==1: ctr += 1

                if ctr<1965: ctr= 1965
                if ctr>1995: ctr= 1995

                if ctr!=oCtr: print ('          --year--  ',ctr)
                oCtr= ctr
                ocl0,odt0,osw0= cl0State,dt0State,sw0State

                sleep(0.001)
finally:
        GPIO.cleanup()
"""
