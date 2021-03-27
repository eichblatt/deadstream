#!/usr/bin/python3

###
### --- mar'21 18-16:00
###
###     needs a bunch of python/adafruit setup
###     not elegant (yet)
### 


from time import sleep

import digitalio
import board
import adafruit_rgb_display.st7735 as st7735

from PIL import Image, ImageDraw, ImageFont


# ---
### --- display setup
# ---

cs_pin= digitalio.DigitalInOut(board.CE0)
dc_pin= digitalio.DigitalInOut(board.D24)
reset_pin= digitalio.DigitalInOut(board.D25)
BAUDRATE= 2400000
BAUDRATE= 40000000


spi= board.SPI()
disp= st7735.ST7735R(spi,rotation=270,cs=cs_pin,dc=dc_pin,rst=reset_pin,baudrate=BAUDRATE)

# --- swap width/height, if
if disp.rotation % 180 == 90: height,width= disp.width,disp.height
else: width,height= disp.width,disp.height

border= 2

image= Image.new("RGB",(width,height))
draw= ImageDraw.Draw(image)
draw.rectangle((0,0,width,height), outline=0,fill=(0,0,0))
disp.image(image)
print(' ---> disp ',disp.width,disp.height)


# ---
### --- poti setup
# ---

from RPi import GPIO

cl0,dt0,sw0= 13,19,26

GPIO.setmode(GPIO.BCM)
GPIO.setup(cl0,GPIO.IN,pull_up_down=GPIO.PUD_DOWN)
GPIO.setup(dt0,GPIO.IN,pull_up_down=GPIO.PUD_DOWN)
GPIO.setup(sw0,GPIO.IN,pull_up_down=GPIO.PUD_DOWN)

oCtr,ctr= 1966,1966
cl0State,dt0State,sw0State= GPIO.input(cl0),GPIO.input(dt0),GPIO.input(sw0)
ocl0,odt0,osw0= cl0State,dt0State,sw0State

print(' --> 0 ',cl0State,dt0State,sw0State)

# ---
### ---
# ---


draw.rectangle((0,0,width,height), outline=128,fill=(120,10,10))
draw.rectangle((border,border,width-border-1, height-border-1),outline=0,fill=(0,0,0))

font= ImageFont.truetype("FreeMono.ttf",20)
#font= ImageFont.truetype("FreeMono.ttf",14)
#fot= ImageFont.truetype("FreeMono.ttf",10)

text= "Year: 1966 \n"
(fw,fh)= font.getsize(text)
text+= " ---> \n Grateful \n Dead \n Stream"
(font_width,font_height)= font.getsize(text)
print(' ---> hey ',font_width,font_height)
draw.text((30,10), text, font=font,fill=(50,210,210))

## --ae--

#text= " oxoxoxo "
#(font_width,font_height)= font.getsize(text)
#draw.text((30,80), text, font=font,fill=(70,70,200))
#disp.image(image)
 
### ---

try:
        while True:
             cl0State,dt0State,sw0State= GPIO.input(cl0),GPIO.input(dt0),GPIO.input(sw0)
             if ocl0!=cl0State or odt0!=dt0State or osw0!=sw0State:

                if osw0==1 and sw0State==0:
                  print(' --meMenu-- ')

                else:

                      cpuTemp= 0
                      with open('/sys/class/thermal/thermal_zone0/temp') as ftmp: cpuTemp= int(ftmp.read())*.001
                   # ------
                      draw.rectangle((102,110,102+55,110+13),outline=0,fill=(0,0,0))
                      draw.text((102,110), '%5.1fC'%cpuTemp, font=font,fill=(210,210,210))

                      if cl0State!=ocl0 or dt0State!=odt0:
                        if ocl0==1 and odt0==1 and cl0State==1 and dt0State==0: ctr -= 1
                        if ocl0==1 and odt0==1 and cl0State==0 and dt0State==1: ctr += 1

                      if ctr!=oCtr:
                        draw.rectangle((30,10,fw+30,fh+10),outline=0,fill=(0,0,0))
                        text= 'Year: %4i ' % ctr
                        print(' ---> year ',text,'  tmp %5.1fC'%cpuTemp)
                        draw.text((30,10), text, font=font,fill=(50,210,210))
                   # ------
                        disp.image(image)
                        oCtr= ctr

             ocl0,odt0,osw0= cl0State,dt0State,sw0State
             sleep(0.001)

finally:
         pass ### GPIO.cleanup()


