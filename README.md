# The Grateful Dead Time Machine

A raspberry pi controller with year, month, date knobs to stream shows from audio collections on archive.org.

It also contains a simple, command-line-interface to the collections on archive.org, which can be used to see what's available and play a given tape.


A Simple example for the python script:

``` python
import os
from timemachine import GD

metadata_path = os.path.join(GD.ROOT_DIR,'metadata')
a = GD.GDArchive(metadata_path)

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

# Install the module

```
pip3 install .
```

or

```
python3 setup.py install
```

# Uninstall the module

```
pip3 uninstall timemachine
```

# Build without installing

This will put the module in `build/lib`.

```
python3 setup.py build
```

# Run unit tests

To be able to run unit tests, install the requirements.

```
pip3 install -r requirements
```

## Run tests with pytest

```
python3 -m pytest
```

## Run tests with tox

Using tox will test the whole build pipeline using setup.py
and run the unit tests using pytest.

```
tox

```
## Upgrading the software

## About the code

The code was developed by Steve Eichblatt, with key guidance from Derek Wisong.
