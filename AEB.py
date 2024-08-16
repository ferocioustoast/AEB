import pygame._sdl2.audio as sdl2_audio
from pygame import mixer
import numpy as np
import threading
import platform
import time
import yaml
import os
try:
    import vgamepad as vg
    controller_available = True
except Exception:
    if platform.system() == 'Windows':
        os.system('cls')
    else:
        os.system('clear')
    if platform.system() == 'Windows':
        n = input("ViGEmBus driver not found, Would you like to open the download page? [y]es [n]o: ")
        os.system('cls')
        if n.lower() == 'y' or n == '' or n.lower() == 'yes':
            os.startfile("https://github.com/nefarius/ViGEmBus/releases/latest")
        n = input("Would you like to continue with no controller functions? [y]es [n]o: ")
        if n.lower() == 'y' or n == '' or n.lower() == 'yes':
            controller_available = False
        else:
            quit()
    else:
        controller_available = False

config_file = 'config.yaml'

settings = {
    'sinewave_freqs': [987],  # Hz, frequency to play sinewave at

    # Volume can be set between 0.0 and 1.0
    'left_max_vol': 0.8,
    'left_min_vol': 0.4,
    'right_max_vol': 0.8,
    'right_min_vol': 0.4,

    'amplitude': 1,  # Multiplier for sinewave

    'ramp_up_enabled': True,  # Enable volume ramp up on inactivity
    'ramp_up_time': 0.3,  # Time in seconds for volume ramp up
    'ramp_up_steps': 20,  # Number of steps in volume ramp up
    'idle_time_before_ramp_up': 0.1,  # Seconds of inactivity before ramp up

    'ramp_down_enabled': True,  # Enable volume ramp down on inactivity
    'ramp_down_time': 0.3,  # Time in seconds for volume ramp down
    'ramp_down_steps': 20,  # Number of steps in volume ramp down
    'idle_time_before_ramp_down': 0.5,  # Seconds of inactivity before ramp down

    'loop_transition_time': 0.5,  # Time to go between min_loop, max_loop
    'loop_ranges': {  # ranges will randomly be + or - 0 through 38
        0: [1, 255],
        1: [1, 55],
        2: [201, 255],
    },

    'randomize_loop_speed': False,  # Randomly increase speed, sometimes lowering
    'delay_loop_speed': False,  # Delay starting random loop speed
    'loop_speed_delay': 60,  # Time in seconds to delay loop speed

    'randomize_loop_range': False,  # Randomize loop range using loop_ranges

    'min_loop': 1,  # Minimum value for loop
    'max_loop': 255,  # Maximum value for loop

    'slowest_loop_speed': 2,  # Time in seconds for minimum loop transition

    'channel_switch_half_way': False,  # Enable channel switch at motor midpoint
    'extend_lvol': False,  # Increase lvol after half_rum, otherwise stay at lminvol

    'print_volumes': False,  # Print volume changes to console
    'print_motor_states': False,  # Print motor states to console

    'always_set_volume': False,  # Set zero volume when motor is zero

    'launch_programs_on_select': False,  # Launch programs on device selection
    'program_list': [  # list of programs to launch
        # r'C:',  # opens C drive
        # r'C:\Windows\notepad.exe'  # opens notepad exe directly
    ]
}

looping = False  # whether we are looping

buttons = False  # Press start button four times
pause = False  # Pause all sounds
warning = True  # Display warning message on entering control menu

sounds = []  # List for storing sinewave sounds

# Changing half_rum can lead to math problems
half_rum = 127.5  # Used to switch channels, Calculate steps: 127.5

sample_rate = 44100  # Sample rate for sinewave: 44100

# Empty string to store selected audio device in
did = ''

zero_time = 0  # Time when hit zero
last_zero = True  # Last motor at zero
old_motor = 0  # Motor for checking ramp_down
ramp_start = 0  # Time for triggering ramp_down


def create_config_file():
    with open(config_file, 'w') as f:
        yaml.dump(settings, f)


