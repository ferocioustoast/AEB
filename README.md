# 🔉 Audio Estim Bridge 🌉

## ⚠️ WARNING: This program may unexpectedly shock you. The creator is not a professional software developer, audio engineer, or electrical engineer and has no idea what they are doing. Use at your own risk. You have been warned! ⚠️

### ⚙️ How it Works

The program plays a sinewave and can receive control input in three main ways:

1.  **X360 Controller Emulation:** It emulates an X360 controller (Windows only) that can connect to software like [Intiface](https://intiface.com/central/). This software can then control the "rumble" of the emulated X360 controller.
2.  **Tcode (L0) Websocket Device (WSDM):** It can connect as a WSDM client to compatible software (_If using with Intiface make sure to manually add the websocket device under 'devices' as 'tcode-v03' named 'AEB'_) to receive motor commands directly over a local websocket connection (defaulting to `ws://localhost:54817`, but the port is configurable).
3.  **Tcode (L0) UDP Server:** It can run a UDP server to listen for Tcode (L0) commands sent from compatible software over a local UDP connection (defaulting to port 8000, but this is also configurable).

Using the X360 controller rumble, WSDM motor commands, or UDP Tcode commands, the program dynamically changes the volume of the left and right audio channels of the sinewave.

**Important Note:** X360 controller input and WSDM input are mutually exclusive.
*   When WSDM is enabled, the program will ignore input from the emulated X360 controller.
*   When WSDM is disabled, the program will process input from the emulated X360 controller (if available and ViGEmBus is installed).

As vgamepad uses ViGEmBus, which is Windows only, **the X360 controller emulation only works on Windows.** However, the non-controller functions (like the internal loop, WSDM input, or UDP server input if a compatible Tcode source is available) may still work on other operating systems if used with Python.

### 💻 Install using Executable (Windows only, easiest)

1.  Download and install [ViGEmBus](https://github.com/nefarius/ViGEmBus/releases/latest). _This is the driver that emulates the X360 controller. It is only needed if you intend to use the X360 controller input method._
2.  Download and run the latest [AEB executable](https://github.com/ferocioustoast/AEB/releases/latest).

### 🐍 Install using Python

_Assuming you already have [Python](https://www.python.org/downloads/) installed, and added to PATH._

1.  Clone this repo.
2.  Install the requirements with Powershell/CMD/terminal.
    ```sh
    python -m pip install -r .\requirements.txt
    ```
3.  If you are on Windows and plan to use the X360 controller input, during the installation of `vgamepad`, an installer for ViGEmBus may launch; install that as well. If it doesn't, or if you skipped it, you can install it manually from the link in the "Executable Install" section.

### ▶️ Usage

1.  Run AEB (either the executable or `python AEB.py` if using Python).
2.  Select the output audio device you want the sinewave to play on.
3.  You now have several ways to control the audio stimulation:
    *   **Internal Loop:** Press 't' to start a customizable loop that automatically varies the left and right channel volumes.
    *   **X360 Controller Input (Windows Only):** If ViGEmBus is installed, AEB emulates an X360 controller. Connect a program such as [Intiface](https://intiface.com/central/) to this virtual controller. Intiface (or similar software) can then send rumble commands to AEB.
    *   **Tcode (L0) Websocket Device (WSDM) Input:** Press 'w' to enable WSDM mode. AEB will then prompt you for a port (defaulting to the `wsdm_port` value in `config.yaml`, typically 54817) and attempt to connect to a Tcode websocket server at `ws://localhost:<your_chosen_port>`. Commands from the server will control the audio.
    *   **Tcode (L0) UDP Server Input:** Press 'u' to start the UDP server. AEB will then prompt you for a port (defaulting to the `udp_port` value in `config.yaml`, typically 8000) and listen for Tcode commands on `localhost:<your_chosen_port>`.
4.  As the virtual controller receives rumble, WSDM receives motor commands, UDP Tcode commands are received, or the internal loop progresses, the left and right channel volumes of the sinewave will change. Play around with the hotkeys shown in the menu (or edit the `config.yaml` file generated after the first run) to customize the sensation.

#### ⌨️ Main Menu Hotkeys

![screenshot](https://raw.githubusercontent.com/ferocioustoast/AEB/master/imgs/menu.PNG)

-   `v`  : Toggles printing volume changes to the console.
-   `vv` : Toggles printing motor states (from controller or WSDM) to the console.
-   `x`  : (Windows X360 controller mode only) Presses the 'start' button four times on the virtual controller. This can sometimes help with connection detection in certain software. Ignored if WSDM is active.
-   `h`  : Toggles how channel volumes are calculated (channel_switch_half_way).
-   `e`  : Toggles alternative left channel volume calculation (extend_lvol).
-   `p`  : Pauses or unpauses all sounds.
-   `t`  : Starts or stops the internal looping mode.
    -   `rs` : (When looping) Toggles randomized loop speed changes.
    -   `rsd`: (When looping) Toggles delayed start for random loop speed changes.
    -   `rr` : (When looping) Toggles randomized changes to min/max loop range.
    -   `s`  : (When looping) Change the base time (in seconds) for one full loop cycle.
    -   `ma` : (When looping) Change the maximum motor value (0-255) for the loop.
    -   `mi` : (When looping) Change the minimum motor value (0-255) for the loop.
-   `u`  : Starts or stops the UDP server, listening for Tcode(L0) commands on a custom port. When starting, you'll be prompted for a port (defaulting to `udp_port` in `config.yaml`). _(Note: This is a separate Tcode input method from WSDM)._
-   `w`  : Toggles Tcode (L0) Websocket Device Mode (WSDM).
    *   Enabling WSDM will prompt you for the port to connect to (defaulting to `wsdm_port` in `config.yaml`, typically 54817). AEB will then attempt to connect to `ws://localhost:<your_chosen_port>`.
    *   If WSDM is enabled, input from the X360 virtual controller will be ignored.
    *   If WSDM is disabled, X360 virtual controller input will be processed (if available).
-   `l`  : Opens any programs manually added to the `program_list` in the `config.yaml` file.
-   `c`  : Enters the Control Menu for more detailed settings.
-   `q`  : Quits the program.

#### 🎛️ Control Menu Hotkeys

![screenshot](https://raw.githubusercontent.com/ferocioustoast/AEB/master/imgs/control_menu.PNG)

-   `a`  : Edit the sinewave amplitude (multiplier, default 1.0).
-   `f`  : Edit the frequencies (in Hertz) of the sinewave(s). Multiple frequencies can be specified.
-   `mi` : Change the minimum volume (0.0 to 1.0) for the left, right, or both audio channels.
-   `ma` : Change the maximum volume (0.0 to 1.0) for the left, right, or both audio channels.
-   `r`  : View and edit ramp-up settings (enable, time, steps, idle trigger time).
-   `rd` : View and edit ramp-down settings (enable, time, steps, idle trigger time).
-   `c`  : Exits the Control Menu and returns to the Main Menu.
-   `l`  : Load settings from a specified `.yaml` config file. If the file is not found, a new one with default settings (or based on the filename if it exists) will be used or created.
-   `s`  : Save the current settings to a `.yaml` config file. By default, it saves to the currently loaded config, but you can specify a new filename.
-   `p`  : Pauses or unpauses all sounds (same as in Main Menu).