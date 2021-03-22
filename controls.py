#!/usr/bin/python3
from RPi import GPIO
from time import sleep
import datetime
import logging

logging.basicConfig(format='%(levelname)s:%(message)s', level=logging.INFO)

class knob:
  def __init__(self,pins,name,values,init=None,bouncetime=300):
    self.cl, self.dt, self.sw = pins
    self.name = name
    self._values = values 
    self.value = min(values) if init == None else init
    self.bouncetime = bouncetime

  def __str__(self):
    return self.__repr__()

  def __repr__(self):
    return F"{self.name}: pins cl:{self.cl}, dt:{self.dt}, sw:{self.sw}. Value: {self.value}"
 
  def setup(self):
    GPIO.setmode(GPIO.BCM)
    _ = [GPIO.setup(x,GPIO.IN,pull_up_down=GPIO.PUD_DOWN) for x in [self.cl,self.dt,self.sw]]
    GPIO.add_event_detect(self.sw,GPIO.BOTH, callback = self.sw_callback, bouncetime = self.bouncetime) 
    GPIO.add_event_detect(self.dt,GPIO.FALLING, callback = self.dt_callback, bouncetime = self.bouncetime) 
    GPIO.add_event_detect(self.cl,GPIO.FALLING, callback = self.cl_callback, bouncetime = self.bouncetime) 
    return None 

  def show_pin_states(self,msg): 
    logging.debug (F"{self.name} {msg}: State of cl:{GPIO.input(self.cl)}, dt:{GPIO.input(self.dt)}, sw:{GPIO.input(self.sw)}")
    return 
 
  def cl_callback(self,channel):
    self.show_pin_states("cl")
    dt0 = GPIO.input(self.dt) 
    sleep(0.005)
    dt1 = GPIO.input(self.dt)
    if (dt0 == 1) and (dt1 == 1): 
      self.set_value(self.value + 1)
      logging.debug (F"incrementing {self.name}.  {self.value}")
    return

  def dt_callback(self,channel):
    self.show_pin_states("dt")
    cl0 = GPIO.input(self.cl)
    sleep(0.005)
    cl1 = GPIO.input(self.cl)
    if (cl0 == 1) and (cl1 == 1): 
      self.set_value(self.value -1)
      logging.debug (F"DEcrementing {self.name}. {self.value}")
    return

  def sw_callback(self,channel):
    print(F"Pushed button {self.name}")
    #sleep(0.3)

  def set_value(self,value): 
    self.value = min(max(value,min(self._values)),max(self._values))
  def get_value(self): 
    return self.value 
  def cleanup(self): 
    GPIO.cleanup()

class date_knob_reader:
  def __init__(self,y,m,d):
    maxd = [31,29,31,30,31,30,31,31,30,31,30,31] ## max days in a month.
    if d.value > maxd[m.value-1]: d.set_value(maxd[m.value-1])
    self.date = None
    try:
      self.date = datetime.date(y.value,m.value,d.value)
    except ValueError:
      d.set_value(d.value-1)
      self.date = datetime.date(y.value,m.value,d.value)
 
  def __str__(self):  
    return self.__repr__()

  def __repr__(self):
      return F'Date Knob Says: {self.date.strftime("%Y-%m-%d")}'

  def tape_available(self):
      return None

y = knob((13,19,26),"year",range(1965,1996),1979)
m = knob((16,20,21),"month",range(1,13),11)
d = knob((12,5,6)  ,"day",range(1,32),2,bouncetime=100)

_ = [x.setup() for x in [y,m,d]]

staged_date = date_knob_reader(y,m,d)
print (staged_date)
d0 = staged_date.date

while True:
  staged_date = date_knob_reader(y,m,d)
  if staged_date.date != d0: 
    print (staged_date)
    d0 = staged_date.date
  sleep(.01)
