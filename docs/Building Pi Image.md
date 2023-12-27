# Building Pi Image

- [Building Pi Image](#building-pi-image)
  - [Create the Deadhead User](#create-the-deadhead-user)
  - [Enable SSH (for debugging only)](#enable-ssh-for-debugging-only)
  - [Enable SPI](#enable-spi)
  - [Disable GUI on Raspberry Pi](#disable-gui-on-raspberry-pi)
  - [Send audio to headphone jack](#send-audio-to-headphone-jack)
  - [Change the hostname to `timemachinev5`](#change-the-hostname-to-timemachinev5)
  - [Clone the repo](#clone-the-repo)
  - [Install libmpv-dev](#install-libmpv-dev)
  - [Install mpv](#install-mpv)
    - [NOTE](#note)
  - [Install the package locally](#install-the-package-locally)
  - [Update the code](#update-the-code)
  - [Getting Bluetooth to work](#getting-bluetooth-to-work)
  - [Creating an SD Image](#creating-an-sd-image)

## Create the Deadhead User

Once logged into the pi, with a deadhead username:

## Enable SSH (for debugging only)

sudo service ssh start
Enable SSH (sudo raspi-config, Interface Options, SSH)

deadhead@timemachinev5:~ $ sudo systemctl enable ssh

## Enable SPI

sudo raspi-config
SPI
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

## Install libmpv-dev

sudo apt-get install libmpv-dev

## Install mpv

sudo apt-get install mpv

### NOTE

I may need to get an older version of this library.

## Install the package locally

deadhead@timemachinev3:~/deadstream $ python3 -m venv env
deadhead@timemachinev3:~/deadstream $ source env/bin/activate
(env) deadhead@timemachinev3:~/deadstream $ pip install .
(env) deadhead@timemachinev3:~/deadstream $ pip install ipython
(env) deadhead@timemachinev3:~/deadstream $ ipython -i timemachine/main.py

## Update the code

To install the package on the machine, ie, to run it on startup, run the update.sh script

## Getting Bluetooth to work

Ugh!
Add root to the groups audio, etc.

sudo raspi-config
Advanced options, Audio setup, Choose pulseaudio

<https://www.collabora.com/news-and-blog/blog/2022/09/02/using-a-raspberry-pi-as-a-bluetooth-speaker-with-pipewire-wireplumber/>

## Creating an SD Image

See the file ~/timemachine/images/make_image.sh
