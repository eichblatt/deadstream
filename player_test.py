import sys
import time
from threading import Event

from timemachine import GD
GD.logger.setLevel(10)

track_event = Event()

if __name__ == "__main__":
    # Open the video player and load a file.
    archive = GD.GDArchive("/home/steve/projects/deadstream/metadata")
    tape = archive.best_tape('1982-11-25')
    p = GD.GDPlayer(tape)
    @p.property_observer('playlist-pos')
    def on_track_event(_name, value):
      track_event.set()
      print(F'in track event callback {_name}, {value}')

    
    # Seek to 5 minutes.
    p.seek_to(1,0.)
   
    p.fseek(300)

    # Start playback.
    p.play()

    # Playback for 15 seconds.
    time.sleep(5)

    # Pause playback.
    p.pause()
    
   # for i in range(8): p.next()
    #p.seek_to(8,0.0)

    p.status()
    p.play()
    #for i in range(3): p.fseek(-30)
