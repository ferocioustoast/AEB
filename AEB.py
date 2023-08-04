import pygame._sdl2.audio as sdl2_audio
from pygame import mixer
import vgamepad as vg
import numpy as np
import threading
import time
import os

frequency = 987  # Frequency, in hertz, to play sinewave at: 987

# Volume can be set between 0.0 and 1.0
lmaxvol = 0.5  # Left maximum volume: 0.5
lminvol = 0.4  # Left minimum volume: 0.4
rmaxvol = 0.5  # Right maximum volume: 0.5
rminvol = 0.4  # Right minimum volume: 0.4

amp = 1  # Number used to multiply the sinewave by: 1

ramp_up = True  # If at zero for inactive_time, ramp volume up over ramp_time
ramp_time = 0.8  # Time, in seconds, to ramp volume up
ramp_inc = 20  # Number of steps to take when ramping, more adds more time
inactive_time = 0.6  # Time, in seconds, to be at zero to trigger ramp up

ramp_down = True  # Ramp volume down over ramp_time
ramp_time_d = 0.8  # Time, in seconds, to ramp volume down
ramp_inc_d = 20  # Number of steps to take when ramping, more adds more time

half_way = False  # Old way, use half_rum to switch channels
extended = False  # Used with half_way, keep lvol at lmaxvol after half_rum

verbose = False  # spam volumes
very_verbose = False  # Spam motor states

buttons = False  # Press start button four times
pause = False  # Pause all sounds
warning = True  # Display warning message on entering control menu
launch_programs = False  # auto launch below programs after selecting device

programs = [  # list of programs to launch
    # r'C:',  # opens C drive
    # r'C:\Windows\notepad.exe',  # opens notepad exe directly
]

# Changing half_rum can lead to math problems, only used in half_way
half_rum = 127.5  # Used to switch channels, Calculate steps: 127.5

sample_rate = 44100  # Sample rate for sinewave: 44100

# Empty string to store selected audio device in
did = ''

zero_time = 0
last_zero = True


def open_programs(programs):
    if programs != []:
        for program in programs:
            try:
                os.startfile(program)
            except TypeError:
                print(f"Couldn't open {program}")
    else:
        print('No programs were added to the program list. \
Please add them manually to the AEB.py file.')


def spam_buttons():
    # Press the start button on the controller a few times
    import time
    for i in range(4):
        gamepad.press_button(button=vg.XUSB_BUTTON.XUSB_GAMEPAD_START)
        gamepad.update()
        time.sleep(0.5)
        gamepad.release_button(button=vg.XUSB_BUTTON.XUSB_GAMEPAD_START)
        gamepad.update()
        time.sleep(0.5)


def check_rumble(small_motor):
    # Check if we need to do anything
    return small_motor > 0


def find_l_vol(motor, lminvol, lmaxvol):
    # Calculate the needed left volume
    # Start at lmaxvol and lower to lminvol
    if half_way:
        lvol = lmaxvol + (lminvol - lmaxvol) * motor / half_rum
    else:
        lvol = lmaxvol + (lminvol - lmaxvol) * motor / 255
    lvol = max(lminvol, min(lmaxvol, lvol))
    if verbose:
        print(f'lvol: {lvol}')
    return lvol


def find_r_vol(motor, rminvol, rmaxvol):
    # Calculate the needed right volume
    # Start at rminvol and increase to rmaxvol
    if half_way:
        rvol = rminvol + (rmaxvol - rminvol) * (motor - half_rum) / half_rum
    else:
        rvol = rminvol + (rmaxvol - rminvol) * (motor) / 255
    rvol = max(rminvol, min(rmaxvol, rvol))
    if verbose:
        print(f'rvol: {rvol}')
    return rvol


def generate_sinewave(frequency, sample_rate, amp):
    sinewave = np.sin(2 * np.pi * np.arange(sample_rate)
                      * float(frequency) / sample_rate).astype(np.float32)
    sinewave = sinewave * float(amp)
    return sinewave


