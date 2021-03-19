# deadstream -- The Grateful Dead Time Machine

A raspberry pi controller with year, month, date knobs to stream any Grateful Dead show on archive.org.

A Simple example:

``` python
import GD

metadata_path = '/home/steve/projects/deadstream/metadata'
a = GD.archive(metadata_path)

#dates = a.dates  # shows a list of all dates on which there are tapes.

tape = a.best_tape('1979-11-02')

player = GD.GDPlayer(tape)

player.play()

player.next()

player.seek(100)

player.pause()

player.play()

player.stop()

```

