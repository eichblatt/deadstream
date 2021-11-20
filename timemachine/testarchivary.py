import sys
import time
from threading import Event

from timemachine import Archivary
from timemachine import GD

track_event = Event()

aa = Archivary.Archivary(collection_name=['GratefulDead','Phish','PhilLeshandFriends'])
aa.tape_dates
tape = aa.best_tape('1992-05-05')

p = GD.GDPlayer(tape)

#pp = Archivary.PhishinArchive(reload_ids=False)
#pp.tape_dates['1992-05-05'][0].tracks()

#ph_tape = pp.best_tape('1992-05-05')
#p = GD.GDPlayer(ph_tape)

#gd = Archivary.GDArchive(collection_name=['GratefulDead','PhilLeshandFriends'])
#tapedate = '1982-11-25'
#tapes = gd.tape_dates[tapedate]
#gd_tape = tapes[3]

p.play()


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
