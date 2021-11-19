import sys
import time
from threading import Event

from timemachine import Archivary
from timemachine import GD

track_event = Event()

pp = Archivary.PhishinArchive()
pp.tape_dates['1992-05-05'][0].tracks()

ph_tape = pp.best_tape('1992-05-05')
p = GD.GDPlayer(ph_tape)

p.play()

gd = Archivary.GDArchive()
tapedate = '1982-11-25'
tapes = gd.tape_dates[tapedate]
gd_tape = tapes[3]



@p.property_observer('playlist-pos')
def on_track_event(_name, value):
    track_event.set()
    if value == None:
        pass
    print(F'in track event callback {_name}, {value}')


p.seek_to(1, 0.)

p.fseek(300)

# Start playback.
p.play()

time.sleep(10)

p.pause()

p.seek_to(8, 100.0)

p.status()
p.play()
for i in range(3):
    p.fseek(-30)
