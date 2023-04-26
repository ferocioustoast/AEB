import pygame._sdl2.audio as sdl2_audio
from pygame import mixer
import vgamepad as vg
import numpy as np
import os

frequency = 987  # Frequency to play sinewave at: 987

lmaxvol = 0.5  # Left maximum volume: 0.5
lminvol = 0.4  # Left minimum volume: 0.4
rmaxvol = 0.5  # Right maximum volume: 0.5
rminvol = 0.4  # Right minimum volume: 0.4

extended = False  # If True keep lvol at lmaxvol after half_way, else lminvol
buttons = False  # Press a few buttons on start
verbose = False  # spam volumes
very_verbose = False  # Spam motor states, volumes
pause = False  # Pause all sounds
auto_pause = True  # Pause all sounds when entering the control menu

half_way = 127.5  # Used to switch channels, Calculate steps: 127.5

lstep = (lminvol - lmaxvol) / half_way
rstep = (rminvol - rmaxvol) / half_way

sample_rate = 44100  # Sample rate for sinewave: 44100

sinewave = np.sin(2 * np.pi * np.arange(sample_rate)
                  * frequency / sample_rate).astype(np.float32)

did = ''


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
    # See if we need to do anything
    if small_motor > 0:
        # Motor has rumble
        return True
    else:
        # Motor has no rumble
        return False


def find_l_vol(motor):
    # Calculate the needed left volume
    # Start at lmaxvol and lower to lminvol til halfway
    lvol = lmaxvol
    lvol += lstep * motor
    if lvol > lmaxvol:
        print(f'lvol was too high at: {lvol}')
        lvol = lmaxvol
    elif lvol < lminvol:
        print(f'lvol was too low at: {lvol}')
        lvol = lminvol
    if verbose:
        print(f'lvol: {lvol}')
    return lvol


def find_r_vol(motor):
    # Calculate the needed right volume
    # Start at rminvol and increase to rmaxvol
    rvol = rminvol
    rvol -= rstep * (motor - half_way)
    if rvol > rmaxvol:
        print(f'rvol was too high at: {rvol}')
        rvol = rmaxvol
    elif rvol < rminvol:
        print(f'rvol was too low at: {rvol}')
        rvol = rminvol
    if verbose:
        print(f'rvol: {rvol}')
    return rvol


def select_device():
    global did
    print('\n')
    devs = sdl2_audio.get_audio_device_names()
    mixer.quit()
    i = 0
    while 1 == 1:
        for d in devs:
            print(f'{i} : {d}')
            i += 1
            if i >= len(devs):
                i = 0
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


def rumble(client, target, large_motor, small_motor, led_number, user_data):
    """
    Callback function triggered at each received state change
    :param small_motor: integer in [0, 255]
    """
    sm = small_motor
    if sm < large_motor:
        sm = large_motor
    if check_rumble(sm):
        if sm < half_way:
            mixer.Channel(0).set_volume(find_l_vol(sm), rminvol)
        else:
            if extended:
                mixer.Channel(0).set_volume(lmaxvol, find_r_vol(sm))
            else:
                mixer.Channel(0).set_volume(lminvol, find_r_vol(sm))
    else:
        mixer.Channel(0).set_volume(0.0, 0.0)


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
    if extended:
        print('e : Toggle extended [on] and off')
    else:
        print('e : Toggle extended on and [off]')
    if pause:
        print('p : Toggle the sound on and [off]')
    else:
        print('p : Toggle the sound [on] and off')
    print('c : Enter the control menu')
    print('h : Show this help menu')
    print('q : Quit')


def print_controls():
    print('\n')
    # print(f'f  : Edit the {[frequency]} frequency')
    print(f'mi : Edit the left {[lminvol]} and/or right {[rminvol]} minimum volume')
    print(f'ma : Edit the left {[lmaxvol]} and/or right {[rmaxvol]} maximum volume')
    print('c  : Leave the control menu')
    if pause:
        print('p  : Toggle the sound on and [off]')
    else:
        print('p  : Toggle the sound [on] and off')


if __name__ == '__main__':
    # setup mixer
    os.system('cls')
    mixer.init(size=32)
    mixer.set_num_channels(1)
    sound = mixer.Sound(sinewave)
    select_device()

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
            pass
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
        elif n == 'd':
            select_device()
        elif n == 'c':
            if auto_pause:
                print('Auto Pausing...')
                pause = True
                mixer.pause()
            while 1 == 1:
                print_controls()
                n = input("\n")
                if n == 'f':
                    try:
                        print(f'Current frequency: {frequency}')
                        n = input("Enter desired frequency: ")
                        print(f'Setting frequency to {n}...')
                    except ValueError:
                        print('\n')
                        print('Numbers only')
                if n == 'mi':
                    print('[l]eft [r]ight or [b]oth sides?')
                    n = input("")
                    try:
                        if n == 'l':
                            print(f'Current left minvol: {lminvol}')
                            n = input("Enter desired left minvol: ")
                            print(f'Setting left minvol to {n}...')
                            lminvol = float(n)
                        elif n == 'r':
                            print(f'Current right minvol: {rminvol}')
                            n = input("Enter desired right minvol: ")
                            print(f'Setting right minvol to {n}...')
                            rminvol = float(n)
                        elif n == 'b':
                            print(f'Current left minvol: {lminvol}')
                            print(f'Current right minvol: {rminvol}')
                            n = input("Enter desired minvol: ")
                            print(f'Setting both minvols to {n}...')
                            lminvol = float(n)
                            rminvol = float(n)
                    except ValueError:
                        print('\n')
                        print('Numbers only')
                if n == 'ma':
                    print('[l]eft [r]ight or [b]oth sides?')
                    n = input("")
                    try:
                        if n == 'l':
                            print(f'Current left maxvol: {lmaxvol}')
                            n = input("Enter desired left maxvol: ")
                            print(f'Setting left maxvol to {n}...')
                            lmaxvol = float(n)
                        elif n == 'r':
                            print(f'Current right maxvol: {rmaxvol}')
                            n = input("Enter desired right maxvol: ")
                            print(f'Setting right maxvol to {n}...')
                            rmaxvol = float(n)
                        elif n == 'b':
                            print(f'Current left maxvol: {lmaxvol}')
                            print(f'Current right maxvol: {rmaxvol}')
                            n = input("Enter desired maxvol: ")
                            print(f'Setting both maxvols to {n}...')
                            lmaxvol = float(n)
                            rmaxvol = float(n)
                    except ValueError:
                        print('\n')
                        print('Numbers only')
                elif n == 'h':
                    print(f'Current Half way: {half_way}')
                    n = input("Enter desired half way: ")
                    print(f'Setting half way to {n}...')
                    try:
                        half_way = float(n)
                    except ValueError:
                        print('\n')
                        print('Numbers only')
                elif n == 'p':
                    if pause is False:
                        print('Pausing sound...')
                        pause = True
                        mixer.pause()
                    else:
                        print('Resuming sound...')
                        pause = False
                        mixer.unpause()
                elif n == 'c':
                    break

        elif n == 'q':
            print('Quitting...')
            mixer.quit()
            break
