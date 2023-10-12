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
ramp_time = 0.3  # Time, in seconds, to ramp volume up: 0.3
ramp_inc = 20  # Number of steps to take when ramping, more adds more time: 20
inactive_time = 0.1  # Time, in seconds, to be at zero to trigger ramp up: 0.1

ramp_down = True  # Ramp volume down over ramp_time_d
ramp_time_d = 0.3  # Time, in seconds, to ramp volume down: 0.3
ramp_inc_d = 20  # Number of steps to take when ramping more adds more time: 20
inactive_time_d = 0.5  # Time, in seconds, to trigger ramp down: 0.5

random_looping = False  # whether to randomize the speed of the loop
loop_time = 0.5  # Time, in seconds, to go between minloop, maxloop: 0.5
minloop, maxloop = 1, 255  # range to loop through: 1, 255
minloopspeed = 2  # Time, in seconds, for the slowest possible loop_time: 2
looping = False  # whether we are looping

half_way = False  # Old way, use half_rum to switch channels
extended = False  # Increase lvol after half_rum, otherwise stay at lminvol

verbose = False  # spam volumes
very_verbose = False  # Spam motor states

never_zero = False  # Skip setting the volume to 0 if at 0 motor
buttons = False  # Press start button four times
pause = False  # Pause all sounds
warning = True  # Display warning message on entering control menu
launch_programs = False  # auto launch below programs after selecting device

programs = [  # list of programs to launch
    # r'C:',  # opens C drive
    # r'C:\Windows\notepad.exe',  # opens notepad exe directly
]

# Changing half_rum can lead to math problems
half_rum = 127.5  # Used to switch channels, Calculate steps: 127.5

sample_rate = 44100  # Sample rate for sinewave: 44100

# Empty string to store selected audio device in
did = ''

zero_time = 0  # Time when hit zero
last_zero = True  # Last motor at zero
old_motor = 0  # Motor for checking ramp_down
ramp_start = 0  # Time for triggering ramp_down


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
        if motor >= half_rum:
            lvol = lminvol
        else:
            lvol = lmaxvol + (lminvol - lmaxvol) * motor / half_rum
    if extended and motor > half_rum:
        lvol = lminvol + (lmaxvol - lminvol) * motor / 255
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
        if motor < half_rum:
            rvol = rminvol
        else:
            rvol = rminvol + (rmaxvol - rminvol) * (motor - half_rum) / half_rum
    else:
        rvol = rminvol + (rmaxvol - rminvol) * motor / 255
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
    # Ramp the volume of Sound up or down over the set time
    if verbose:
        print(f'Ramping volume {ramp}...')
    if ramp == 'up':
        for i in range(round(ramp_inc) + 1):
            if verbose:
                print(f'{(i / ramp_inc)} / 1.0')
            mixer.Sound.set_volume(sound, (i / ramp_inc))
            time.sleep(ramp_time / ramp_inc)
    elif ramp == 'down':
        for i in reversed(range(round(ramp_inc_d) + 1)):
            if verbose:
                print(f'{(i / ramp_inc_d)} / 1.0')
            mixer.Sound.set_volume(sound, (i / ramp_inc_d))
            time.sleep(ramp_time_d / ramp_inc_d)


def ramp_check(motor):
    # Check if the motor is still at old_motor after waiting inactive_time_d
    global last_zero
    if old_motor == motor and time.time() - ramp_start >= inactive_time_d:
        ramp_volume('down')
        last_zero = True


def volume_from_motor(motor):
    # Set the volume of the left and right channels based on the motor value
    global zero_time
    global last_zero
    global old_motor
    global ramp_start

    if not check_rumble(motor):
        if ramp_up:
            zero_time = time.time()
            last_zero = True
        if never_zero:
            pass
        else:
            mixer.Channel(0).set_volume(0.0, 0.0)
        return

    if ramp_down and not ramp_up:
        mixer.Sound.set_volume(sound, 1.0)

    lvol = find_l_vol(motor, lminvol, lmaxvol)
    rvol = find_r_vol(motor, rminvol, rmaxvol)

    if ramp_up and last_zero and time.time() - zero_time >= inactive_time:
        volume_ramp_up_thread = threading.Thread(target=ramp_volume, args=('up',))
        mixer.Sound.set_volume(sound, 0.0)
        volume_ramp_up_thread.start()

    mixer.Channel(0).set_volume(lvol, rvol)
    last_zero = False

    if ramp_down:
        old_motor = motor
        ramp_start = time.time()
        ramp_check_timer = threading.Timer(inactive_time_d, ramp_check, args=(motor,))
        ramp_check_timer.start()


