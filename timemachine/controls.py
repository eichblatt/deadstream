#!/usr/bin/python3
from RPi import GPIO
from time import sleep
import datetime
import logging
import digitalio
import board
from  . import config
import adafruit_rgb_display.st7735 as st7735
from adafruit_rgb_display import color565
from PIL import Image, ImageDraw, ImageFont
import pkg_resources

logging.basicConfig(format='%(asctime)s.%(msecs)03d %(levelname)s: %(name)s %(message)s', level=logging.INFO,datefmt='%Y-%m-%d %H:%M:%S')
logger = logging.getLogger(__name__)

class button:
  def __init__(self,pin,name,pull_up=False,bouncetime=300):
    self.pin = pin
    self.name = name
    self.bouncetime = bouncetime
    self.pull_up = True if self.pin in [2,3] else pull_up
    self.is_setup = False
    self.active = False

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
        logger.warn(F"Retrying event_detection callback on pin {pin}")
    logger.warn(F"Failed to set event_detection callback on pin {pin}")

  def setup(self):
    if self.pin == None: return
    if self.is_setup: return
    GPIO.setmode(GPIO.BCM)
    if self.pull_up: # These pins are pulled up.
      GPIO.setup(self.pin,GPIO.IN,pull_up_down=GPIO.PUD_DOWN)
      self.add_callback(self.pin,GPIO.BOTH,self.push)
    else:
      GPIO.setup(self.pin,GPIO.IN,pull_up_down=GPIO.PUD_DOWN)
      self.add_callback(self.pin,GPIO.RISING,self.push)

    self.is_setup = True
    return None 

  def push(self,channel):
    logger.debug(F"Pushed button {self.name}. -- {GPIO.input(self.pin)}")
    nullval = 0 if not self.pull_up else 1
    if GPIO.input(self.pin) == nullval: return
    self.press = True
    sleep(0.5)
    if GPIO.input(self.pin) == nullval: 
      self.active = True
      self.longpress = False
    while GPIO.input(self.pin) != nullval: 
      logger.debug(F"Longpress of button {self.name}. -- {GPIO.input(self.pin)}")
      self.active = True
      self.press = False
      self.longpress = True
      sleep(0.1)
    return

  def cleanup(self): 
    GPIO.cleanup()

 
