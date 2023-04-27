# Audio Estim Bridge

## WARNING: This program may unexpectedly shock you. The creator is not a professional software developer, audio engineer, or electrical engineer and has no idea what they are doing. Use at your own risk. You have been warned!

### How it Works

The program plays a sinewave and emulates an X360 controller that can connect to something like [Intiface](https://intiface.com/central/), which can control the rumble of the controller. Using the rumble, we change the volume of the left and right channels of the sinewave depending on the strength of the rumble.

As vgamepad uses ViGEm, which is Windows only, <b>this will only work for Windows.</b>

### Installation

_Assuming you already have [Python](https://www.python.org/downloads/) installed_,

1. Download AEB.py and requirements.txt from this repo.

2. Install the requirements with Powershell/CMD.
   ```sh
   python -m pip install -r .\requirements.txt
   ```
3. During installation, vgamepad will launch an installer for ViGEm; install that as well.

### Usage

1. Run AEB.py with Powershell/CMD or by double-clicking AEB.py.

2. Select the output device you want the audio to play on.

3. Use a program such as [Intiface](https://intiface.com/central/) that can connect to the X360 controller and control the rumble.

4. As the virtual controller receives rumble, the left and right channels volumes will change depending on the rumble. Play around with the hotkeys shown or edit the py file directly to customize the feeling.

#### Hotkeys

![screenshot](https://raw.githubusercontent.com/ferocioustoast/AEB/master/imgs/menu.PNG)

- v  : Toggles showing left and right volume changes
- vv : Toggles showing the motor states
- x  : Presses the 'start' button four times on the virtual controller
- e  : Sets the left channel volume to _lmaxvol_ when over _half_way_ rumble, instead of _lminvol_.
- p  : Pauses the sound
- c  : Enters the control menu _(see control menu hotkeys below)_.
- h  : Shows the help menu
- q  : Closes the program

![screenshot](https://raw.githubusercontent.com/ferocioustoast/AEB/master/imgs/control_menu.PNG)

- f  : Edit the frequency _(in hertz)_ of the sinewave.
- mi : Change the left/right or both channels minimum volumes; they must be in between 0.0 and 1.0.
- ma : Change the left/right or both channels maximum volumes; they must be in between 0.0 and 1.0.
- c  : Leave the control menu
- p  : Pauses the sound