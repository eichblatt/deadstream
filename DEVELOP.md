# Set up a development environment

1. Clone the repo
2. `cd deadstream`
2. Run `python -m venv env` to create a python virtual environment
3. Activate the virtual environment by `source env/bin/activate`
4. Run `pip install -r requirements.txt` to install required packages (into the virtual environment)

# MPV (libmpv) on Fedora

Fedora's package repository does not have mpv, but it is in the RPM Fusion repository.

Follow the instructions at https://rpmfusion.org/Configuration/ to enable the RPM Fusion
repository.

```bash
dnf install \
    https://mirrors.rpmfusion.org/free/fedora/rpmfusion-free-release-$(rpm -E %fedora).noarch.rpm \
    https://mirrors.rpmfusion.org/nonfree/fedora/rpmfusion-nonfree-release-$(rpm -E %fedora).noarch.rpm
```

Once Fusion is enabled, install libmpv.

```bash
dnf install mpv-libs-devel
```

# Tox complaining about missing modules

If you make a change that requires re-building the tox virtual environment(s),
such as changing the `install_requires` in `setup.py`, use:

```
tox --recreate
```

This will force tox to rebuild its virtual environments.