def load_config():
    global settings
    default_settings = settings
    try:
        with open(config_file, 'r') as f:
            settings = yaml.safe_load(f)
        if not settings:
            # Has config file but it's empty
            settings = {}
        for _ in default_settings:
            if _ not in settings:
                print(f'Added new variable "{_}" to {config_file}')
                update_config(_, default_settings[_])
        for _ in dict(settings):
            if _ not in default_settings:
                settings.pop(_)
                print(f'Removed unused variable "{_}" from {config_file}')
                create_config_file()
    except FileNotFoundError:
        print(f'Config file not found, creating new {config_file}.')
        create_config_file()


def update_config(var_name, new_value):
    global settings
    settings[var_name] = new_value
    with open(config_file, 'w') as f:
        yaml.dump(settings, f)


def open_programs(programs):
    if programs != []:
        for program in programs:
            try:
                os.startfile(program)
            except TypeError:
                print(f"Couldn't open {program}")
    else:
        print("\nNo programs were added to the program list. \
Please add them manually to the config file.\nFor example the config \
file would look like:\n\nprogram_list:\n- 'C:'\n- 'C:\\Windows\\notepad.exe'")


def spam_buttons():
    # Press the start button on the controller a few times
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
    if settings['channel_switch_half_way']:
        if motor >= half_rum:
            lvol = lminvol
        else:
            lvol = lmaxvol + (lminvol - lmaxvol) * motor / half_rum
    else:
        lvol = lmaxvol + (lminvol - lmaxvol) * motor / 255
    lvol = max(lminvol, min(lmaxvol, lvol))
    if settings['print_volumes']:
        print(f'Left Volume: {lvol}')
    return lvol


def find_r_vol(motor, rminvol, rmaxvol):
    # Calculate the needed right volume
    # Start at rminvol and increase to rmaxvol
    if settings['channel_switch_half_way']:
        if motor < half_rum:
            rvol = rminvol
        else:
            rvol = rminvol + (rmaxvol - rminvol) * (motor - half_rum) / half_rum
    if settings['extend_lvol']:
        rvol = rmaxvol + (rminvol - rmaxvol) * (motor - half_rum) / half_rum
    else:
        rvol = rminvol + (rmaxvol - rminvol) * motor / 255
    rvol = max(rminvol, min(rmaxvol, rvol))
    if settings['print_volumes']:
        print(f'Right Volume: {rvol}')
    return rvol


def generate_sinewave(frequency, sample_rate, amp):
    sinewave = np.sin(2 * np.pi * np.arange(sample_rate)
                      * float(frequency) / sample_rate).astype(np.float32) * amp
    return sinewave


def generate_squarewave(frequency, sample_rate, amp):
    squarewave = np.sign(np.sin(2 * np.pi * np.arange(sample_rate)
                                * float(frequency) / sample_rate)) * amp
    return squarewave


def select_device():
    global did
    devs = sdl2_audio.get_audio_device_names()
    mixer.quit()
    i = 0
    print('**Important Warning:**')
    print('Please use a dedicated audio device for your estim device.')
    print('If you are using only one audio device, ALL sounds will go to your estim device.')
    print('\n')
    while 1 == 1:
        for i, d in enumerate(devs):
            print(f'{i} : {d}')
        try:
            print('\n')
            n = int(input('Enter the number matching the audio device your estim device is connected to: '))
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
    if settings['print_volumes']:
        print(f'Ramping volume {ramp}...')
    if ramp == 'up':
        for i in range(round(settings['ramp_up_steps']) + 1):
            if settings['print_volumes']:
                print(f'{(i / settings["ramp_up_steps"])} / 1.0')
            for sound in sounds:
                mixer.Sound.set_volume(sound, (i / settings['ramp_up_steps']))
            time.sleep(settings['ramp_up_time'] / settings['ramp_up_steps'])
    elif ramp == 'down':
        for i in reversed(range(round(settings['ramp_down_steps']) + 1)):
            if settings['print_volumes']:
                print(f'{(i / settings["ramp_down_steps"])} / 1.0')
            for sound in sounds:
                mixer.Sound.set_volume(sound, (i / settings['ramp_down_steps']))
            time.sleep(settings['ramp_down_time'] / settings['ramp_down_steps'])


