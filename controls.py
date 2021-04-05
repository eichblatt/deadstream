#!/usr/bin/python3
from RPi import GPIO
from time import sleep
import GD
import datetime
import logging
import digitalio
import board
import config
import adafruit_rgb_display.st7735 as st7735
from adafruit_rgb_display import color565
from PIL import Image, ImageDraw, ImageFont
import pkg_resources

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
    GPIO.add_event_detect(self.sw,GPIO.RISING, callback = self.sw_callback, bouncetime = self.bouncetime) 
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
    logging.info(F"Pushed button {self.name}")
    if self.name == 'year':
       config.SELECT_DATE = True 
       logging.info(F"Setting SELECT_DATE to {config.SELECT_DATE}")
    if self.name == 'day':
       config.PLAY_STATE = not config.PLAY_STATE  
       logging.info(F"Setting PLAY_STATE to {config.PLAY_STATE}")
    #sleep(0.3)

  def set_value(self,value): 
    self.value = min(max(value,min(self._values)),max(self._values))
  def get_value(self): 
    return self.value 
  def cleanup(self): 
    GPIO.cleanup()

class date_knob_reader:
  def __init__(self,y,m,d,archive=None):
    maxd = [31,29,31,30,31,30,31,31,30,31,30,31] ## max days in a month.
    if d.value > maxd[m.value-1]: d.set_value(maxd[m.value-1])
    self.date = None
    self.archive = archive
    try:
      self.date = datetime.date(y.value,m.value,d.value)
    except ValueError:
      d.set_value(d.value-1)
      self.date = datetime.date(y.value,m.value,d.value)
 
  def __str__(self):  
    return self.__repr__()

  def __repr__(self):
    avail = "Tape Available" if self.tape_available() else ""
    return F'Date Knob Says: {self.date.strftime("%Y-%m-%d")}. {avail}'

  def fmtdate(self):
    if self.date == None: return None
    return self.date.strftime('%Y-%m-%d')

  def venue(self):
    if self.tape_available: 
      t = self.archive.best_tape(self.fmtdate())
      t.get_metadata()
      return t.venue()
    return ""

  def tape_available(self):
    if self.archive == None: return False
    return self.fmtdate() in self.archive.dates   


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

class screen:
  def __init__(self):
    cs_pin= digitalio.DigitalInOut(board.CE0)
    dc_pin= digitalio.DigitalInOut(board.D24)
    reset_pin= digitalio.DigitalInOut(board.D25)
    #BAUDRATE= 2400000
    BAUDRATE= 40000000
    spi= board.SPI()
    self.disp= st7735.ST7735R(spi,rotation=270,cs=cs_pin,dc=dc_pin,rst=reset_pin,baudrate=BAUDRATE)
   
    self.bgcolor = color565(0,0,0)
    # --- swap width/height, if
    if self.disp.rotation % 180 == 90: height,width= self.disp.width,self.disp.height
    else: width,height= self.disp.width,self.disp.height
    self.width, self.height = width, height


    self.image = Image.new("RGB",(160,96))
    self.draw = ImageDraw.Draw(self.image)
    self.disp.image(self.image)
    print(' ---> disp ',self.disp.width,self.disp.height)
    self.font= ImageFont.truetype(pkg_resources.resource_filename("GD", "FreeMono.ttf"), 20)

  def rectangle(self,loc,size,color=(0,0,255)):
    x,y = loc; w,h = size;
    self.disp.fill_rectangle(x,y,w,h,color565(color))

  def set_pixel(self,loc,color=(0,0,255)):
    x,y = loc
    self.disp.pixel(x,y,color565(color))

  def black(self):
    self.disp.fill()
    self.disp.init()

  def clear(self):
    self.disp.reset()
    self.black()

  def show_text(self,text,loc=(0,0),color=(255,255,255)):
    (font_width,font_height)= self.font.getsize(text)
    print(F' ---> font_size {font_width},{font_height}')
    self.draw.text(loc, text, font=self.font,fill=color)
    self.disp.image(self.image)

  def show_playstate(self,playstate,loc=(146,6),color=(100,100,255)):
    y,x = loc; color = color565(color);
    logging.debug("showing playstate {playstate}")
    if playstate == 'playing':  
       self.disp.fill_rectangle(x,y,9,9,self.bgcolor)  
       for i in range(9):
         self.disp.hline(x+int(i/2),y+i,9-i,color)  
    if playstate == 'paused' :  
       self.disp.fill_rectangle(x,y,9,9,color)  
       self.disp.fill_rectangle(x,y+3,9,3,self.bgcolor)   # draw black stripe
    if playstate == 'stopped' :  
       self.disp.fill_rectangle(x,y,9,9,self.bgcolor)  

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

 
#y = knob((13,26,23),"year",range(1965,1996),1979)   # cl, dt, sw
#m = knob((16,22,20),"month",range(1,13),11)
#d = knob((12,6,5)  ,"day",range(1,32),2,bouncetime=100)

y = knob((16,22,23),"year",range(1965,1996),1979)   # cl, dt, sw
m = knob((13,17,27),"month",range(1,13),11)
d = knob((12,5,6)  ,"day",range(1,32),2,bouncetime=100)


_ = [x.setup() for x in [y,m,d]]

logging.info ("Loading GD Archive")
a = GD.GDArchive('/home/steve/projects/deadstream/metadata')
#a = None
logging.info ("Done ")

staged_date = date_knob_reader(y,m,d,a)
selected_date = None
print (staged_date)
d0 = staged_date.date

scr = screen()
scr.clear()
#scr.show_date(datetime.date(1977,11,2),tape=True)
scr.show_date(staged_date.date,tape=staged_date.tape_available())
#scr.show_text(staged_date.venue())
play_state = config.PLAY_STATE

while True:
  staged_date = date_knob_reader(y,m,d,a)
  if staged_date.date != d0: 
    logging.info (F"DATE: {config.DATE}, SELECT_DATE: {config.SELECT_DATE}, PLAY_STATE: {config.PLAY_STATE}")
    print (staged_date)
    d0 = staged_date.date
    scr.show_date(staged_date.date,tape=staged_date.tape_available())
#    if staged_date.tape_available(): 
#      venue = staged_date.venue()
#      scr.show_text(venue)
#    else:
#      scr.draw.rectangle((0,0,160,32),outline=0,fill=(0,0,0)) # erase the venue
#      scr.disp.image(scr.image)
  if config.SELECT_DATE:
    if staged_date.tape_available():
       config.DATE = staged_date.date 
       logging.info(F"Setting DATE to {config.DATE.strftime('%Y-%m-%d')}")
       scr.show_date(config.DATE,loc=(85,0),size=10,color=(255,255,255),stack=True,tape=True)
    config.SELECT_DATE = False
  if config.PLAY_STATE and not play_state:  # start playing
     date_fmt = config.DATE.strftime('%Y-%m-%d')
     tape = a.best_tape(date_fmt)
     player = GD.GDPlayer(tape)
     logging.info(F"Playing {date_fmt} on player")
     player.play()
     scr.show_playstate('playing')
  if not config.PLAY_STATE and play_state:  # pause playing
     logging.info(F"Pausing {date_fmt} on player")
     player.pause()

     scr.show_playstate('paused')
  play_state = config.PLAY_STATE

  sleep(.1)
