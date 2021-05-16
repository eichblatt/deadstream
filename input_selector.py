from timemachine import controls 
from timemachine import config
from time import sleep
from threading import Event
from typing import Callable
import datetime,string
import board
import digitalio
from adafruit_rgb_display.st7735 import ST7735R
from adafruit_rgb_display import color565
from gpiozero import RotaryEncoder, Button
from tenacity import retry
from tenacity.stop import stop_after_delay
from PIL import Image, ImageDraw, ImageFont
import pkg_resources
import subprocess,re

controls.logger.setLevel(50) 

@retry(stop=stop_after_delay(10))
def retry_call(callable: Callable, *args, **kwargs):
    """Retry a call."""
    return callable(*args, **kwargs)

def twist_knob(screen_event: Event, knob: RotaryEncoder, label):
    if knob.is_active:
      print(f"Knob {label} steps={knob.steps} value={knob.value}")
    else:
      if knob.steps<knob.threshold_steps[0]: knob.steps = knob.threshold_steps[0]
      if knob.steps>knob.threshold_steps[1]: knob.steps = knob.threshold_steps[1]
      print(f"Knob {label} is inactive")
    screen_event.set()

def select_button(button):
   print ("pressing select")
   select_event.set()

def stop_button(button):
   print ("pressing stop")
   done_event.set()


y = retry_call(RotaryEncoder, config.year_pins[1], config.year_pins[0],max_steps = 0,threshold_steps = (-1,93))
y.when_rotated = lambda x: twist_knob(screen_event, y, "year")
y_button = retry_call(Button, config.year_pins[2])
select = retry_call(Button, config.select_pin,hold_time = 2,hold_repeat = True)
stop = retry_call(Button, config.stop_pin)

select.when_pressed = lambda x: select_button(x)
stop.when_pressed = lambda x: stop_button(x)

select_event = Event()
done_event = Event()
screen_event = Event()

scr = controls.screen(upside_down=False)
scr.clear()

def select_option(scr,y,message,choices):
  scr.clear()
  selected = None
  y.steps = 0 
  screen_height = 5
  update_now = scr.update_now
  scr.update_now = False
  done_event.clear()
  select_event.clear()
  step = divmod(y.steps,len(choices))[1]

  scr.show_text(message,loc=(0,0),font=scr.smallfont,color=(0,255,255),force=True)
  (text_width,text_height)= scr.smallfont.getsize(message)

  y_origin = text_height*(1+message.count('\n'))
  selection_bbox = controls.Bbox(0,y_origin,160,128)

  while not select_event.is_set():
      scr.clear_area(selection_bbox,force=False)
      x_loc = 0
      y_loc = y_origin
      step = divmod(y.steps,len(choices))[1]

      text = '\n'.join(choices[max(0,step-int(screen_height/2)):step])
      (text_width,text_height)= scr.oldfont.getsize(text)
      scr.show_text(text,loc=(x_loc,y_loc),font=scr.oldfont,force=False)
      y_loc = y_loc + text_height*(1+text.count('\n'))
      
      text = choices[step] 
      (text_width,text_height)= scr.oldfont.getsize(text)
      scr.show_text(text,loc=(x_loc,y_loc),font=scr.oldfont,color=(0,0,255),force=False)
      y_loc = y_loc + text_height

      text = '\n'.join(choices[step+1:min(step+screen_height,len(choices))])
      (text_width,text_height)= scr.oldfont.getsize(text)
      scr.show_text(text,loc=(x_loc,y_loc),font=scr.oldfont,force=True)
      
      sleep(0.01)
  select_event.clear()
  selected = choices[step] 
  #scr.show_text(F"So far: \n{selected}",loc=selected_bbox.origin(),color=(255,255,255),font=scr.smallfont,force=True)
 
  print(F"word selected {selected}")
  scr.update_now = update_now
  return selected


def select_chars(scr,y,message):
  scr.clear()
  printable_chars = string.printable
  selected = ''
  y.steps = 0 
  screen_width = 12
  update_now = scr.update_now
  scr.update_now = False
  done_event.clear()
  select_event.clear()

  scr.show_text(message,loc=(0,0),font=scr.smallfont,color=(0,255,255),force=True)
  (text_width,text_height)= scr.smallfont.getsize(message)

  y_origin = text_height*(1+message.count('\n'))
  selection_bbox = controls.Bbox(0,y_origin,160,y_origin+22)
  selected_bbox = controls.Bbox(0,y_origin+21,160,128)

  while not done_event.is_set(): 
    while not select_event.is_set() and not done_event.is_set(): 
      scr.clear_area(selection_bbox,force=False)
      #scr.draw.rectangle((0,0,scr.width,scr.height),outline=0,fill=(0,0,0))
      x_loc = 0
      y_loc = y_origin

      text = 'DEL' 
      (text_width,text_height)= scr.oldfont.getsize(text)
      if y.steps<0: 
        scr.show_text(text,loc=(x_loc,y_loc),font=scr.oldfont,color=(0,0,255),force=False)
        scr.show_text(printable_chars[:screen_width],loc=(x_loc + text_width,y_loc),font=scr.oldfont,force=True)
        continue
      scr.show_text(text,loc=(x_loc,y_loc),font=scr.oldfont,force=False)
      x_loc = x_loc + text_width

      text = printable_chars[max(0,y.steps-int(screen_width/2)):y.steps] 
      (text_width,text_height)= scr.oldfont.getsize(text)
      scr.show_text(text,loc=(x_loc,y_loc),font=scr.oldfont,force=False)
      x_loc = x_loc + text_width
      
      text = printable_chars[y.steps] 
      (text_width,text_height)= scr.oldfont.getsize(text)
      scr.show_text(text,loc=(x_loc,y_loc),font=scr.oldfont,color=(0,0,255),force=False)
      x_loc = x_loc + text_width

      text = printable_chars[y.steps+1:min(y.steps+screen_width,len(printable_chars))] 
      (text_width,text_height)= scr.oldfont.getsize(text)
      scr.show_text(text,loc=(x_loc,y_loc),font=scr.oldfont,force=True)
      x_loc = x_loc + text_width
      
      sleep(0.1)
    select_event.clear()
    if done_event.is_set(): continue
    if y.steps<0:
      selected = selected[:-1]
      scr.clear_area(selected_bbox,force=False)
    else:
      selected = selected + printable_chars[y.steps] 
    scr.show_text(F"So far: \n{selected}",loc=selected_bbox.origin(),color=(255,255,255),font=scr.smallfont,force=True)
 
  print(F"word selected {selected}")
  scr.update_now = update_now
  return selected

def get_wifi_choices():
  cmd = "sudo iwlist wlan0 scan | grep ESSID:"
  raw = subprocess.check_output(cmd,shell=True)
  choices = [x.lstrip().replace('ESSID:','').replace('"','') for x in raw.decode().split('\n')]
  [x for x in choices if bool(re.search('[a-z,0-9]',x,re.IGNORECASE))]
  return choices

wifi_choices = get_wifi_choices()

wifi = select_option(scr,y,"Select Wifi Name",wifi_choices)
#wifi = select_chars(scr,y,"Input Wifi Name\nTurn Year then Select\nPress Stop to end")
passkey = select_chars(scr,y,"Input Passkey\nTurn Year then Select\nPress Stop to end")

scr.clear()
scr.show_text(F"wifi: {wifi}\npasskey:{passkey}",loc=(0,0),color=(255,255,255),font=scr.smallfont,force=True)

