#!/usr/bin/python3

from sys import stdout,exit
from time import time,sleep
import pickle5 as pickle

from datetime import date,datetime
from dateutil.relativedelta import relativedelta

import digitalio
import board
import adafruit_rgb_display.st7735 as st7735
from adafruit_rgb_display import color565
from RPi import GPIO as gpio

from PIL import Image, ImageDraw, ImageFont

## ---

notBild= False
meInterrupt= False
import signal

def meCustomHandler(signum,stack_frame):
   global meInterrupt
   print('encountered ctrl+C - here before the process exists')
   meInterrupt= True

signal.signal(signal.SIGINT, meCustomHandler)

## ---

class meDate():
  def __init__(self, y,m,d):
     self.year= y
     self.month= m
     self.day= d

oot= time()

# ---                          mar'21 27-01:50  from ./bigger
### --- display setup           pretty much like in steves
# ---

cs_pin= digitalio.DigitalInOut(board.CE0)
dc_pin= digitalio.DigitalInOut(board.D24)
reset_pin= digitalio.DigitalInOut(board.D25)
BAUDRATE= 40000000

spi= board.SPI()
disp= st7735.ST7735R(spi,rotation=270,cs=cs_pin,dc=dc_pin,rst=reset_pin,baudrate=BAUDRATE)
# --- swap width/height, if
if disp.rotation % 180 == 90: height,width= disp.width,disp.height
else: width,height= disp.width,disp.height

### --- fonts

class Font():
   def __init__(self):
      self.little= ImageFont.truetype("ariallgt.ttf",15)
      self.font= ImageFont.truetype("ariallgt.ttf",20)
      self.large= ImageFont.truetype("ariallgt.ttf",57)
      self.medium= ImageFont.truetype("ariallgt.ttf",30)
      self.small= ImageFont.truetype("ariallgt.ttf",25)
      self.gig= ImageFont.truetype("DejaVuSansMono-Bold.ttf",20)

### --- init display

border= 1
image= Image.new("RGB",(width,height))
screen= ImageDraw.Draw(image)
screen.rectangle((0,0,width,height), outline=200, fill=(200,200,30))
screen.rectangle((border,border,width-border-1, height-border-1),outline=0,fill=(2,2,2))
disp.image(image)

### ---

F= Font()
Year,Month,Day,WeekDay,aShow=1965,0,1,'Monday',False
today= date(Year,Month+1,Day)
WeekDay= today.weekday()

print(' ---rt--- a %7.2f '%(time()-oot))

def steve():
   global image,disp,screen, width,height,notBild
   global Year,Month,Day,WeekDay,aShow
   mName= ['January','February','March','April','May','June','July','August','September','October','November','December']
   dName= ['Monday','Tuesday','Wednesday','Thursday','Friday','Saturday','Sunday']
   notBild= True

   border= 1
   screen.rectangle((0,0,width,height), outline=200, fill=(200,200,30))
   screen.rectangle((border,border,width-border-1, height-border-1), outline=0 ,fill=(2,2,2))
# ------------
   cpuTemp= 0
   with open('/sys/class/thermal/thermal_zone0/temp') as ftmp: cpuTemp= int(ftmp.read())*.001
   screen.text((118,112), '%5.1fc'%cpuTemp, font=F.little,fill=(220,220,220))

   try: thereIsAGig= gigs[Year][Month+1][Day]
   except: thereIsAGig= None

   year= ' %4i ' % Year
   weekday= ' %9s' % (dName[WeekDay-1])
   monday= "{:<15}".format(' %s-%02i ' % (mName[Month],Day))
   aShow= ' show ' if thereIsAGig else '      '
# ----------------------------------------------------------
   screen.text((30,-5),year,font=F.large,fill=(40,230,180))
   screen.text((2,46),weekday,font=F.medium,fill=(80,210,170))
   screen.text((0,75),monday,font=F.small,fill=(120,200,170))
   screen.text((-3,100),aShow,font=F.gig,fill=(40,40,230))
# -------------------
   disp.image(image)


