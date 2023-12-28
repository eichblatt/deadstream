# Building Pi Image

- [Building Pi Image](#building-pi-image)
  - [Create the deadhead User](#create-the-deadhead-user)
  - [Enable SSH (for debugging only)](#enable-ssh-for-debugging-only)
  - [Enable SPI](#enable-spi)
  - [Disable GUI on Raspberry Pi](#disable-gui-on-raspberry-pi)
  - [Send audio to headphone jack](#send-audio-to-headphone-jack)
  - [Change the hostname to `timemachinev5`](#change-the-hostname-to-timemachinev5)
  - [Clone the repo](#clone-the-repo)
  - [Install libmpv-dev and mpv](#install-libmpv-dev-and-mpv)
    - [NOTE](#note)
  - [Install the package locally](#install-the-package-locally)
  - [Version 2](#version-2)
  - [Update the code](#update-the-code)
  - [Getting Bluetooth to work](#getting-bluetooth-to-work)
    - [Set the default sink to bluetooth](#set-the-default-sink-to-bluetooth)
  - [Install jackd](#install-jackd)
  - [Disable SSH](#disable-ssh)
  - [Creating an SD Image](#creating-an-sd-image)

## Create the deadhead User

Once logged into the pi, with a deadhead username:

## Enable SSH (for debugging only)

sudo service ssh start
Enable SSH (sudo raspi-config, Interface Options, SSH)

deadhead@timemachinev5:~ $ sudo systemctl enable ssh

## Enable SPI

sudo raspi-config
Interface options, SPI
Enable Yes

## Disable GUI on Raspberry Pi

deadhead@timemachinev3:~ $ sudo service lightdm stop
deadhead@timemachinev3:~ $ sudo systemctl disable lightdm

## Send audio to headphone jack

sudo raspi-config, System, Audio, choose headphones

## Change the hostname to `timemachinev5`

deadhead@raspberrypi:~ $ sudo vi /etc/hosts
deadhead@raspberrypi:~ $ sudo vi /etc/hostname

## Clone the repo

`
deadhead@timemachinev3:~ $ git clone https://github.com/eichblatt/deadstream.git
`

## Install libmpv-dev and mpv

sudo apt-get install libmpv-dev

sudo apt-get install mpv

### NOTE

I may need to get an older version of this library.

## Install the package locally

deadhead@timemachinev3:~/deadstream $ python3 -m venv env
deadhead@timemachinev3:~/deadstream $ source env/bin/activate
(env) deadhead@timemachinev3:~/deadstream $ pip install .
(env) deadhead@timemachinev3:~/deadstream $ pip install ipython
(env) deadhead@timemachinev3:~/deadstream $ ipython -i timemachine/main.py

## Version 2

In order for the rewind button to work, we need to be in version 2 boards.
Add `dtoverlay=gpio-shutdown` to the file `/boot/config.txt`

## Update the code

To install the package on the machine, ie, to run it on startup, run the update.sh script
cd deadstream/timemachine/bin
bash ./update.sh

## Getting Bluetooth to work

Ugh!
Add root to the groups audio, etc.

sudo raspi-config
Advanced options, Audio setup, Choose pulseaudio

<https://www.collabora.com/news-and-blog/blog/2022/09/02/using-a-raspberry-pi-as-a-bluetooth-speaker-with-pipewire-wireplumber/>

### Set the default sink to bluetooth

pacmd list-sinks
pacmd set-default-sink 1

See <https://askubuntu.com/questions/71863/how-to-change-pulseaudio-sink-with-pacmd-set-default-sink-during-playback>

And add this to /etc/dbus-1/system.d/pulse.conf

```{verbatim}
<!DOCTYPE busconfig PUBLIC
 "-//freedesktop//DTD D-BUS Bus Configuration 1.0//EN"
 "http://www.freedesktop.org/standards/dbus/1.0/busconfig.dtd">
<busconfig>
 <policy user="root">
  <allow own="org.pulseaudio.Server"/>
                <allow send_destination="org.bluez"/>
                <allow send_interface="org.bluez.Manager"/>
 </policy>
 <policy user="pulse">
  <allow own="org.pulseaudio.Server"/>
                <allow send_destination="org.bluez"/>
                <allow send_interface="org.bluez.Manager"/>
 </policy>
 <policy context="default">
                <deny own="org.pulseaudio.Server"/>
                <deny send_destination="org.bluez"/>
                <deny send_interface="org.bluez.Manager"/>
        </policy>
</busconfig>
```

or  /etc/dbus-1/system.d/bluetooth.conf

and

`chmod -x /usr/bin/start-pulseaudio-x11`

## Install jackd

Totally not sure if this will help, but I'm desperate
sudo apt-get install jackd

## Disable SSH

sudo systemctl disable ssh

## Creating an SD Image

See the file ~/timemachine/images/make_image.sh
