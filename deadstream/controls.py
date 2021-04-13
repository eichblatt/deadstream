#!/usr/bin/python3
from RPi import GPIO
from time import sleep
import datetime
import logging
import digitalio
import board
import config
import adafruit_rgb_display.st7735 as st7735
from adafruit_rgb_display import color565
from PIL import Image, ImageDraw, ImageFont
import pkg_resources

logging.basicConfig(format='%(levelname)s:%(message)s', level=logging.DEBUG)

class button:
  def __init__(self,pin,name,bouncetime=10):
    self.pin = pin
    self.name = name
    self.bouncetime = bouncetime
    self.is_setup = False

  def __str__(self):
    return self.__repr__()

  def __repr__(self):
    return F"{self.name}: pin:{self.pin}"

  def add_callback(self,pin,edge_type,cb,maxtries=3):
    itries = 0
    while itries < maxtries:
      itries += 1
      try:
        GPIO.add_event_detect(pin,edge_type, callback = cb, bouncetime = self.bouncetime) 
        return
      except:
        logging.warn(F"Retrying event_detection callback on pin {pin}")
    logging.warn(F"Failed to set event_detection callback on pin {pin}")

  def setup(self):
    if self.pin == None: return
    if self.is_setup: return
    GPIO.setmode(GPIO.BCM)
    GPIO.setup(self.pin,GPIO.IN,pull_up_down=GPIO.PUD_DOWN)
    self.add_callback(self.pin,GPIO.RISING,self.callback)
    self.is_setup = True
    return None 

  def show_pin_state(self,msg): 
    logging.debug (F"{self.name} {msg}: State of pin:{GPIO.input(self.pin)}")
    return 
 
  def callback(self,channel):
    if GPIO.input(self.pin) == 0: return
    logging.debug(F"Pushed button {self.name}")
    if self.name == 'select':
       config.SELECT_DATE = True 
       logging.debug(F"Setting SELECT_DATE to {config.SELECT_DATE}")
    if self.name == 'ffwd':
       config.FSEEK = False
       sleep(0.5)
       while GPIO.input(self.pin) == 1: # button is still being pressed
           logging.debug(F"Setting FFWD to {config.FFWD}, FSEEK is {config.FSEEK}")
           config.FSEEK = True
           sleep(0.1)
       if not config.FSEEK: 
           logging.debug(F"Setting FFWD to {config.FFWD}, FSEEK is {config.FSEEK}")
           config.FFWD = True
       config.FSEEK = False
    if self.name == 'rewind':
       config.RSEEK = False
       sleep(0.5)
       while GPIO.input(self.pin) == 1: # button is still being pressed
           logging.debug(F"Setting REWIND to {config.REWIND}, RSEEK is {config.RSEEK}")
           config.RSEEK = True
           sleep(0.1)
       if not config.RSEEK: 
           logging.debug(F"Setting REWIND to {config.REWIND}, RSEEK is {config.RSEEK}")
           config.REWIND = True
    if self.name == 'play_pause':
       if config.PLAY_STATE in [config.READY, config.PAUSED, config.STOPPED]: config.PLAY_STATE = config.PLAYING  # play if not playing
       elif config.PLAY_STATE == config.PLAYING: config.PLAY_STATE = config.PAUSED   # Pause if playing
       logging.debug(F"Setting PLAY_STATE to {config.PLAY_STATES[config.PLAY_STATE]}")
    if self.name == 'stop':
       if config.PLAY_STATE in [config.PLAYING, config.PAUSED]: config.PLAY_STATE = config.STOPPED  # stop playing or pausing
       logging.debug(F"Setting PLAY_STATE to {config.PLAY_STATES[config.PLAY_STATE]}")

  def cleanup(self): 
    GPIO.cleanup()

 