class knob:
  def __init__(self,pins,name,values,init=None,bouncetime=50):
    self.cl, self.dt, self.sw = pins
    self.name = name
    self._values = values 
    self.value = min(values) if init == None else init
    self.bouncetime = bouncetime
    self.is_setup = False
    self.in_rotate = False
    self.turn = False
    self.press = False
    self.longpress = False
    self.active = False

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
        logger.warn(F"Retrying event_detection callback on pin {pin}")
    logger.warn(F"Failed to set event_detection callback on pin {pin}")
    raise

  def setup(self):
    if self.is_setup: return
    GPIO.setmode(GPIO.BCM)
    _ = [GPIO.setup(x,GPIO.IN,pull_up_down=GPIO.PUD_DOWN) for x in [self.cl,self.dt,self.sw]]
    try:
      self.add_callback(self.sw,GPIO.RISING,self.push)
      self.add_callback(self.cl,GPIO.FALLING,self.rotate)
      self.is_setup = True
    except: raise
    return None 

  def rotate(self,channel):
    if self.in_rotate: 
      logger.debug (F" Already in rotate for {self.name}")
      return
    self.in_rotate = True
    self.active = True
    vals = [(GPIO.input(self.dt),GPIO.input(self.cl)) for i in range(10)]
    if sum([v[1] for v in vals])>3: 
      logger.debug (F" Noisy click on {self.name}.  {self.value}")
      cl_val = 1
    else: cl_val = 0
    if sum([v[0] for v in vals])>5: dt_val = 1 
    else: dt_val = 0
    if cl_val == 0 and dt_val == 0:
      self.set_value(self.value - 1)
      logger.debug (F" --- decreasing {self.name}.  {self.value}")
    elif cl_val == 0 and dt_val == 1:
      self.set_value(self.value + 1)
      logger.debug (F" +++ increasing {self.name}.  {self.value}")
    self.in_rotate = False
    self.turn = True
    return
 
  def push(self,channel):
    logger.debug(F"Pushed button {self.name}")
    self.active = True
    self.press = True

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
    self.y = y; self.m = m; self.d = d;
    self.update()
 
  def __str__(self):  
    return self.__repr__()

  def __repr__(self):
    avail = "Tape Available" if self.tape_available() else ""
    return F'Date Knob Says: {self.date.strftime("%Y-%m-%d")}. {avail}'

  def update(self):
    maxd = [31,29,31,30,31,30,31,31,30,31,30,31] ## max days in a month.
    if self.d.value > maxd[self.m.value-1]: self.d.set_value(maxd[self.m.value-1])
    try:
      self.date = datetime.date(self.y.value,self.m.value,self.d.value)
    except ValueError:
      self.d.set_value(self.d.value-1)
      self.date = datetime.date(self.y.value,self.m.value,self.d.value)
 
  def fmtdate(self):
    if self.date == None: return None
    return self.date.strftime('%Y-%m-%d')

  def venue(self):
    if self.tape_available(): 
      t = self.archive.best_tape(self.fmtdate())
      return t.venue()
    return ""

  def tape_available(self):
    if self.archive == None: return False
    self.update()
    return self.fmtdate() in self.archive.dates   

  def next_date(self):
    if self.archive == None: return None
    self.update()
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
    logger.debug(F"drawing rectangle {y},{x},{line_height},{line_width},color {color}")
 
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
  def __init__(self,upside_down=False):
    cs_pin= digitalio.DigitalInOut(board.CE0)
    dc_pin= digitalio.DigitalInOut(board.D24)
    reset_pin= digitalio.DigitalInOut(board.D25)
    #BAUDRATE= 2400000
    BAUDRATE= 40000000
    spi= board.SPI()
    rotation_angle = 90 if not upside_down else 270
    self.disp= st7735.ST7735R(spi,rotation=rotation_angle,cs=cs_pin,dc=dc_pin,rst=reset_pin,baudrate=BAUDRATE)
   
    self.bgcolor = color565(0,0,0)
    # --- swap width/height, if
    if self.disp.rotation % 180 == 90: height,width= self.disp.width,self.disp.height
    else: width,height= self.disp.width,self.disp.height
    self.width, self.height = width, height
    logger.debug(F" ---> disp {self.disp.width},{self.disp.height}")
    self.boldfont = ImageFont.truetype(pkg_resources.resource_filename("timemachine", "DejaVuSansMono-Bold.ttf"), 33)
    self.boldsmall = ImageFont.truetype(pkg_resources.resource_filename("timemachine", "DejaVuSansMono-Bold.ttf"), 22)
    self.font = ImageFont.truetype(pkg_resources.resource_filename("timemachine", "ariallgt.ttf"), 30)
    self.smallfont = ImageFont.truetype(pkg_resources.resource_filename("timemachine", "ariallgt.ttf"), 20)
    self.oldfont = ImageFont.truetype(pkg_resources.resource_filename("timemachine", "FreeMono.ttf"), 20)
    self.largefont = ImageFont.truetype(pkg_resources.resource_filename("timemachine", "FreeMono.ttf"), 30)
    self.hugefont = ImageFont.truetype(pkg_resources.resource_filename("timemachine", "FreeMono.ttf"), 40)

    self.image = Image.new("RGB",(width,height))
    self.draw = ImageDraw.Draw(self.image)       # draw using this object. Display image when complete.

    self.staged_date = None
    self.selected_date = None

    self.staged_date_bbox = Bbox(0,0,160,31)
    #self.selected_date_bbox = Bbox(0,100,130,128)
    self.selected_date_bbox = Bbox(0,100,160,128)
    self.venue_bbox = Bbox(0,31,160,56)
    self.track1_bbox = Bbox(0,55,160,77)
    self.track2_bbox = Bbox(0,78,160,100)
    self.playstate_bbox = Bbox(130,100,160,128)
    self.sbd_bbox = Bbox(155,100,160,108)
    self.exp_bbox = Bbox(0,55,160,100)


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
    logger.debug(F' show_text {text}. text_size {text_height},{text_width}')
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
           #logger.debug(F"scrolling excess {excess}, inc: {inc}, i:{i}")
           if self.venue_name != text: break
           #sleep(0.005)
           self.clear_area(bbox)
           self.show_text(text,bbox.shift(Bbox(inc*i,0,0,0)).origin(),font=font,color=color,stroke_width=stroke_width)
         sleep(1)
         self.clear_area(bbox)

  def show_experience(self,text="Press Month to\nExit Experience",color=(255,255,255),now=True):
    self.clear_area(self.exp_bbox)
    self.show_text(text,self.exp_bbox.origin(),font=self.smallfont,color=color,stroke_width=1,now=now)

  def show_venue(self,text,color=(0,255,255),now=True):
    self.clear_area(self.venue_bbox)
    self.show_text(text,self.venue_bbox.origin(),font=self.boldsmall,color=color,now=now)

  def show_staged_date(self,date,color=(0,255,255),now=True):
    if date == self.staged_date: return
    self.clear_area(self.staged_date_bbox)
    month = str(date.month).rjust(2)
    day = str(date.day).rjust(2)
    year = str(divmod(date.year,100)[1]).rjust(2)
    text = month + '-' + day + '-' + year
    logger.debug (F"staged date string {text}")
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

  def show_playstate(self,staged_play=False,color=(0,100,255),sbd=None):
    logger.debug(F"showing playstate {config.PLAY_STATE}")
    bbox = self.playstate_bbox
    self.clear_area(bbox)
    size   = bbox.size()
    if staged_play:
       self.draw.regular_polygon((bbox.center(),10),3,rotation=30,fill=color)
       self.draw.regular_polygon((bbox.center(),8),3,rotation=30,fill=(0,0,0))
       self.refresh()
       return
    if config.PLAY_STATE == config.PLAYING:  
       self.draw.regular_polygon((bbox.center(),10),3,rotation=30,fill=color)
    elif config.PLAY_STATE == config.PAUSED:  
       self.draw.line([(bbox.x0+10,bbox.y0+4),(bbox.x0+10,bbox.y0+20)],width=4,fill=color)
       self.draw.line([(bbox.x0+20,bbox.y0+4),(bbox.x0+20,bbox.y0+20)],width=4,fill=color)
    elif config.PLAY_STATE == config.STOPPED :  
       self.draw.regular_polygon((bbox.center(),10),4,rotation=0,fill=color)
    elif config.PLAY_STATE in [config.INIT,config.READY] :  
       pass
    if sbd: self.show_soundboard(sbd)
    self.refresh()

  def show_soundboard(self,sbd,color=(255,255,255)):
    if not sbd: 
      self.draw.regular_polygon((self.sbd_bbox.center(),3),4,rotation=45,fill=(0,0,0))
      return
    logger.debug("showing soundboard status")
    self.draw.regular_polygon((self.sbd_bbox.center(),3),4,rotation=45,fill=color)

