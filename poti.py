#!/usr/bin/python

###
### --- mar'21 17-13:20
###
###     just to get a single potentiometer, ie 'rotary encoder' to function with the pi
###     rtuning and push button
###

from RPi import GPIO
from time import sleep

cl0,dt0,sw0= 23,22,24   # GPIO numbers

GPIO.setmode(GPIO.BCM)
GPIO.setup(cl0,GPIO.IN,pull_up_down=GPIO.PUD_DOWN)
GPIO.setup(dt0,GPIO.IN,pull_up_down=GPIO.PUD_DOWN)
GPIO.setup(sw0,GPIO.IN,pull_up_down=GPIO.PUD_DOWN)

oCtr,ctr= 1966,1966
cl0State,dt0State,sw0State= GPIO.input(cl0),GPIO.input(dt0),GPIO.input(sw0)
ocl0,odt0,osw0= cl0State,dt0State,sw0State
print (' --> 0 ',cl0State,dt0State,sw0State)

try:

        while True:
                cl0State,dt0State,sw0State= GPIO.input(cl0),GPIO.input(dt0),GPIO.input(sw0)

                if osw0==1 and sw0State==0:
                  if ctr==1966: ctr= 1995
                  else:
                        if ctr==1995: ctr= 1966
                        else:
                              ctr= 1966
                  print()

                if cl0State!=ocl0 or dt0State!=odt0:
                  if ocl0==1 and odt0==1 and cl0State==1 and dt0State==0: ctr -= 1
                  if ocl0==1 and odt0==1 and cl0State==0 and dt0State==1: ctr += 1

                if ctr<1966: ctr= 1966
                if ctr>1995: ctr= 1995

                if ctr!=oCtr: print ('          --year--  ',ctr)
                oCtr= ctr
                ocl0,odt0,osw0= cl0State,dt0State,sw0State

                sleep(0.001)
finally:
        GPIO.cleanup()