class knob:
  def __init__(self,pins,name,values,init=None,bouncetime=100):
    self.cl, self.dt, self.sw = pins
    self.name = name
    self._values = values 
    self.value = min(values) if init == None else init
    self.bouncetime = bouncetime
    self.is_setup = False

  def __str__(self):
    return self.__repr__()

  def __repr__(self):
    return F"{self.name}: pins cl:{self.cl}, dt:{self.dt}, sw:{self.sw}. Value: {self.value}"
 
  def add_callback(self,pin,edge_type,cb,maxtries=3):
    itries = 0
    while itries < maxtries:
      itries += 1
      try:
        GPIO.add_event_detect(pin,edge_type, callback = cb, bouncetime = self.bouncetime) 
        return
      except:
        logging.warn(F"Retrying event_detection callback on pin {pin}")
    logging.warn(F"Failed to set event_detection callback on pin {pin}")
    raise

  def setup(self):
    if self.is_setup: return
    GPIO.setmode(GPIO.BCM)
    _ = [GPIO.setup(x,GPIO.IN,pull_up_down=GPIO.PUD_DOWN) for x in [self.cl,self.dt,self.sw]]
    try:
      self.add_callback(self.sw,GPIO.RISING,self.sw_callback)
      self.add_callback(self.dt,GPIO.FALLING,self.dt_callback)
      self.add_callback(self.cl,GPIO.FALLING,self.cl_callback)
      self.is_setup = True
    except: raise
    return None 

  def show_pin_states(self,msg): 
    logging.debug (F"{self.name} {msg}: State of cl:{GPIO.input(self.cl)}, dt:{GPIO.input(self.dt)}, sw:{GPIO.input(self.sw)}")
    return 
 
  def cl_callback(self,channel):
    self.show_pin_states("cl")
    dt = GPIO.input(self.dt) 
    if dt == 1: 
      self.set_value(self.value + 1)
      logging.debug (F" +++ increasing {self.name}.  {self.value}")
    return

  def dt_callback(self,channel):
    self.show_pin_states("dt")
    cl = GPIO.input(self.cl)
    if cl == 1: 
      self.set_value(self.value -1)
      logging.debug (F" --- decreasing {self.name}. {self.value}")
    return

  def sw_callback(self,channel):
    logging.debug(F"Pushed button {self.name}")
    if self.name == 'year':
      config.TIH = True 
      logging.debug(F"Setting TIH to {config.TIH}")
    if self.name == 'month':
      if config.PLAY_STATE in [config.READY, config.PAUSED, config.STOPPED]: config.PLAY_STATE = config.PLAYING  # play if not playing
      elif config.PLAY_STATE == config.PLAYING: config.PLAY_STATE = config.PAUSED   # Pause if playing
      logging.debug(F"Setting PLAY_STATE to {config.PLAY_STATES[config.PLAY_STATE]}")
    if self.name == 'day':
      config.NEXT_DATE = True
      logging.debug(F"Setting NEXT_DATE to {config.NEXT_DATE}")
     #sleep(0.3)

  def set_value(self,value): 
    self.value = min(max(value,min(self._values)),max(self._values))
  def get_value(self): 
    return self.value 

  def cleanup(self): 
    GPIO.cleanup()

class date_knob_reader:
  def __init__(self,y,m,d,archive=None):
    self.date = None
    self.archive = archive
    self.update(y,m,d)
 
  def __str__(self):  
    return self.__repr__()

  def __repr__(self):
    avail = "Tape Available" if self.tape_available() else ""
    return F'Date Knob Says: {self.date.strftime("%Y-%m-%d")}. {avail}'

  def update(self,y,m,d):
    maxd = [31,29,31,30,31,30,31,31,30,31,30,31] ## max days in a month.
    if d.value > maxd[m.value-1]: d.set_value(maxd[m.value-1])
    try:
      self.date = datetime.date(y.value,m.value,d.value)
    except ValueError:
      d.set_value(d.value-1)
      self.date = datetime.date(y.value,m.value,d.value)
 
  def fmtdate(self):
    if self.date == None: return None
    return self.date.strftime('%Y-%m-%d')

  def venue(self):
    if self.tape_available: 
      t = self.archive.best_tape(self.fmtdate())
      return t.venue()
    return ""

  def tape_available(self):
    if self.archive == None: return False
    return self.fmtdate() in self.archive.dates   

  def next_date(self):
    if self.archive == None: return None
    for d in self.archive.dates:
      if d>self.fmtdate(): return datetime.datetime.strptime(d,'%Y-%m-%d').date()
    return self.date
      

