# Time Machine Operating Instructions

## Assembly

Remove the micro SD card from the adapter, and insert into the Raspbery Pi. The SD card goes into a small metal cage on the back side of the raspberry pi (the opposite side from the 40-pin connector).

Plug the Raspberry Pi into the connector on the Time Machine board. The Pi must be plugged in such that the USB power, and the headphone jack are on the **left side** when the Time Machine is viewed from the front. Use screws to secure the Raspberry Pi to the Time Machine.

Plug in a micro USB connector to the PWR IN connector on the Raspberry Pi (there is only one such connector on a Raspberry Pi 3A...other Pi's have separate Power and USB connectors...look for "PWR" on the board if in doubt).

## Connecting to Wifi

The Time Machine screen will come on when power is connected to the Raspberry Pi.
When the Time Machine is powered up, it will prompt you to select a Wifi name and input the passkey.

### Selecting the Wifi 
Turning the **year** knob changes which Wifi name will be displayed in red. 
To select the Wifi displayed in red, press the **select** button.

### Entering the Wifi Passkey
The screen will prompt you to input the passkey for the selected Wifi. 

A list of characters will be shown in white, with one "selectable" letter shown in red. 

- Turn the **year** knob to change which character is shown in red. 
- Press **select** button to select the red character.
- Once the entire password has been entered, press the **stop** button to indicate that you have finished. 
- If you make a mistake, turn the **year** knob all the way back until the "DEL" is shown in red. Pressing the **select** button erases the last character selected.

Once the correct Wifi name and password are entered, the Time Machine will launch the main program. You will not need to re-enter this information again as long as it remains valid. If you take the time machine to a new Wifi or change your password, the Wifi/passkey entry program will run again after a reboot.

### If Wifi Connection Fails
In the early prototypes, one failed password entry, etc, would put the Time Machine in a state where it would failt to connect to wifi without special intervention. If you are locked out of the Wifi connection, the procedure is:
- Remove the SD card, and plug it into your PC. You should see a folder called **/boot**.
- Create a file in the /boot folder called **wpa_supplicant.conf** with the following contents:
```
ctrl_interface=DIR=/var/run/wpa_supplicant GROUP=netdev
update_config=1
country=US

network={
        ssid="your wifi name"
        psk="your wifi password"
    }
```
**NOTE** replace your wifi name with the name of your wifi *in quotes*. For example if your wifi name is **MyWifi** and your password is **MyPassword**, then the file would look like:

```
ctrl_interface=DIR=/var/run/wpa_supplicant GROUP=netdev
update_config=1
country=US

network={
        ssid="MyWifi"
        psk="MyPassword"
    }
```
- *Windows users*: Make sure that the file is called **wpa_supplicant.conf**, and that it does not have a hidden file extension (like wpa_supplicant.conf.txt).
- Place the SD card into the Raspberry Pi and re-boot. 
- If this does not fix the Wifi connection problem, check the SD card contents again. The **wpa_supplicant.conf** file should no longer be in the **/boot** folder. The Raspberry Pi automatically moves it when it boots up. If that file is still there, then see the above instruction regarding hidden file extensions. If the file is not in the **/boot** folder, then check the contents of the **wpa_supplicant.conf** file. It should have worked, unless your Wifi name/passkey is incorrect, or you have a special type of Wifi. If so, please let me know.


## The Audio Output
### Analog Output
The Time Machine is currently configured to output analog audio from the headphone jack. You can plug this into your stereo using [a cable like this](https://www.amazon.com/Rankie-3-5mm-2-Male-Adapter-Cable/dp/B071R4R5B8/ref=sr_1_4?dchild=1&keywords=headphone+to+RCA+male&qid=1621462242&sr=8-4), or [an adapter like this](https://www.amazon.com/CERRXIAN-LEMENG-2-Pack-Adapter-Splitter/dp/B018V7GTNK/ref=sr_1_16?dchild=1&keywords=headphone+to+RCA+female&qid=1621462318&sr=8-16)
### Digital Output
The Time Machine can be configured to output Digital Audio through the HDMI connector. 

## Using the Time Machine

Using the Time Machine should be very intuitive. 
 - Select a Month, Day, and Year by turning the **Month**, **Day**, and **Year** knobs. 
 - Press the **select** button to select the date
 - Press the **play/pause** button to play the show.
 - **Stop**, **Rewind**, **Fast Fwd** behave as expected. See details below.

### The Screen Layout
The top of the screen shows the **staged date** in a large font in the MM-DD-YY format. 

If there is a show on the staged date, the **venue, city, state** is shown below the staged date. If there is a tape from the archive on that date, which is not a show, this area shows the tape identifier (usually something like "gdYYYY-MM-DD..."). Note that the venue, city, and state usually do not fit on the screen and will "scroll" over time. 

The area of the screen showing the venue, city, state will alternately display the **tape identifier**. If the tape is soundboard recording, the tape identifier is shown in white text. If the tape is an audience recording, the tape identifier is shown in red text.

If the staged date is selected (by pressing the **select** button) it becomed the **selected date**, and is shown in a smaller font at the bottom of the screen in MM-DD-YYYY format.

The **current track** and **next track** are shown in the middle of the screen in a red font.

The bottom right-hand corner of the screen shows the **playstate**, either playing, paused, stopped, or empty.

### Details about each knob and button
However, some special controls and shortcuts are documented here.
Each knob can be turned, and also pressed as a button. Each button may be "pressed" or "held" (pressed for a predefined period, generally 1 second).

#### Month Knob
- Turning the Month knob changes the month of the **staged date** from 1 to 12.
- Pressing the Month knob puts you into (or back out of) "Experience Mode". In Experience Mode, you can not see which songs are coming up, rewind, ffwd, or stop the current show. As if you were there, experiencing the show.

#### Day Knob
- Turning the Day knob changes the day of the **staged date** from 1 to 31 (depending on the Month (and Year if a Leap Year))
- Pressing the Day knob moves the **staged date** to the next date on which there is a tape in the archive.
- Holding the Day knob (*for 3 seconds*) turns off the screen. Turning or pressing any of the 3 knobs will wake up the screen.

#### Year Knob
- Turning the Year knob changes the year of the **staged date** from 1965 to 1995.
- Pressing the Year knob moves the **staged date** to today's month/day during the currently staged year (**today in history**, whether there is a tape on that date or not). Pressing the Year knob *again* will move the **staged date** to the next **today in history** on which there *is* a tape in the archive (or, if this is the last, it will start over again from 1965).
- Holding the year knob puts the Time Machine **on tour** in the currently selected year. This means that, whatever else the Time Machine is playing, it will play the Today In History show for the "on tour year" at the time that the show began (if known) or the default start time. To exit **on tour** mode, hold the year knob until it says that the Tour is finished (It will require an extra 3 seconds of holding the year button, in order to confirm).

#### Select Button
- Pressing the Select button selects the **staged date**, making it the **selected date**. This stops any currently playing tape.
- Holding the Select button cycles through the **tape identifiers** of the **staged date**. The identifiers are shown in the venue, city, state field. Red text indicates audience recordings. Releasing the Select button selects the **tape identifier** currently displayed. In this way, all tapes from the archive are reachable.

#### Play/Pause Button
- Pressing the Play/Pause button plays or pauses the tape from the selected date.
- Holding the Play/Pause button (*for 8 seconds*) selects and plays a **random** show from the archive.

#### Rewind and Fast Forward Buttons
- Pressing Rewind or Fast Forward advances to the next or moves back to the previous track.
- Holding Rewind or Fast Forward advances or moves back the play head by 30 seconds every 2 seconds.

#### Stop Button
- Pressing the Stop button stops the playback and moves the play head to the beginning of the show.
- Holding the Stop button (*for 8 seconds*) downloads the latest version of the software and restarts the program. **USE WITH CAUTION**

**Enjoy!**
