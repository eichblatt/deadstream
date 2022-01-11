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

## The Services

### calibrate.service
runs at bootup, before the WiFi is even turned on.
This reads the orientation of the knobs, tests the buttons and sound, and configures a default COLLECTION.
Exits when finished.
### connect_network.service
runs after calibrate.service, when the WiFi radio is on.
Checks if connected to the internet and if not, allows the user to select WiFi and enter passkey.
Exits with a status when finished.
### timemachine.service 
runs upon successful completion of connect_network.service.
This is the main program to play shows. This should run as long as the machine is up, or until it is restarted.
### serve_options.service
runs on bootup and stays running all the time.
serve_options runs the web server, allowing you to configure some things that are too hard to do through the Time Machine itself.
Such as setting the COLLECTIONS list, and the Time Zone and stuff like that.
You can access this server from a browser on the same WiFi with <IP_ADDRESS>:9090
### update.service
runs on demand.
The user can asks for an update in the timemachine service by pressing and holding the "stop" button.
Update will check if there is a new tag on github, and if so, create a new virtual environment, download, install,
and test the latest code. If the code passes the test, then it will put the new virtual environment in place,
and hold on to the previous 8 virtual environments, for rollback if needed.

## About the code

The code was developed by Steve Eichblatt, with key guidance from Derek Wisong.
