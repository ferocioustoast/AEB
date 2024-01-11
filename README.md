# Audio Estim Bridge

## WARNING: This program may unexpectedly shock you. The creator is not a professional software developer, audio engineer, or electrical engineer and has no idea what they are doing. Use at your own risk. You have been warned!

### How it Works

The program plays a sinewave and emulates an X360 controller that can connect to something like [Intiface](https://intiface.com/central/), which can control the rumble of the controller. Using the rumble, we change the volume of the left and right channels of the sinewave depending on the strength of the rumble.

As vgamepad uses ViGEm, which is Windows only, <b>this will only work for Windows.</b>

### Install using Executable (recommended)

1. Download and install [ViGEmBus](https://github.com/nefarius/ViGEmBus/releases/latest) _This is the driver that emulates the X360 controller_

2. Download and run [AEB](https://github.com/ferocioustoast/AEB/releases/latest)


### Install using Python

_Assuming you already have [Python](https://www.python.org/downloads/) installed, and added to PATH._

1. Download AEB.py and requirements.txt from this repo.

2. Install the requirements with Powershell/CMD.
   ```sh
   python -m pip install -r .\requirements.txt
   ```
3. During installation, vgamepad will launch an installer for ViGEm; install that as well.

### Usage

1. Run AEB with Powershell/CMD or by double-clicking AEB.

2. Select the output device you want the audio to play on.

3. Pressing 't' will start a customizable loop changing the left and right channel volumes, or use a program such as [Intiface](https://intiface.com/central/) that can connect to the X360 controller and control the rumble.

4. As the virtual controller receives rumble, the left and right channels volumes will change depending on the rumble. Play around with the hotkeys shown or edit the py file directly to customize the feeling.

#### Main Menu Hotkeys

![screenshot](https://raw.githubusercontent.com/ferocioustoast/AEB/master/imgs/menu.PNG)

- v  : Toggles showing left and right volume changes
- vv : Toggles showing the motor states
- x  : Presses the 'start' button four times on the virtual controller
- h  : Enables the old way of switching channels at _half_rum_
- e  : Allows the left channel volume to grow to _lmaxvol_ when over _half_rum_
- p  : Pauses the sound
- t  : Start looping though a customizable range
  -  rs : Enable random changes to speed, increasing over time. _max speed in ~15 minutes_
  -  rr : Enable random changes to min/max loop. _can edit ranges directly in py file_
  -  s  : Change the amount of time, _in seconds,_ to take per loop.
  -  ma : Change the maximum motor number of the loop. _highest is 255_
  -  mi : Change the minimum motor number of the loop. _lowest is 0_
- l  : Opens any programs manually added to the list in AEB.py.
- c  : Enters the control menu _(see control menu hotkeys below)_.
- q  : Closes the program

#### Control Menu Hotkeys

![screenshot](https://raw.githubusercontent.com/ferocioustoast/AEB/master/imgs/control_menu.PNG)

- a  : Multiply the sinewave by the entered number.
- f  : Edit the frequency _(in hertz)_ of the sinewave.
- mi : Change the left/right or both channels minimum volumes; they must be in between 0.0 and 1.0.
- ma : Change the left/right or both channels maximum volumes; they must be in between 0.0 and 1.0.
- r  : Edit or see ramp-up settings
- rd : Edit or see ramp-down settings
- c  : Leave the control menu
- p  : Pauses the sound