def bild():
   global image,disp,screen,notBild
   font= F.font

   text= "Year: 1965-1995 \n"
   (fw,fh)= font.getsize(text)
   text+= "-------- \n Greatful \n   Dead "
   (font_width,font_height)= font.getsize(text)
   print(' ---> hey ',font_width,font_height)
   screen.text(( 5,10), text, font=font,fill=(50,220,200))
   ## --ae--
   text= "      streaming "
   (font_width,font_height)= font.getsize(text)
   screen.text((25,100), text, font=font,fill=(90,90,230))
   disp.image(image)
   notBild= False

bild()

print(' ---rt--- b %7.2f '%(time()-oot))

###
### --------------------------------------------------------------------------------

###
### --- mar'21 21-22:05
###
###     a function to give us a nice dict for all the greatful dead dates
###     with day-of-the-week
###     mostly a quick and dirty
###

def meCalender(theList):

   week= ['mon','tue','wed','thu','fri','sat','sun']
   none= [0,31,59,90,120,151,181,212,243,273,304,334]
   leap= [0,31,60,91,121,152,182,213,244,274,305,335]
   leapYears= [1968,1972,1976,1980,1984,1988,1992,1996]
   day1st= [4,5,6,0, 2,3,4,5, 0,1,2,3, 5,6,0,1, 3,4,5,6, 1,2,3,4, 6,0,1,2, 4,5,6,0]

   theGigs= {}

   for L in theList:
      y,m,d= L.split('-')
      y,m,d= int(y),int(m),int(d)

      year= leap if y in leapYears else none
      days= year[m-1]+d
      w= week[(days+day1st[y-1965]-1)%7]

      try: n= len(theGigs[y])
      except: theGigs[y]= {}

      try: theGigs[y][m][d]= w
      except:
              theGigs[y][m]= {}
              theGigs[y][m][d]= w

   return theGigs

### --------------------------------------------------------------------------------
###


### --ae------------ only read through database if really wanted ---

import GD


try:
     print(' ---rt--- c %7.2f '%(time()-oot))
     with open('theGigs.pkl','rb') as f:
         gigs= pickle.load(f)
     print(' ---rt--- d theGigs %7.2f '%(time()-oot))

except:
        print(' ---> loading GD ')
        stdout.flush()

        a= GD.GDArchive('/home/empl/projects/deadstream/metadata',reload_ids=False)

        print(' ---> got it  %7.2f '%(time()-oot))
        print(' ---> sort ')

        meDates= a.dates
        gigs= meCalender(meDates)

print(' ---> did it  %7.2f '%(time()-oot))
print(' --> 1971 01 21 - ',gigs[1971][1][21])
print()

### --ae------------
def save_obj(obj,name):
    with open(name+'.pkl','wb') as f:
        pickle.dump(obj,f,pickle.HIGHEST_PROTOCOL)

## save_obj(gigs,theName)
### --ae------------  <-o- use for a new version



class Knobs():
# ------------------------------------------------
   def __init__(self):
      self.pins= [(16,22,23),(13,17,27),(12,5,6)]   ### <<<--- the pins ---
      self.oState= [(1,1,1),(1,1,1),(1,1,1)]
      self.old= (0,date(1965,1,1))
# ------------------------------------------------



## ------------------ actually not needed anymore ----
def channel(aDay):
   global Year,Month,Day,WeekDay,aShow
   med= meDate(Year,Month,Day)
   steve()


t,p= None,None
weRpaused= False