def ramp_check(motor):
    # Check if the motor is still at old_motor after waiting inactive_time_d
    global last_zero
    if old_motor == motor and time.time() - ramp_start >= settings['idle_time_before_ramp_down']:
        ramp_volume('down')
        last_zero = True


def volume_from_motor(motor):
    # Set the volume of the left and right channels based on the motor value
    global zero_time
    global last_zero
    global old_motor
    global ramp_start

    if not check_rumble(motor):
        if settings['ramp_up_enabled']:
            zero_time = time.time()
            last_zero = True
        if not settings['always_set_volume']:
            pass
        else:
            for i in range(0, len(sounds)):
                mixer.Channel(i).set_volume(0.0, 0.0)
        return

    if settings['ramp_down_enabled'] and not settings['ramp_up_enabled']:
        for sound in sounds:
            mixer.Sound.set_volume(sound, 1.0)

    lvol = find_l_vol(motor, settings['left_min_vol'], settings['left_max_vol'])
    rvol = find_r_vol(motor, settings['right_min_vol'], settings['right_max_vol'])

    if settings['ramp_up_enabled'] and last_zero and time.time() - zero_time >= settings['idle_time_before_ramp_up']:
        volume_ramp_up_thread = threading.Thread(target=ramp_volume, args=('up',))
        for sound in sounds:
            mixer.Sound.set_volume(sound, 0.0)
        volume_ramp_up_thread.start()

    for i in range(0, len(sounds)):
        mixer.Channel(i).set_volume(lvol, rvol)
    last_zero = False

    if settings['ramp_down_enabled']:
        old_motor = motor
        ramp_start = time.time()
        ramp_check_timer = threading.Timer(settings['idle_time_before_ramp_down'], ramp_check, args=(motor,))
        ramp_check_timer.start()


def rumble(client, target, large_motor, small_motor, led_number, user_data):
    """
    Callback function triggered at each received state change
    :param small_motor: integer in [0, 255]
    """
    if settings['print_motor_states']:
        print(f'Small Motor: {small_motor}, Large Motor: {large_motor}')

    motor = max(small_motor, large_motor)

    volume_from_motor(motor)


def delay_speed(delay=settings['delay_loop_speed']):
    time.sleep(0.1)
    time.sleep(delay)
    print('Enabling random loop speed...')
    settings['randomize_loop_speed'] = True


def loop_motor():
    multi = 0.90
    print("Starting Loop...")

    if settings['delay_loop_speed']:
        settings['randomize_loop_speed'] = False
        delay_speed_thread = threading.Thread(target=delay_speed)
        delay_speed_thread.start()

    if settings['ramp_up_enabled']:
        volume_ramp_up_thread = threading.Thread(target=ramp_volume, args=('up',))
        for sound in sounds:
            mixer.Sound.set_volume(sound, 0.0)
        volume_ramp_up_thread.start()

    while not loop.is_set():
        for i in range(settings['min_loop'], settings['max_loop'] + 1):
            if loop.is_set():
                break
            total_steps = settings['max_loop'] - settings['min_loop'] + 1
            step_time = settings['loop_transition_time'] / total_steps
            volume_from_motor(i)
            timer = time.time()
            while timer + step_time > time.time():
                pass

        for i in reversed(range(settings['min_loop'], settings['max_loop'] + 1)):
            if loop.is_set():
                break
            total_steps = settings['max_loop'] - settings['min_loop'] + 1
            step_time = settings['loop_transition_time'] / total_steps
            volume_from_motor(i)
            timer = time.time()
            while timer + step_time > time.time():
                pass

        if settings['randomize_loop_range']:
            # Randomly change the loop min/max using set {loop_ranges}
            import random
            if random.randint(1, 10) == 8:
                rand_range = random.choice(settings['loop_ranges'])
                minchange = rand_range[0]
                maxchange = rand_range[1]
                if random.randint(1, 2) == 1:
                    if random.randint(1, 2) == 1:
                        minchange += random.randint(1, 20)
                    if random.randint(1, 2) == 1:
                        maxchange += random.randint(1, 20)
                    if random.randint(1, 2) == 1:
                        minchange -= random.randint(1, 20)
                    if random.randint(1, 2) == 1:
                        maxchange -= random.randint(1, 20)

                # Make sure min/max loop 1-255
                minchange = max(minchange, 1)
                minchange = min(minchange, 255)
                maxchange = min(maxchange, 255)
                maxchange = max(maxchange, 1)

                settings['min_loop'] = minchange
                settings['max_loop'] = maxchange

        if settings['randomize_loop_speed']:
            import random
            settings['loop_transition_time'] *= multi

            # Randomly increase the loop time with a decreasing probability.
            if random.randint(1, 2) == 1:
                multi -= 0.001
                if random.randint(1, 10) == 1:
                    settings['loop_transition_time'] += 0.001
                elif random.randint(1, 10) == 2:
                    settings['loop_transition_time'] += 0.01
                elif random.randint(1, 10) == 3:
                    settings['loop_transition_time'] += 0.1
                elif random.randint(1, 10) == 4:
                    settings['loop_transition_time'] += 1.0

                # Set loop_transition_time to a fast speed after reaching low multi
                if multi < 0:
                    settings['loop_transition_time'] = 0.0000001

            settings['loop_transition_time'] = min(settings['loop_transition_time'], settings['slowest_loop_speed'])

    loop.clear()
    print("Ending Loop...")