def rumble(client, target, large_motor, small_motor, led_number, user_data):
    """
    Callback function triggered at each received state change
    :param small_motor: integer in [0, 255]
    """
    if very_verbose:
        print(f'small_motor: {small_motor}, large_motor: {large_motor}')

    motor = max(small_motor, large_motor)

    volume_from_motor(motor)


def loop_motor():
    global loop_time
    multi = 0.90
    print("Starting Loop...")
    if ramp_up:
        volume_ramp_up_thread = threading.Thread(target=ramp_volume, args=('up',))
        mixer.Sound.set_volume(sound, 0.0)
        volume_ramp_up_thread.start()

    while not loop.is_set():
        for i in range(minloop, maxloop + 1):
            if loop.is_set():
                break
            total_steps = maxloop - minloop + 1
            step_time = loop_time / total_steps
            volume_from_motor(i)
            timer = time.time()
            while timer + step_time > time.time():
                pass

        for i in reversed(range(minloop, maxloop + 1)):
            if loop.is_set():
                break
            total_steps = maxloop - minloop + 1
            step_time = loop_time / total_steps
            volume_from_motor(i)
            timer = time.time()
            while timer + step_time > time.time():
                pass

        if random_looping:
            import random
            loop_time *= multi

            # Randomly increase the loop time with a decreasing probability.
            if random.randint(1, 2) == 1:
                multi -= 0.001
                if random.randint(1, 10) == 1:
                    loop_time += 0.001
                elif random.randint(1, 10) == 2:
                    loop_time += 0.01
                elif random.randint(1, 10) == 3:
                    loop_time += 0.1
                elif random.randint(1, 10) == 4:
                    loop_time += 1.0

                # Set loop_time to a fast speed after reaching low multi
                if multi < 0:
                    loop_time = 0.0000001

            loop_time = min(loop_time, minloopspeed)

    loop.clear()
    print("Ending Loop...")


def print_help():
    print('\n')
    if verbose:
        print('v : Toggle verbose mode [on] and off')
    else:
        print('v : Toggle verbose mode on and [off]')
    if very_verbose:
        print('vv: Toggle very verbose mode [on] and off')
    else:
        print('vv: Toggle very verbose mode on and [off]')
    print('x : Spam buttons')
    if half_way:
        print('h : Toggle half_way mode [on] and off')
    else:
        print('h : Toggle half_way mode on and [off]')
    if extended:
        print('e : Toggle extended [on] and off')
    else:
        print('e : Toggle extended on and [off]')
    if looping:
        print('t : Stop looping')
        print(f's : Change loop time [{round(loop_time, 6)}] of loop')
        print(f'ma : Change max loop [{maxloop}]')
        print(f'mi : Change min loop [{minloop}]')
        if random_looping:
            print('rs : Toggle random speed [on] and off')
        else:
            print('rs : Toggle random speed on and [off]')
    else:
        print('t : Start looping')
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
    if ramp_down:
        print('rd : Edit ramp_down [on] settings')
    else:
        print('rd : Edit ramp_down [off] settings')
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
                        frequency = int(n)
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
        elif n == 't':
            if not looping:
                looping = True
                loop = threading.Event()
                random_thread = threading.Thread(target=loop_motor)
                random_thread.start()
            else:
                loop.set()
                looping = False
        elif n == 's' and looping:
            try:
                print(f'Current loop time: {loop_time}')
                n = input("Enter desired loop time: ")
                print(f'Setting loop time to {n}...')
                loop_time = float(n)
            except ValueError:
                print('\n')
                print('Numbers only')
        elif n == 'ma' and looping:
            try:
                print(f'Current max loop: {maxloop}')
                n = input("Enter desired max loop between 1 and 255: ")
                assert int(n) >= 1 and int(n) <= 255
                print(f'Setting max loop to {n}...')
                maxloop = int(n)
            except ValueError:
                print('\n')
                print('Numbers only')
            except AssertionError:
                print('\n')
                print('Numbers between 1 and 255 only')
        elif n == 'mi' and looping:
            try:
                print(f'Current min loop: {minloop}')
                n = input("Enter desired min loop between 0 and 254: ")
                assert int(n) >= 0 and int(n) <= 254
                print(f'Setting min loop to {n}...')
                minloop = int(n)
            except ValueError:
                print('\n')
                print('Numbers only')
            except AssertionError:
                print('\n')
                print('Numbers between 0 and 254 only')
        elif n == 'rs' and looping:
            if not random_looping:
                print(f'Enabling random_looping')
                random_looping = True
            else:
                print(f'Disabling random_looping')
                random_looping = False
        elif n == 'q':
            print('Quitting...')
            mixer.quit()
            break