def CallBack(nn):
   global K, Year,Month,Day,WeekDay
   global t,p,weRpaused

   old= K.old
   for (J,abc) in enumerate(K.pins):
      if nn in abc:
                    cl,dt,sw= abc
                    ocl,odt,osw= K.oState[J]
                    old= K.old
                    j= J

   today= date(Year,Month+1,Day)
   theDay= today

   Kcl,Kdt,Ksw= gpio.input(cl),gpio.input(dt),gpio.input(sw)
   if ocl!=Kcl or odt!=Kdt or osw!=Ksw:

     if osw==1 and Ksw==0:
       print(' --theSwitch-- ',nn)
   #   ---------------------- the push buttons ---
       if nn==27:
                  print(' --theSwitch-- ',nn,' -- pause ',weRpaused)
                  if weRpaused:
                    try:
                         p.play()
                         weRpaused= False
                         fout.write('     %7.1f %5.1f  -paused- \n'%(time()-startTime,cpuTemp))
                    except: print(' -except- play() after pause ')
                  else:
                        try:
                             p.pause()
                             weRpaused= True
                             fout.write('     %7.1f %5.1f  -paused- \n'%(time()-startTime,cpuTemp))
                        except: print(' -except- pause() ')
       else:
             if nn==6:
                       print(' --theSwitch-- ',nn,' -- stop ')
                       try: p.stop()
                       except: print(' -except- stop() ')
                       print(' -p- ',p)
                       print(' -t- ',t)
                       try: p.close()
                       except: print(' -except- close() ')
                       print('            -- ',nn,' -- close ')
             else:
                   if nn==23:
                              aShow= '%4i-%02i-%02i' % (Year,Month+1,Day)
                              print(' --theSwitch-- ',nn,' -- ')  ## ,aShow)
                              t= a.best_tape(aShow)
                              p= GD.GDPlayer(t)
                              try: p.play()
                              except: print(' -except- play() ')

   #   --------------------------------- rotary ---
     else:
           if Kcl==ocl and Kdt==odt:
             if j==old[0]:
                           today= old[1]
                           channel(today)
                        # ----------------->> simply one back <<---
           else:
             if ocl==1 and odt==1:
               if Kcl==1 and Kdt==0: dt= -1
               if Kcl==0 and Kdt==1: dt= +1
       # -X----
               if j==0: theDay+= relativedelta(years=dt)
               else:
                     if j==1: theDay+= relativedelta(months=dt)
                     else:
                           theDay+= relativedelta(days=dt)
       # -X----
           if today!=theDay:
             if theDay.year>1964 and theDay.year<1996:
               Year,Month,Day,WeekDay= theDay.year,theDay.month-1,theDay.day,theDay.isoweekday()
               channel(theDay)
            # ----------------->>

   K.oState[j]= (Kcl,Kdt,Ksw)
   K.old= (j,today)



###
### --- main ---

# ? gpio.cleanup()
print(' ---> starting main %7.2f '%(time()-oot))


K= Knobs()

gpio.setmode(gpio.BCM)

for j,k in enumerate(K.pins):
   gpio.setup(k, gpio.IN,pull_up_down=gpio.PUD_DOWN)
   try:
     for pin in k: gpio.add_event_detect(pin,gpio.BOTH,callback=CallBack)
   except:
           print(' ---aerger--- '+str(k))
           try:
             for pin in k: gpio.add_event_detect(pin,gpio.BOTH,callback=CallBack)
           except: exit('    aerger --- exit '+str(k))

print(' ---> implemented knob 1,2 and 3   %7.2f '%(time()-oot))


## ---
print(' ---rt--- e %7.2f '%(time()-oot))
# import pickle5 as pickle
with open('archive.pkl','rb') as f:
    a= pickle.load(f)
print(' ---rt--- f archive %7.2f '%(time()-oot))
## ---

fout= open('temp.log','a')
startTime= time()
fout.write(' --- %f \n' % (time()-startTime))

try:
  while True:
    cpuTemp= 0
    with open('/sys/class/thermal/thermal_zone0/temp') as ftmp: cpuTemp= int(ftmp.read())*.001
    fout.write('     %7.1f %5.1f \n' % (time()-startTime,cpuTemp))
    fout.flush()
    if notBild: steve()
    print(' --> main ','  tmp %5.1fC'%cpuTemp)

    sleep(10)
# -------------------------
    if meInterrupt: break
    pass 

finally:
         fout.close()
         print(' ---finally--- ')
         gpio.cleanup()

         screen.rectangle((0,0,width,height), outline=200, fill=(200,200,30))
         screen.rectangle((border,border,width-border-1, height-border-1),outline=0,fill=(2,2,2))
         disp.image(image)
         exit()

         bild()
         disp.image(image)
         sleep(1)