class seven_segment:
  def __init__(self,disp,loc,size,thickness=3,color=(0,0,255),bgcolor=(0,0,0)):
    self.disp = disp
    self.x,self.y = loc
    self.w,self.h = size
    self.thickness = thickness
    self.color = color565(color)
    self.bgcolor = color565(bgcolor)
    
    self.segments = [(0,0,0), (0,.5,0),(0,1,0),(0,0,1),(1,0,1),(0,.5,1),(1,.5,1)]  # x location, y location, vertical?
    self.digits = [[0,2,3,4,5,6],[4,6],[0,1,2,3,6],[0,1,2,4,6],[1,4,5,6],[0,1,2,4,5],[0,1,2,3,4,5],[2,6,4],[0,1,2,3,4,5,6],[1,2,4,5,6],[1],[]] # which segments on.
    
  def draw_background(self):
    self.disp.fill_rectangle(self.y,self.x,self.h,self.w,self.bgcolor)  # background
    #[self.draw_segment(x,True) for x in self.segments]

  def draw_segment(self,seg,bgcolor=False):
    color = self.color if not bgcolor else self.bgcolor
    if seg[2]: # vertical
      line_width = self.thickness
      line_height = divmod(self.h,2)[0]
    else: 
      line_width = self.w
      line_height = self.thickness
    x,y = (self.x + int(seg[0]*self.w - seg[0]*self.thickness),self.y + int(seg[1]*self.h - seg[1]*self.thickness))
    self.disp.fill_rectangle(y,x,line_height,line_width,color)
    logging.debug(F"drawing rectangle {y},{x},{line_height},{line_width},color {color}")
 
  def draw(self,digit):
    if digit == '-': digit = 10
    if digit == ' ': digit = 11
    if type(digit) == str: digit = int(digit)
    if not (digit>=0) and (digit<=11): raise ValueError
    self.draw_background()
    pattern = [self.segments[x] for x in self.digits[digit]] 
    [self.draw_segment(x) for x in pattern]

class Bbox:
  def __init__(self,x0,y0,x1,y1):
    self.corners = (x0,y0,x1,y1)
    self.x0,self.y0,self.x1,self.y1 = self.corners
  
  def __str__(self):
    return self.__repr__()

  def __repr__(self):
    return F"Bbox: x0 {self.x0},y0 {self.y0},x1 {self.x1},y1 {self.y1}"

  def width(self): return self.x1-self.x0
  def height(self): return self.y1-self.y0
  def origin(self): return (self.x0,self.y0)
  def topright(self): return (self.x1,self.y1)
  def size(self): return (int(self.height()),int(self.width()))
  def center(self): return (int((self.x0+self.x1)/2),int((self.y0+self.y1)/2))
  def shift(self,d): return Bbox(self.x0-d.x0,self.y0-d.y0,self.x1-d.x1,self.y1-d.y1)

 