def select_device():
    global did
    print('\n')
    devs = sdl2_audio.get_audio_device_names()
    mixer.quit()
    i = 0
    while 1 == 1:
        for i, d in enumerate(devs):
            print(f'{i} : {d}')
        try:
            n = int(input("Select desired output device: "))
            print('\n')
            print(f'Connecting to: {devs[n]}')
            print('\n')
            mixer.init(size=32, devicename=devs[n])
            did = devs[n]
            break
        except IndexError:
            print('\n')
            print('Device not in list')
            print('\n')
        except ValueError:
            print('\n')
            print('Numbers only')
            print('\n')


def ramp_volume(ramp):
    if ramp == 'up':
        if verbose:
            print('Ramping volume up...')
        for i in range(round(ramp_inc) + 1):
            if verbose:
                print(f'{(i / ramp_inc)} / 1.0')
            mixer.Sound.set_volume(sound, (i / ramp_inc))
            time.sleep(ramp_time / ramp_inc)
    elif ramp == 'down':
        if verbose:
            print('Ramping volume down...')
        for i in reversed(range(round(ramp_inc_d) + 1)):
            if verbose:
                print(f'{(i / ramp_inc_d)} / 1.0')
            mixer.Sound.set_volume(sound, (i / ramp_inc_d))
            time.sleep(ramp_time_d / ramp_inc_d)


def control_motor(motor):
    global zero_time
    global last_zero
    if not check_rumble(motor):
        if ramp_up:
            zero_time = time.time()
            last_zero = True
        mixer.Channel(0).set_volume(0.0, 0.0)
        return

    lvol = find_l_vol(motor, lminvol, lmaxvol)
    rvol = find_r_vol(motor, rminvol, rmaxvol)

    if ramp_up and last_zero and time.time() - zero_time >= inactive_time:
        volume_ramp_thread = threading.Thread(target=ramp_volume, args=('up',))
        mixer.Sound.set_volume(sound, 0.0)
        volume_ramp_thread.start()

    if not half_way:
        mixer.Channel(0).set_volume(lvol, rvol)
        last_zero = False
            return

        if motor < half_rum:
            mixer.Channel(0).set_volume(lvol, rminvol)
        else:
            if extended:
                mixer.Channel(0).set_volume(lmaxvol, rvol)
            else:
                mixer.Channel(0).set_volume(lminvol, rvol)
        last_zero = False


def rumble(client, target, large_motor, small_motor, led_number, user_data):
    """
    Callback function triggered at each received state change
    :param small_motor: integer in [0, 255]
    """
    if very_verbose:
        print(f'small_motor: {small_motor}, large_motor: {large_motor}')

    motor = max(small_motor, large_motor)

    control_motor(motor)


def print_help():
    print('\n')
    if verbose:
        print('v : Toggle verbose mode [on] and off')
    else:
        print('v : Toggle verbose mode on and [off]')
    if very_verbose:
        print('vv : Toggle very verbose mode [on] and off')
    else:
        print('vv : Toggle very verbose mode on and [off]')
    print('x : Spam buttons')
    if half_way:
        print('h : Toggle half_way mode [on] and off')
    else:
        print('h : Toggle half_way mode on and [off]')
    if half_way:
        if extended:
            print('e : Toggle extended [on] and off')
        else:
            print('e : Toggle extended on and [off]')
    if pause:
        print('p : Toggle the sound on and [off]')
    else:
        print('p : Toggle the sound [on] and off')
    print('l : Launch programs added to py file')
    print('c : Enter the control menu')
    print('q : Close the program')


def print_controls():
    print('\n')
    if warning:
        print('BE CAREFUL CHANGING THESE WHILE HOOKED UP!')
        print('\n')
    print(f'a  : Edit the {[amp]} amplification')
    print(f'f  : Edit the {[frequency]} frequency')
    print(f'mi : Edit the left {[lminvol]} and/or right {[rminvol]} minimum volume')
    print(f'ma : Edit the left {[lmaxvol]} and/or right {[rmaxvol]} maximum volume')
    if ramp_up:
        print('r  : Edit ramp_up [on] settings')
    else:
        print('r  : Edit ramp_up [off] settings')
    print('c  : Leave the control menu')
    if pause:
        print('p  : Toggle the sound on and [off]')
    else:
        print('p  : Toggle the sound [on] and off')


