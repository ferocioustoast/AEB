# Audio Estim Bridge
Using python with vgamepad to emulate an X360 controller and turn received vibrations into sinewaves with pygame mixer. This will only work on Windows as vgamepad only works on Windows.

## WARNING: This program may unexpectedly shock you. The creator is not a professional software developer, audio engineer, or electrical engineer and has no idea what they are doing. Use at your own risk. You have been warned!

### Installation

1. Download AEB.py and requirements.txt from this repo

2. Install the requirements with Powershell/CMD
   ```sh
   python -m pip install -r .\requirements.txt
   ```
3. During install vgamepad will launch an installer for ViGEm, install that aswell.

### Usage

1. Run AEB.py with Powershell/CMD or by double clicking AEB.py

2. Select the output device you want the audio to play on.

4. Use a program such as https://intiface.com/central/ that can connect to the X360 controller and control the vibrations.

5. Play around with the hotkeys shown in the window or edit the file directly until the resulting sounds are satisfactory.
