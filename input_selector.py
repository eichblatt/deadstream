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


y = retry_call(RotaryEncoder, config.year_pins[1], config.year_pins[0],max_steps = 0,threshold_steps = (0,99))
m = retry_call(RotaryEncoder, config.month_pins[1], config.month_pins[0],max_steps = 0,threshold_steps = (0,127))
d = retry_call(RotaryEncoder, config.day_pins[1], config.day_pins[0],max_steps = 0,threshold_steps = (0,127))
#y.steps = 1979-1965; m.steps = 11; d.steps = 2;
y.when_rotated = lambda x: twist_knob(screen_event, y, "year")
m.when_rotated = lambda x: twist_knob(screen_event, m, "month")
d.when_rotated = lambda x: twist_knob(screen_event, d, "day")
y_button = retry_call(Button, config.year_pins[2])
m_button = retry_call(Button, config.month_pins[2])
d_button = retry_call(Button, config.day_pins[2])
select = retry_call(Button, config.select_pin,hold_time = 2,hold_repeat = True)
play_pause = retry_call(Button, config.play_pause_pin,hold_time = 5)
ffwd = retry_call(Button, config.ffwd_pin,hold_time = 1,hold_repeat = True)
rewind = retry_call(Button, config.rewind_pin,hold_repeat = True)
stop = retry_call(Button, config.stop_pin)


play_pause.when_pressed = lambda x: print (F"pressing {x}")
play_pause.when_held = lambda x: print ("nyi")

select.when_pressed = lambda x: select_button(x)
stop.when_pressed = lambda x: stop_button(x)
select.when_held = lambda x: print (F"long pressing {x}")

ffwd.when_released = lambda x: print (F"releasing {x}")
ffwd.when_held = lambda x: print (F"long pressing {x}")

select_event = Event()
done_event = Event()
screen_event = Event()


scr = controls.screen(upside_down=True)
scr.clear()

def select_chars(scr,y,message,y_origin=30):
  scr.clear()
  printable_chars = string.printable
  selected = ''
  y.steps = 0 
  screen_width = 15
  update_now = scr.update_now
  scr.update_now = False
  done_event.clear()
  select_event.clear()
  x_origin = 0
  selection_bbox = controls.Bbox(0,y_origin,160,y_origin+29)

  scr.show_text(message,loc=(x_origin,0),font=scr.smallfont,force=True)

  while not done_event.is_set(): 
    while not select_event.is_set() and not done_event.is_set(): 
      scr.clear_area(selection_bbox,force=False)
      #scr.draw.rectangle((0,0,scr.width,scr.height),outline=0,fill=(0,0,0))
      x_loc = x_origin
      y_loc = y_origin

      text = printable_chars[max(0,y.steps-int(screen_width/2)):y.steps] 
      (text_width,text_height)= scr.smallfont.getsize(text)
      scr.show_text(text,loc=(x_loc,y_loc),font=scr.smallfont,force=False)
      x_loc = x_loc + text_width
      
      text = printable_chars[y.steps] 
      (text_width,text_height)= scr.smallfont.getsize(text)
      scr.show_text(text,loc=(x_loc,y_loc),font=scr.smallfont,color=(0,0,255),force=False)
      x_loc = x_loc + text_width

      text = printable_chars[y.steps+1:min(y.steps+screen_width,len(printable_chars))] 
      (text_width,text_height)= scr.smallfont.getsize(text)
      scr.show_text(text,loc=(x_loc,y_loc),font=scr.smallfont,force=True)
      x_loc = x_loc + text_width
      
      sleep(0.1)
    select_event.clear()
    if done_event.is_set(): continue
    selected = selected + printable_chars[y.steps] 
    scr.show_text(F"So far: \n{selected}",loc=(x_origin,y_origin+22),color=(255,255,255),font=scr.smallfont,force=True)
 
  print(F"word selected {selected}")
  scr.update_now = update_now
  return selected

wifi = select_chars(scr,y,"Input WiFi Name\nUse year knob and select\nstop button to end",y_origin=65)
passkey = select_chars(scr,y,"Input Passkey\nUse year knob and select\nstop button to end",y_origin=65)

scr.clear()
scr.show_text(F"wifi: {wifi}\npasskey:{passkey}",loc=(0,0),color=(255,255,255),font=scr.smallfont,force=True)

