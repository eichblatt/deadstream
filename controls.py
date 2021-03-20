#!/usr/bin/python3
from RPi import GPIO
from time import sleep
import datetime

class knob:
  def __init__(self,pins,name,values,init=None):
    self.cl, self.dt, self.sw = pins
    self.name = name
    self.direction = None
    self._values = values 
    self.value = min(values) if init == None else init

  def __str__(self):
    return self.__repr__()

  def __repr__(self):
    return F"{self.name}: pins cl:{self.cl}, dt:{self.dt}, sw:{self.sw}. Value: {self.value}"
 
  def setup(self):
    GPIO.setmode(GPIO.BCM)
    _ = [GPIO.setup(x,GPIO.IN,pull_up_down=GPIO.PUD_DOWN) for x in [self.cl,self.dt,self.sw]]
    GPIO.add_event_detect(self.sw,GPIO.BOTH, callback = self.sw_callback, bouncetime = 300) 
    GPIO.add_event_detect(self.dt,GPIO.BOTH, callback = self.dt_callback, bouncetime = 300) 
    GPIO.add_event_detect(self.cl,GPIO.FALLING, callback = self.cl_callback, bouncetime = 300) 
    return None 

  def pin_states(self,msg): 
    print(F"{self.name} {msg}: State of cl:{GPIO.input(self.cl)}, dt:{GPIO.input(self.dt)}, sw:{GPIO.input(self.sw)}")
  
  def cl_callback(self,channel):
    self.pin_states("cl")
    if GPIO.input(self.dt) == 0: self.direction = -1
    else: self.direction = 1
    self.set_value(self.value + self.direction)
    print(F"incrementing {self.name} by {self.direction}. {self.value}")
    #sleep(0.3)

  def dt_callback(self,channel):
    #self.pin_states("dt")
    #sleep(0.3)
    pass

  def sw_callback(self,channel):
    print(F"Pushed button {self.name}")
    #sleep(0.3)

  def set_value(self,value): self.value = min(max(value,min(self._values)),max(self._values))
  def get_value(self): return self.value 
  
  def cleanup(self): GPIO.cleanup()
     
y = knob((23,22,24),"year",range(1965,1996),1979)
m = knob((18,27,17),"month",range(1,13),11)
d = knob((15,14,4),"day",range(1,32),2)

_ = [x.setup() for x in [y,m,d]]

class date:
  def __init__(self,y,m,d):
  maxd = [31,29,31,30,31,30,31,31,30,31,30,31] ## max days in a month.
  if d.value > maxd[m-1]: d.set_value(maxd[m-1])
  try:
    self.date = datetime.date(y.value,m.value,d.value)
  except ValueError:
    d.set_value(d.value-1)
    self.date = datetime.date(y.value,m.value,d.value)
  