class state:
  def __init__(self,date_reader,player=None):
    self.module_name = 'config'
    self.date_reader = date_reader
    self.player = player
    self.dict = self.get_current()

  def __str__(self):
    return self.__repr__()

  def __repr__(self):
    return F"state is {self.dict}"

  @staticmethod
  def dict_diff(d1,d2): 
    changes = {}
    for k in d2.keys():
        if d1[k] != d2[k]:
          changes[k] = (d1[k],d2[k])
    return changes

  def snap(self): 
    previous = self.dict.copy() 
    current = self.get_current()
    changes = self.dict_diff(previous,current)
    return (changes,previous,current)

  def get_changes(self): 
    previous = self.dict   # do this first!
    current = self.get_current()
    return self.dict_diff(previous,current)

  def set(self,new_state):
   for k in new_state.keys():
      config.__dict__[k] = new_state[k]   # NOTE This directly names config, which I'd like to be a variable.

  def get_current(self): 
    module = globals().get(self.module_name,None)
    self.dict = {}
    if module:
      self.dict = {key: value for key,value in module.__dict__.items() if (not key.startswith('_')) and key.isupper()}
    self.date_reader.update()
    self.dict['DATE_READER'] = self.date_reader.date
    try:
      self.dict['TRACK_NUM'] = self.player._get_property('playlist-pos')
      self.dict['TAPE_ID'] = self.player.tape.identifier
      self.dict['TRACK_TITLE'] = self.player.tape.tracks()[self.dict['TRACK_NUM']].title
      if (self.dict['TRACK_NUM']+1)<len(self.player.playlist):
         next_track = self.dict['TRACK_NUM']+1 
         self.dict['NEXT_TRACK_TITLE'] = self.player.tape.tracks()[next_track].title
      else: self.dict['NEXT_TRACK_TITLE'] = ''
    except: 
      self.dict['TRACK_NUM'] = -1
      self.dict['TAPE_ID'] = ''
      self.dict['TRACK_TITLE'] = ''
      self.dict['NEXT_TRACK_TITLE'] = ''
    self.dict['TRACK_ID'] = self.dict['TAPE_ID']+ "_track_" + str(self.dict['TRACK_NUM'])
    return self.dict