class screen:
  def __init__(self):
    cs_pin= digitalio.DigitalInOut(board.CE0)
    dc_pin= digitalio.DigitalInOut(board.D24)
    reset_pin= digitalio.DigitalInOut(board.D25)
    #BAUDRATE= 2400000
    BAUDRATE= 40000000
    spi= board.SPI()
    #self.disp= st7735.ST7735R(spi,rotation=270,cs=cs_pin,dc=dc_pin,rst=reset_pin,baudrate=BAUDRATE)
    self.disp= st7735.ST7735R(spi,rotation=90,cs=cs_pin,dc=dc_pin,rst=reset_pin,baudrate=BAUDRATE)
   
    self.bgcolor = color565(0,0,0)
    # --- swap width/height, if
    if self.disp.rotation % 180 == 90: height,width= self.disp.width,self.disp.height
    else: width,height= self.disp.width,self.disp.height
    self.width, self.height = width, height
    logging.debug(F" ---> disp {self.disp.width},{self.disp.height}")
    self.boldfont = ImageFont.truetype(pkg_resources.resource_filename("deadstream", "DejaVuSansMono-Bold.ttf"), 33)
    self.boldsmall = ImageFont.truetype(pkg_resources.resource_filename("deadstream", "DejaVuSansMono-Bold.ttf"), 22)
    self.font = ImageFont.truetype(pkg_resources.resource_filename("deadstream", "ariallgt.ttf"), 30)
    self.smallfont = ImageFont.truetype(pkg_resources.resource_filename("deadstream", "ariallgt.ttf"), 20)
    self.oldfont = ImageFont.truetype(pkg_resources.resource_filename("deadstream", "FreeMono.ttf"), 20)
    self.largefont = ImageFont.truetype(pkg_resources.resource_filename("deadstream", "FreeMono.ttf"), 30)
    self.hugefont = ImageFont.truetype(pkg_resources.resource_filename("deadstream", "FreeMono.ttf"), 40)

    self.image = Image.new("RGB",(width,height))
    self.draw = ImageDraw.Draw(self.image)       # draw using this object. Display image when complete.

    self.staged_date = None
    self.selected_date = None

    self.staged_date_bbox = Bbox(0,0,160,31)
    self.selected_date_bbox = Bbox(0,100,160,128)
    self.venue_bbox = Bbox(0,31,160,56)
    self.track1_bbox = Bbox(0,55,160,77)
    self.track2_bbox = Bbox(0,78,160,100)
    self.playstate_bbox = Bbox(130,100,160,128)



  def refresh(self):
    self.disp.image(self.image)

  def clear_area(self,bbox,now=False):
    self.draw.rectangle(bbox.corners,outline=0,fill=(0,0,0))
    if now: self.refresh()
 
  def clear(self):
    self.draw.rectangle((0,0,self.width,self.height),outline=0,fill=(0,0,0))
    self.refresh()

  def rectangle(self,loc,size,color=(0,0,255)):
    x,y = loc; w,h = size;
    self.disp.fill_rectangle(x,y,w,h,color565(color))

  def show_text(self,text,loc=(0,0),font=None,color=(255,255,255),stroke_width=0,now=True):
    if font==None: font = self.font
    (text_width,text_height)= font.getsize(text)
    logging.debug(F' show_text {text}. text_size {text_height},{text_width}')
    self.draw.text(loc, text, font=font,stroke_width=stroke_width,fill=color)
    if now: self.refresh()

  def scroll_venue(self,color=(0,255,255),stroke_width=0,inc=15):
    """ This function can be called in a thread from the main. 
        eg. 
        venue_thread = threading.Thread(target=s.scroll_venue,name="venue_scroll",args=(),kwargs={'stroke_width':0,'inc':10})
        venue_thread.start()
        s.venue_name ="Fillmore West, San Francisco, CA"

        It works, but eats a lot of cycles. I'm not ready to go in this direction yet
    """   
    bbox = self.venue_bbox
    font = self.boldsmall
    self.clear_area(bbox)
    while True:
      text = self.venue_name
      (text_width,text_height)= font.getsize(text)
      excess = text_width - bbox.width()
      self.draw.text(bbox.origin(),text,font=font,fill=color,stroke_width=stroke_width)
      if excess > 0:
         self.show_text(text,bbox.origin(),font=font,color=color,stroke_width=stroke_width)
         sleep(2)
         for i in range(int(excess/inc)+2):
           #logging.debug(F"scrolling excess {excess}, inc: {inc}, i:{i}")
           if self.venue_name != text: break
           #sleep(0.005)
           self.clear_area(bbox)
           self.show_text(text,bbox.shift(Bbox(inc*i,0,0,0)).origin(),font=font,color=color,stroke_width=stroke_width)
         sleep(1)
         self.clear_area(bbox)

  def show_venue(self,text,color=(0,255,255),now=True):
    self.clear_area(self.venue_bbox)
    self.show_text(text,self.venue_bbox.origin(),font=self.boldsmall,color=color,now=now)

  def show_date(self,date,loc=(0,96),size=16,separation=4,color=(0,200,255),stack=False,tape=False):
    x0,y0 = loc; segwidth = size; segheight = 2*size; 
    size = (segwidth,segheight)
    ss = []
    monthlist = [c for c in str(date.month).rjust(2)]
    dash = ['-']
    daylist = [c for c in str(date.day).rjust(2)]

    if stack:
      y1 = y0+segheight+separation
      ss = [seven_segment(self.disp,(x0 + i*(segwidth + separation),y1),size,color=color) for i in range(5)]
      ss = ss + [seven_segment(self.disp,(x0 + i*(segwidth + separation),y0),size,color=color) for i in range(4)]
      yearlist = [c for c in str(date.year).rjust(4)]
      for i,v in enumerate(monthlist + dash + daylist + yearlist): ss[i].draw(v)
    else:
      ss = [seven_segment(self.disp,(x0 + i*(segwidth + separation),y0),size,color=color) for i in range(8)]
      yearlist = [c for c in str(divmod(date.year,100)[1]).rjust(2)]
      for i,v in enumerate(monthlist + dash + daylist + dash + yearlist): ss[i].draw(v)

    if tape: self.disp.fill_rectangle(0,0,30,30,color565(255,255,255))  
    else: self.disp.fill_rectangle(0,0,30,30,self.bgcolor)  

  def show_staged_date(self,date,color=(0,255,255),now=True):
    if date == self.staged_date: return
    self.clear_area(self.staged_date_bbox)
    month = str(date.month).rjust(2)
    day = str(date.day).rjust(2)
    year = str(divmod(date.year,100)[1]).rjust(2)
    text = month + '-' + day + '-' + year
    logging.debug (F"staged date string {text}")
    self.show_text(text,self.staged_date_bbox.origin(),self.boldfont,color=color,now=now)
    self.staged_date = date

  def show_selected_date(self,date,color=(255,255,255),now=True):
    if date == self.selected_date: return
    self.clear_area(self.selected_date_bbox)
    month = str(date.month).rjust(2)
    day = str(date.day).rjust(2)
    year = str(date.year).rjust(4)
    text = month + '-' + day + '-' + year
    self.show_text(text,self.selected_date_bbox.origin(),self.boldsmall,color=color,now=now)
    self.selected_date = date

  def show_track(self,text,trackpos,color=(120,0,255)):
    bbox = self.track1_bbox if trackpos == 0 else self.track2_bbox
    self.clear_area(bbox)
    self.draw.text(bbox.origin(), text, font=self.smallfont,fill=color,stroke_width=1);
    self.refresh()

  def show_playstate(self,color=(0,100,255)):
    logging.debug("showing playstate {config.PLAY_STATES[config.PLAY_STATE]}")
    bbox = self.playstate_bbox
    self.clear_area(bbox)
    center = bbox.center()
    size   = bbox.size()
    if config.PLAY_STATES[config.PLAY_STATE] == 'Playing':  
       self.draw.regular_polygon((center,10),3,rotation=30,fill=color)
    elif config.PLAY_STATES[config.PLAY_STATE] == 'Paused' :  
       self.draw.line([(bbox.x0+10,bbox.y0+4),(bbox.x0+10,bbox.y0+20)],width=4,fill=color)
       self.draw.line([(bbox.x0+20,bbox.y0+4),(bbox.x0+20,bbox.y0+20)],width=4,fill=color)
    elif config.PLAY_STATES[config.PLAY_STATE] == 'Stopped' :  
       self.draw.regular_polygon((center,10),4,rotation=0,fill=color)
    elif config.PLAY_STATES[config.PLAY_STATE] in ['Init','Ready'] :  
       pass
    self.refresh()