def print_help():
    print('\n')
    if not controller_available:
        print('Running without controller functions\n')

    if settings['print_volumes']:
        print('v : Disable printing volume changes')
    else:
        print('v : Enable printing volume changes')
    if settings['print_motor_states']:
        print('vv: Disable printing motor states')
    else:
        print('vv: Enable printing motor states')

    if controller_available:
        print('x : Press start on virtual controller')

    if settings['channel_switch_half_way']:
        print('h : Disable switching channels at half motor')
    else:
        print('h : Enable switching channels at half motor')

    if settings['extend_lvol']:
        print('e : Disable extending lvol over half motor')
    else:
        print('e : Enable extending lvol over half motor')

    if looping:
        print('t : Stop looping')
        print(f"  s: Change loop time (current: {round(settings['loop_transition_time'], 6)})")
        print(f"  ma: Change max loop (current: {settings['max_loop']})")
        print(f"  mi: Change min loop (current: {settings['min_loop']})")
        if settings['randomize_loop_speed']:
            print('  rs : Disable random loop speed')
        else:
            print('  rs : Enable random loop speed')
        if not settings['delay_loop_speed']:
            print('  rsd : Enable delayed random loop speed')
        if settings['randomize_loop_range']:
            print('  rr : Disable random loop range')
        else:
            print('  rr : Enable random loop range')
    else:
        if settings['delay_loop_speed']:
            print('t : Start looping (delayed speed)')
        else:
            print('t : Start looping')

    if pause:
        print('p : Unpause all sounds')
    else:
        print('p : Pause all sounds')

    if settings['program_list']:
        print('l : Launch programs')

    print('c : Enter control menu')
    print('q : Quit program')


def print_controls():
    print('\n')
    if warning:
        print('BE CAREFUL CHANGING THESE WHILE HOOKED UP!\n')

    print(f"a : Edit amplification (current: {settings['amplitude']})")
    print(f"f : Edit frequency (current: {settings['sinewave_freqs']})")
    print(f"mi: Edit left (current: {settings['left_min_vol']}) and/or right (current: {settings['right_min_vol']}) minimum volume")
    print(f"ma: Edit left (current: {settings['left_max_vol']}) and/or right (current: {settings['right_max_vol']}) maximum volume")

    if settings['ramp_up_enabled']:
        print("r : Edit ramp up settings (on)")
    else:
        print("r : Edit ramp up settings (off)")

    if settings['ramp_down_enabled']:
        print("rd: Edit ramp down settings (on)")
    else:
        print("rd: Edit ramp down settings (off)")

    print('c : Leave the control menu')
    print('l : Load a config file')
    print('s : Save the current options to a config file')

    if pause:
        print('p : Unpause all sounds')
    else:
        print('p : Pause all sounds')