if __name__ == '__main__':
    # setup mixer
    os.system('cls')
    try:
        mixer.init(size=32)
    except Exception:
        print('Could not initialize audio mixer. \
Do you have any active audio devices?')
        input()
    mixer.set_num_channels(1)
    sound = mixer.Sound(generate_sinewave(frequency, sample_rate, amp))
    select_device()
    if launch_programs:
        open_programs(programs)

    # set volume to zero, play sound
    mixer.Channel(0).set_volume(0.0, 0.0)
    sound.play(-1)

    # start 360 controller, set rumble callback
    gamepad = vg.VX360Gamepad()

    gamepad.register_notification(callback_function=rumble)

    while 1 == 1:
        print_help()
        n = input("\n")
        if n == 'v':
            if verbose is True:
                verbose = False
                print("Verbose: Off")
            else:
                verbose = True
                print("Verbose: On")
        elif n == 'vv':
            if very_verbose is True:
                very_verbose = False
                print("Very verbose: Off")
            else:
                very_verbose = True
                print("Very verbose: On")
        elif n == 'x':
            print("Pressing buttons...")
            spam_buttons()
        elif n == 'h':
            if half_way is True:
                half_way = False
                print("half_way: Off")
            else:
                half_way = True
                print("half_way: On")
        elif n == 'e':
            if extended is True:
                extended = False
                print("extended: Off")
            else:
                extended = True
                print("extended: On")
        elif n == 'p':
            if pause is False:
                print('Pausing sound...')
                pause = True
                mixer.pause()
            else:
                print('Resuming sound...')
                pause = False
                mixer.unpause()
        elif n == 'l':
            open_programs(programs)
        elif n == 'c':
            while 1 == 1:
                print_controls()
                n = input("\n")
                if n == 'f':
                    try:
                        print(f'Current frequency: {frequency}')
                        n = input("Enter desired frequency: ")
                        print(f'Setting frequency to {n}...')
                        mixer.stop()
                        frequency = n
                        sound = mixer.Sound(generate_sinewave(frequency, sample_rate, amp))
                        mixer.Channel(0).set_volume(0.0, 0.0)
                        sound.play(-1)
                    except ValueError:
                        print('\n')
                        print('Numbers only')
                elif n == 'a':
                    try:
                        print(f'Current amplitude: {amp}')
                        n = input("Enter desired amplitude: ")
                        print(f'Setting amplitude to {n}...')
                        mixer.stop()
                        amp = float(n)
                        sound = mixer.Sound(generate_sinewave(frequency, sample_rate, amp))
                        mixer.Channel(0).set_volume(0.0, 0.0)
                        sound.play(-1)
                    except ValueError:
                        print('\n')
                        print('Numbers only')
                elif n == 'mi':
                    print('[l]eft [r]ight or [b]oth sides?')
                    n = input("")
                    try:
                        if n == 'l':
                            print(f'Current left minvol: {lminvol}')
                            n = input("Enter desired left minvol between 0.0 and 1.0: ")
                            assert float(n) >= 0.0 and float(n) <= 1.0
                            print(f'Setting left minvol to {n}...')
                            lminvol = float(n)
                        elif n == 'r':
                            print(f'Current right minvol: {rminvol}')
                            n = input("Enter desired right minvol between 0.0 and 1.0: ")
                            assert float(n) >= 0.0 and float(n) <= 1.0
                            print(f'Setting right minvol to {n}...')
                            rminvol = float(n)
                        elif n == 'b':
                            print(f'Current left minvol: {lminvol}')
                            print(f'Current right minvol: {rminvol}')
                            n = input("Enter desired minvol between 0.0 and 1.0: ")
                            assert float(n) >= 0.0 and float(n) <= 1.0
                            print(f'Setting both minvols to {n}...')
                            lminvol = float(n)
                            rminvol = float(n)
                    except ValueError:
                        print('\n')
                        print('Numbers between 0.0 and 1.0 only')
                    except AssertionError:
                        print('\n')
                        print('Numbers between 0.0 and 1.0 only')
                elif n == 'ma':
                    print('[l]eft [r]ight or [b]oth sides?')
                    n = input("")
                    try:
                        if n == 'l':
                            print(f'Current left maxvol: {lmaxvol}')
                            n = input("Enter desired left maxvol between 0.0 and 1.0: ")
                            assert float(n) >= 0.0 and float(n) <= 1.0
                            print(f'Setting left maxvol to {n}...')
                            lmaxvol = float(n)
                        elif n == 'r':
                            print(f'Current right maxvol: {rmaxvol}')
                            n = input("Enter desired right maxvol between 0.0 and 1.0: ")
                            assert float(n) >= 0.0 and float(n) <= 1.0
                            print(f'Setting right maxvol to {n}...')
                            rmaxvol = float(n)
                        elif n == 'b':
                            print(f'Current left maxvol: {lmaxvol}')
                            print(f'Current right maxvol: {rmaxvol}')
                            n = input("Enter desired maxvol between 0.0 and 1.0: ")
                            assert float(n) >= 0.0 and float(n) <= 1.0
                            print(f'Setting both maxvols to {n}...')
                            lmaxvol = float(n)
                            rmaxvol = float(n)
                    except ValueError:
                        print('\n')
                        print('Numbers between 0.0 and 1.0 only')
                    except AssertionError:
                        print('\n')
                        print('Numbers between 0.0 and 1.0 only')
                elif n == 'p':
                    if pause is False:
                        print('Pausing sound...')
                        pause = True
                        mixer.pause()
                    else:
                        print('Resuming sound...')
                        pause = False
                        mixer.unpause()
                elif n == 'r':
                    if ramp_up:
                        print(f'ramp up currently: on')
                    else:
                        print(f'ramp up currently: off')
                    print(f'ramp up over {ramp_time} seconds, over {ramp_inc} steps, if at zero for {inactive_time} seconds')
                    n = input("Toggle [r]amp_up, ramp_[t]ime, ram[p]_inc, [i]nactive_time: ")
                    if n == 'r':
                        if ramp_up:
                            print(r'ramp up now off')
                            ramp_up = False
                        else:
                            print(r'ramp up now on')
                            ramp_up = True
                    elif n == 't':
                        n = input("Enter ramp time in seconds: ")
                        try:
                            print(f'Setting ramp time to: {float(n)} seconds')
                            ramp_time = float(n)
                        except ValueError:
                            print('\n')
                            print('Numbers only')
                    elif n == 'i':
                        n = input("Enter inactive time in seconds: ")
                        try:
                            print(f'Setting inactive time to: {float(n)} seconds')
                            inactive_time = float(n)
                        except ValueError:
                            print('\n')
                            print('Numbers only')
                    elif n == 'p':
                        n = input("Enter number of ramp steps: ")
                        try:
                            print(f'Setting steps to: {float(n)}')
                            ramp_inc = float(n)
                        except ValueError:
                            print('\n')
                            print('Numbers only')
                elif n == 'rd':
                    if ramp_down:
                        print(f'ramp down currently: on')
                    else:
                        print(f'ramp down currently: off')
                    print(f'ramp down over {ramp_time_d} seconds, over {ramp_inc_d} steps, if inactive for {inactive_time_d} seconds')
                    n = input("Toggle [r]amp_down, ramp_[t]ime_d, ram[p]_inc_d, [i]nactive_time_d: ")
                    if n == 'r':
                        if ramp_down:
                            print(r'ramp down now off')
                            ramp_down = False
                        else:
                            print(r'ramp down now on')
                            ramp_down = True
                    elif n == 't':
                        n = input("Enter ramp time in seconds: ")
                        try:
                            print(f'Setting ramp time to: {float(n)} seconds')
                            ramp_time_d = float(n)
                        except ValueError:
                            print('\n')
                            print('Numbers only')
                    elif n == 'i':
                        n = input("Enter inactive time in seconds: ")
                        try:
                            print(f'Setting inactive time to: {float(n)} seconds')
                            inactive_time_d = float(n)
                        except ValueError:
                            print('\n')
                            print('Numbers only')
                    elif n == 'p':
                        n = input("Enter number of ramp steps: ")
                        try:
                            print(f'Setting steps to: {float(n)}')
                            ramp_inc_d = float(n)
                        except ValueError:
                            print('\n')
                            print('Numbers only')
                elif n == 'c':
                    break
        elif n == 'q':
            print('Quitting...')
            mixer.quit()
            break
