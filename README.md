# The Grateful Dead Time Machine

A raspberry pi controller with year, month, date knobs to stream any Grateful Dead show on archive.org.

It's also a simple, command-line-interface to the Greatful Dead collection on archive.org, which can be used to see what's available and play a given tape.

A Simple example for the python script:

``` python
import GD

metadata_path = os.path.join(os.getenv('$HOME'),'/projects/deadstream/metadata')
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
pip install .
```

or

```
python setup.py install
```

# Uninstall the module

```
pip uninstall deadstream
```

# Build without installing

This will put the module in `build/lib`.

```
python setup.py build
```

# Run unit tests

To be able to run unit tests, install the requirements.

```
pip install -r requirements
```

## Run tests with pytest

```
python -m pytest
```

## Run tests with tox

Using tox will test the whole build pipeline using setup.py
and run the unit tests using pytest.

```
tox
```