if __name__ == '__main__':
    # setup mixer
    if platform.system() == 'Windows':
        os.system('cls')
    else:
        os.system('clear')
    try:
        mixer.init(size=32)
    except Exception:
        print('Could not initialize audio mixer. \
Do you have any active audio devices?')
        input()

    # Load/build config before setting mixer.Sound()
    load_config()
    print('\n')

    for wave in settings['sinewave_freqs']:
        sound = mixer.Sound(generate_sinewave(wave, sample_rate, settings['amplitude']))
        sounds.append(sound)

    select_device()
    mixer.set_num_channels(len(sounds))
    if settings['launch_programs_on_select']:
        open_programs(settings['program_list'])

    # set volume to zero, play sound
    for i in range(0, len(sounds)):
        mixer.Channel(i).set_volume(0.0, 0.0)
    for sound in sounds:
        sound.play(-1)

    # start 360 controller, set rumble callback
    if controller_available:
        gamepad = vg.VX360Gamepad()

        gamepad.register_notification(callback_function=rumble)

    while 1 == 1:
        print_help()
        n = input("\n")
        if n == 'v':
            if settings['print_volumes'] is True:
                settings['print_volumes'] = False
                print('Not printing volumes')
            else:
                settings['print_volumes'] = True
                print('Printing volumes')
        elif n == 'vv':
            if settings['print_motor_states'] is True:
                settings['print_motor_states'] = False
                print('Not printing motor states')
            else:
                settings['print_motor_states'] = True
                print('Printing motor states')
        elif n == 'x' and controller_available:
            print('Pressing start four times...')
            spam_buttons()
        elif n == 'h':
            if settings['channel_switch_half_way'] is True:
                settings['channel_switch_half_way'] = False
                print('Not switching at half motor')
            else:
                settings['channel_switch_half_way'] = True
                print('Switching at half motor')
        elif n == 'e':
            if settings['extend_lvol'] is True:
                settings['extend_lvol'] = False
                print("Not extending left volume")
            else:
                settings['extend_lvol'] = True
                print("Extending left volume")
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
            open_programs(settings['program_list'])
        elif n == 'c':
            while 1 == 1:
                print_controls()
                n = input("\n")
                if n == 'f':
                    try:
                        print(f'\n***Multiple frequencies may cause painful clipping***')
                        print(f'***Lowering amplification or max volume may help***')
                        print(f'\nCurrent frequencies: {settings["sinewave_freqs"]}')
                        n = input("Enter desired frequencies (space seperated): ")
                        if not n.strip().replace(" ", "").isdigit():
                            print('\nNumbers only (separated by spaces)')
                            continue
                        print(f'Setting frequencies to {n}...')
                        mixer.stop()
                        frequencies = [int(freq) for freq in n.split()]
                        settings['sinewave_freqs'] = frequencies
                        sounds = []
                        for wave in settings['sinewave_freqs']:
                            sound = mixer.Sound(generate_sinewave(wave, sample_rate, settings['amplitude']))
                            sounds.append(sound)
                        mixer.set_num_channels(len(sounds))
                        for i in range(0, len(sounds)):
                            mixer.Channel(i).set_volume(0.0, 0.0)
                        for sound in sounds:
                            sound.play(-1)
                    except ValueError:
                        print('\n')
                        print('Numbers only')
                elif n == 'a':
                    try:
                        print(f'Current amplitude: {settings["amplitude"]}')
                        n = input("Enter desired amplitude: ")
                        print(f'Setting amplitude to {n}...')
                        mixer.stop()
                        settings['amplitude'] = float(n)
                        sounds = []
                        for wave in settings['sinewave_freqs']:
                            sound = mixer.Sound(generate_sinewave(wave, sample_rate, settings['amplitude']))
                            sounds.append(sound)
                        mixer.set_num_channels(len(sounds))
                        for i in range(0, len(sounds)):
                            mixer.Channel(i).set_volume(0.0, 0.0)
                        for sound in sounds:
                            sound.play(-1)
                    except ValueError:
                        print('\n')
                        print('Numbers only')
                elif n == 'mi':
                    print('[l]eft [r]ight or [b]oth sides?')
                    n = input("")
                    try:
                        if n == 'l':
                            print(f'Current left minvol: {settings["left_min_vol"]}')
                            n = input("Enter desired left minvol between 0.0 and 1.0: ")
                            assert float(n) >= 0.0 and float(n) <= 1.0
                            print(f'Setting left minvol to {n}...')
                            settings['left_min_vol'] = float(n)
                        elif n == 'r':
                            print(f'Current right minvol: {settings["right_min_vol"]}')
                            n = input("Enter desired right minvol between 0.0 and 1.0: ")
                            assert float(n) >= 0.0 and float(n) <= 1.0
                            print(f'Setting right minvol to {n}...')
                            settings['right_min_vol'] = float(n)
                        elif n == 'b':
                            print(f'Current left minvol: {settings["left_min_vol"]}')
                            print(f'Current right minvol: {settings["right_min_vol"]}')
                            n = input("Enter desired minvol between 0.0 and 1.0: ")
                            assert float(n) >= 0.0 and float(n) <= 1.0
                            print(f'Setting both minvols to {n}...')
                            settings['left_min_vol'] = float(n)
                            settings['right_min_vol'] = float(n)
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
                            print(f'Current left maxvol: {settings["left_max_vol"]}')
                            n = input("Enter desired left maxvol between 0.0 and 1.0: ")
                            assert float(n) >= 0.0 and float(n) <= 1.0
                            print(f'Setting left maxvol to {n}...')
                            settings['left_max_vol'] = float(n)
                        elif n == 'r':
                            print(f'Current right maxvol: {settings["right_max_vol"]}')
                            n = input("Enter desired right maxvol between 0.0 and 1.0: ")
                            assert float(n) >= 0.0 and float(n) <= 1.0
                            print(f'Setting right maxvol to {n}...')
                            settings['right_max_vol'] = float(n)
                        elif n == 'b':
                            print(f'Current left maxvol: {settings["left_max_vol"]}')
                            print(f'Current right maxvol: {settings["right_max_vol"]}')
                            n = input("Enter desired maxvol between 0.0 and 1.0: ")
                            assert float(n) >= 0.0 and float(n) <= 1.0
                            print(f'Setting both maxvols to {n}...')
                            settings['left_max_vol'] = float(n)
                            settings['right_max_vol'] = float(n)
                    except ValueError:
                        print('\n')
                        print('Numbers between 0.0 and 1.0 only')
                    except AssertionError:
                        print('\n')
                        print('Numbers between 0.0 and 1.0 only')
                elif n == 'p':
                    if pause is False:
                        print('Pausing sound')
                        pause = True
                        mixer.pause()
                    else:
                        print('Resuming sound')
                        pause = False
                        mixer.unpause()
                elif n == 'r' or n == 'rd':
                    if n == 'r':
                        _ = 'up'
                    else:
                        _ = 'down'
                    while 1 == 1:
                        print('\n')
                        if settings[f'ramp_{_}_enabled']:
                            print(f'[1] Ramp {_} currently: Enabled')
                        else:
                            print(f'[1] Ramp {_} currently: Disabled')
                        print(f'[2] Ramp {_} time: {settings[f"ramp_{_}_time"]} seconds')
                        print(f'[3] Ramp {_} steps: {settings[f"ramp_{_}_steps"]}')
                        print(f'[4] Idle time before ramp {_}: {settings[f"idle_time_before_ramp_{_}"]} seconds')
                        n = input("\nEnter the number matching the option you wish to change (or press enter to leave): ")
                        if n == '1':
                            if settings[f'ramp_{_}_enabled']:
                                print(f'Disabling ramp {_}')
                                settings[f'ramp_{_}_enabled'] = False
                            else:
                                print(f'Enabling ramp {_}')
                                settings[f'ramp_{_}_enabled'] = True
                        elif n == '2':
                            n = input(f"Enter new ramp {_} time in seconds: ")
                            try:
                                settings[f'ramp_{_}_time'] = float(n)
                                print(f'Setting ramp {_} time to: {float(n)} seconds')
                            except ValueError:
                                print('\n')
                                print('Numbers only')
                        elif n == '3':
                            n = input(f"Enter new number of ramp {_} steps: ")
                            try:
                                settings[f'ramp_{_}_steps'] = float(n)
                                print(f'Setting ramp {_} steps to: {float(n)}')
                            except ValueError:
                                print('\n')
                                print('Numbers only')
                        elif n == '4':
                            n = input("Enter new idle time in seconds: ")
                            try:
                                settings[f'idle_time_before_ramp_{_}'] = float(n)
                                print(f'Setting idle time to: {float(n)} seconds')
                            except ValueError:
                                print('\n')
                                print('Numbers only')
                        else:
                            break
                if n == 'l':
                    configs = []
                    for file in os.listdir(os.getcwd()):
                        if file.endswith('.yaml'):
                            configs.append(file)
                    print('\n')
                    print(f'yaml files found: {configs}')
                    print('\n')
                    n = input(f"Enter name of the yaml config to load (or press Enter to use '{config_file}'): ")
                    if n == '':
                        n = config_file
                    if n.endswith('.yaml'):
                        config_file = n
                    else:
                        config_file = n + '.yaml'
                    print(f'\nLoading {config_file}...')
                    load_config()
                if n == 's':
                    n = input(f"Enter name of the yaml config to update (or press Enter to use '{config_file}'): ")
                    if n.endswith('.yaml'):
                        pass
                    elif n == config_file:
                        pass
                    elif n == '':
                        n = config_file
                    else:
                        n = n + '.yaml'
                    config_file = n
                    print(f'\nUpdating {config_file} with the current settings...')
                    for _ in settings:
                        update_config(_, settings[_])
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
                print(f'Current loop transition time in seconds: {settings["loop_transition_time"]}')
                n = input("Enter desired loop transition time: ")
                print(f'Setting loop transition time to {n}...')
                settings['loop_transition_time'] = float(n)
            except ValueError:
                print('\n')
                print('Numbers only')
        elif n == 'ma' and looping:
            try:
                print(f'Current max loop: {settings["max_loop"]}')
                n = input("Enter desired max loop between 1 and 255: ")
                assert int(n) >= 1 and int(n) <= 255
                print(f'Setting max loop to {n}...')
                settings['max_loop'] = int(n)
            except ValueError:
                print('\n')
                print('Numbers only')
            except AssertionError:
                print('\n')
                print('Numbers between 1 and 255 only')
        elif n == 'mi' and looping:
            try:
                print(f'Current min loop: {settings["min_loop"]}')
                n = input("Enter desired min loop between 0 and 254: ")
                assert int(n) >= 0 and int(n) <= 254
                print(f'Setting min loop to {n}...')
                settings['min_loop'] = int(n)
            except ValueError:
                print('\n')
                print('Numbers only')
            except AssertionError:
                print('\n')
                print('Numbers between 0 and 254 only')
        elif n == 'rs' and looping:
            if not settings['randomize_loop_speed']:
                print(f'Enabling random loop speed')
                settings['randomize_loop_speed'] = True
            else:
                print(f'Disabling random loop speed')
                settings['randomize_loop_speed'] = False
        elif n == 'rsd' and looping:
            n = input(f'Enter time in seconds to delay (press Enter for {settings["loop_speed_delay"]}): ')
            try:
                print(f'Randomizing speed after {n} second delay')
                settings['randomize_loop_speed'] = False
                delay_speed_thread = threading.Thread(target=delay_speed, args=(int(n),))
                delay_speed_thread.start()
            except ValueError:
                print('\n')
                print('Numbers only')
        elif n == 'rr' and looping:
            if not settings['randomize_loop_range']:
                print(f'Enabling random_range')
                settings['randomize_loop_range'] = True
            else:
                print(f'Disabling random_range')
                settings['randomize_loop_range'] = False
        elif n == 'q':
            print('Quitting...')
            mixer.quit()
            break