def controlLoop(item_list,callback):
    while True:
      for item in item_list:
          if item.active:
              callback(item) 

"""
        venue_thread = threading.Thread(target=s.scroll_venue,name="venue_scroll",args=(),kwargs={'stroke_width':0,'inc':10})

    if self.name == 'select':   # NOTE I should move this logic to a function, since it's repeated 3 times.
       config.NEXT_TAPE = False
       sleep(0.5)
       while GPIO.input(self.pin) == 1: # button is still being pressed
           logger.debug(F"Setting SELECT_STAGED_DATE to {config.SELECT_STAGED_DATE}, NEXT_TAPE to {config.NEXT_TAPE}")
           config.NEXT_TAPE = True
           sleep(0.1)
       config.NEXT_TAPE = False
       if not config.NEXT_TAPE: 
           logger.debug(F"Setting SELECT_STAGED_DATE to {config.SELECT_STAGED_DATE}, NEXT_TAPE to {config.NEXT_TAPE}")
           config.SELECT_STAGED_DATE = True
           config.PLAY_STATE = config.READY
    if self.name == 'ffwd':
       config.FSEEK = False
       sleep(0.5)
       while GPIO.input(self.pin) == 1: # button is still being pressed
           logger.debug(F"Setting FFWD to {config.FFWD}, FSEEK is {config.FSEEK}")
           config.FSEEK = True
           sleep(0.1)
       if not config.FSEEK: 
           logger.debug(F"Setting FFWD to {config.FFWD}, FSEEK is {config.FSEEK}")
           config.FFWD = True
       config.FSEEK = False
    if self.name == 'rewind':
       logger.debug(F"GPIO is now {GPIO.input(self.pin)}")
       config.RSEEK = False
       sleep(0.5)
       logger.debug(F"GPIO is now {GPIO.input(self.pin)}")
       while GPIO.input(self.pin) == 0: # button is still being pressed -- NOTE: Because this is connected to pin2, default is on.
           logger.debug(F"Setting REWIND to {config.REWIND}, RSEEK is {config.RSEEK}")
           config.RSEEK = True
           sleep(0.1)
       if not config.RSEEK: 
           logger.debug(F"Setting REWIND to {config.REWIND}, RSEEK is {config.RSEEK}")
           config.REWIND = True
    if self.name == 'play_pause':
       if config.PLAY_STATE in [config.READY, config.PAUSED, config.STOPPED]: config.PLAY_STATE = config.PLAYING  # play if not playing
       elif config.PLAY_STATE == config.PLAYING: config.PLAY_STATE = config.PAUSED   # Pause if playing
       logger.debug(F"Setting PLAY_STATE to {config.PLAY_STATE}")
    if self.name == 'stop':
       if config.PLAY_STATE in [config.PLAYING, config.PAUSED]: config.PLAY_STATE = config.STOPPED  # stop playing or pausing
       logger.debug(F"Setting PLAY_STATE to {config.PLAY_STATE}")

"""
"""
    if self.name == 'year':
      config.TIH = True 
      logger.debug(F"Setting TIH to {config.TIH}")
    if self.name == 'month':
      if config.EXPERIENCE: config.EXPERIENCE = False
      else: config.EXPERIENCE = True
      logger.debug(F"Setting EXPERIENCE to {config.EXPERIENCE}")
    if self.name == 'day':
      config.NEXT_DATE = True
      logger.debug(F"Setting NEXT_DATE to {config.NEXT_DATE}")
     #sleep(0.3)

"""
