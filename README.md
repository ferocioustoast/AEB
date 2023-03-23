# Audio Estim Bridge
Using python with vgamepad to emulate an X360 controller and turn received vibrations into sinewaves with pysinewave.

## WARNING: This program may unexpectedly shock you. The creator is not a professional software developer, audio engineer, or electrical engineer and has no idea what they are doing. You have been warned!

### Installation

_Installing is a little more complicated because pip does not download the up to date version of Pysinewave that allows the use of multiple sound channels_

1. Download AEB.py and requirements.txt from this repo

2. Install the requirements with Powershell/CMD
   ```sh
   python -m pip install -r .\requirements.txt
   ```
3. Download up to date Pysinewave sinewave.py file
   ```sh
   https://raw.githubusercontent.com/daviddavini/pysinewave/master/pysinewave/sinewave.py
   ```
4. Place sinewave.py into your python install location, default location is
   ```sh
   C:\Users\YOUR_USER\AppData\Local\Programs\Python\YOUR_VERSION\Lib\site-packages\pysinewave
   ```

### Usage

1. Change the active Windows playback sound device to the device your Estim device is connected to.

_The program will automatically attach to the active sound playback device on start. If you can hear the tone, it is likely that it is not being sent to your Estim device._

2. Run AEB.py with Powershell/CMD or by double clicking AEB.py

3. Change the active Windows playback sound device back.

_The program only attaches when it is first launched; you can now change the active device back to hear any sounds that are not going to your Estim device. This also prevents any unintended sounds from going to your device, which can unexpectedly shock you._

4. Use a program such as https://intiface.com/central/ that can connect to the X360 controller and control the vibrations.

5. Play around with the hotkeys shown in the window or edit the file directly until the resulting sounds are satisfactory.