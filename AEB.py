import pygame._sdl2.audio as sdl2_audio
from pygame import mixer
import numpy as np
import threading
import websockets
import platform
import asyncio
import json
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
    'sinewave_freqs': [987],  # Hz, frequencies to play sinewave at

    # Volume can be set between 0.0 and 1.0
    'left_max_vol': 0.8,
    'left_min_vol': 0.4,
    'right_max_vol': 0.8,
    'right_min_vol': 0.4,

    'amplitude': 1,  # Multiplier for sinewave

    'udp_port': 8000,  # Port for UDP Tcode server
    'wsdm_port': 54817,  # Port for WSDM Tcode server

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

server_running = False
server_thread = None
stop_event = threading.Event()

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
last_motor = -1

wsdm_enabled = False
wsdm_thread = None


async def wsdm_loop():
    global wsdm_enabled
    try:
        async with websockets.connect(f"ws://localhost:{int(settings['wsdm_port'])}") as websocket:
            handshake = json.dumps({
                "identifier": "AEB",
                "address": "br1d63",
                "version": 0
            })

            await websocket.send(handshake)
            print(f"Connected to WSDM server ws://localhost:{settings['wsdm_port']} as: {handshake}")

            while wsdm_enabled:
                try:
                    response = await websocket.recv(4096)
                    motor = float(f"0.{response.split('L0')[-1].split('I')[0]}") * 255
                    if motor < 1:
                        motor = 1  # "Fix" for device turning off at 0
                    volume_from_motor(motor)

                except Exception as e:
                    if wsdm_enabled:
                        print(f"Error receiving WSDM message: {e}")
                    break
    except Exception as e:
        if wsdm_enabled:
            print(f"Error connecting to WSDM server ws://localhost:{settings['wsdm_port']}: {e}")
    finally:
        if wsdm_enabled:
            print("WSDM loop exited unexpectedly, disabling WSDM.")
            wsdm_enabled = False
        else:
            print("WSDM loop stopped.")


def toggle_wsdm():
    global wsdm_enabled, wsdm_thread, controller_available

    if not wsdm_enabled:
        wsdm_enabled = True
        if controller_available:
            print("Controller input is now paused due to WSDM activation.")
        print(f"Starting Tcode websocket device on port {settings['wsdm_port']}...")
        wsdm_thread = threading.Thread(target=asyncio.run, args=(wsdm_loop(),))
        wsdm_thread.daemon = True
        wsdm_thread.start()
    else:
        wsdm_enabled = False
        print("Stopping Tcode websocket device...")
        if controller_available:
            print("Controller input is now active due to WSDM deactivation.")


def create_config_file():
    with open(config_file, 'w') as f:
        yaml.dump(settings, f)


def load_config():
    global settings
    default_settings = settings.copy()
    try:
        with open(config_file, 'r') as f:
            loaded_settings = yaml.safe_load(f)
        if not loaded_settings:  # Has config file but it's empty
            settings = {}
        else:
            settings = loaded_settings

        for key, value in default_settings.items():
            if key not in settings:
                print(f'Added new variable "{key}" with value "{value}" to config structure.')
                settings[key] = value

        keys_to_remove = [key for key in settings if key not in default_settings]
        if keys_to_remove:
            for key in keys_to_remove:
                settings.pop(key)
                print(f'Removed unused variable "{key}" from {config_file}')
            create_config_file()

    except FileNotFoundError:
        print(f'Config file not found, creating new {config_file} with default settings.')
        settings = default_settings
        create_config_file()
    except yaml.YAMLError:
        print(f'Error parsing {config_file}. Using default settings and creating a new config file.')
        settings = default_settings
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
    elif settings['extend_lvol']:
        rvol = rmaxvol + (rminvol - rmaxvol) * (motor - half_rum) / half_rum
    else:
        rvol = rminvol + (rmaxvol - rminvol) * motor / 255
    rvol = max(rminvol, min(rmaxvol, rvol))
    if settings['print_volumes']:
        print(f'Right Volume: {rvol}')
    return rvol


def generate_sinewave(frequency, sample_rate, amp):
    sinewave = np.sin(2 * np.pi * np.arange(sample_rate)
                      * float(frequency) / sample_rate).astype(np.float32)
    return sinewave * amp


def generate_squarewave(frequency, sample_rate, amp):
    t = np.arange(sample_rate) / sample_rate
    wave = np.where(np.sin(2 * np.pi * frequency * t) >= 0, amp, -amp)
    return wave.astype(np.float32)


def generate_sawtooth(frequency, sample_rate, amp):
    t = np.arange(sample_rate) / sample_rate
    sawtooth = (t * frequency) % 1
    sawtooth = (sawtooth - 0.5) * 2 * amp
    return sawtooth.astype(np.float32)


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
    global last_motor

    if motor == last_motor:
        return  # Skip if motor has not changed

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
        try:
            mixer.Channel(i).set_volume(lvol, rvol)
        except IndexError:
            pass
    last_zero = False

    if settings['ramp_down_enabled']:
        old_motor = motor
        ramp_start = time.time()
        ramp_check_timer = threading.Timer(settings['idle_time_before_ramp_down'], ramp_check, args=(motor,))
        ramp_check_timer.start()

    last_motor = motor


def rumble(client, target, large_motor, small_motor, led_number, user_data):
    """
    Callback function triggered at each received state change
    :param small_motor: integer in [0, 255]
    """
    if wsdm_enabled:
        # If WSDM is active, controller input should be ignored
        return

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


def reload_mixer():
    global sounds
    sounds = []
    for wave in settings['sinewave_freqs']:
        sound = mixer.Sound(generate_sinewave(wave, sample_rate, settings['amplitude']))
        sounds.append(sound)
    mixer.stop()
    mixer.set_num_channels(len(sounds))
    for i in range(0, len(sounds)):
        mixer.Channel(i).set_volume(0.0, 0.0)
    for sound in sounds:
        sound.play(-1)


def loop_udp_server(port):
    global server_running, server_thread, stop_event

    if not server_running:
        stop_event.clear()
        server_thread = threading.Thread(target=start_udp_server, args=(int(port),))
        server_thread.daemon = True
        server_thread.start()
        print(f'UDP server up and listening on localhost:{port}')
        server_running = True
    else:
        stop_event.set()
        import socket
        dummy_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            stop_port = int(settings['udp_port'])
            dummy_sock.sendto(b"stop", ('localhost', stop_port))
        except ValueError:
            print(f"Error: Could not convert configured UDP port '{settings['udp_port']}' to an integer for stopping server.")
        finally:
            dummy_sock.close()
        print("UDP server stopped.")
        server_running = False


def start_udp_server(port):
    import socket

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    server_address = ('localhost', port)
    sock.bind(server_address)

    try:
        while not stop_event.is_set():
            data, address = sock.recvfrom(4096)
            try:
                motor = float(f"0.{data.decode().split('L0')[-1].split('I')[0]}") * 255
                volume_from_motor(motor)
            except (ValueError, IndexError):
                pass
            except socket.timeout:
                pass
    finally:
        sock.close()
        print("Socket closed.")


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

    if server_running:
        print('u : Stop UDP server')
    else:
        print('u : Start UDP server')

    if wsdm_enabled:
        print('w : Disable Tcode(L0) websocket device')
    else:
        print('w : Enable Tcode(L0) websocket device')

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

    select_device()
    if settings['launch_programs_on_select']:
        open_programs(settings['program_list'])

    reload_mixer()

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
            if wsdm_enabled:
                print("Controller input is paused while WSDM is active. Disable WSDM ('w') to use controller.")
            else:
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
                n_control = input("\n")
                if n_control == 'f':
                    try:
                        print(f'\n***Multiple frequencies may cause painful clipping***')
                        print(f'***Lowering amplification or max volume may help***')
                        print(f'\nCurrent frequencies: {settings["sinewave_freqs"]}')
                        freq_input = input("Enter desired frequencies (space seperated): ")
                        if not freq_input.strip().replace(" ", "").isdigit():
                            print('\nNumbers only (separated by spaces)')
                            continue
                        print(f'Setting frequencies to {freq_input}...')
                        frequencies = [int(freq) for freq in freq_input.split()]
                        settings['sinewave_freqs'] = frequencies
                        reload_mixer()
                    except ValueError:
                        print('\n')
                        print('Numbers only')
                elif n_control == 'a':
                    try:
                        print(f'Current amplitude: {settings["amplitude"]}')
                        amp_input = input("Enter desired amplitude: ")
                        print(f'Setting amplitude to {amp_input}...')
                        settings['amplitude'] = float(amp_input)
                        sounds = []
                        reload_mixer()
                    except ValueError:
                        print('\n')
                        print('Numbers only')
                elif n_control == 'mi':
                    side_choice = input('[l]eft [r]ight or [b]oth sides?\n')
                    try:
                        if side_choice == 'l':
                            print(f'Current left minvol: {settings["left_min_vol"]}')
                            vol_input = input("Enter desired left minvol between 0.0 and 1.0: ")
                            assert float(vol_input) >= 0.0 and float(vol_input) <= 1.0
                            print(f'Setting left minvol to {vol_input}...')
                            settings['left_min_vol'] = float(vol_input)
                        elif side_choice == 'r':
                            print(f'Current right minvol: {settings["right_min_vol"]}')
                            vol_input = input("Enter desired right minvol between 0.0 and 1.0: ")
                            assert float(vol_input) >= 0.0 and float(vol_input) <= 1.0
                            print(f'Setting right minvol to {vol_input}...')
                            settings['right_min_vol'] = float(vol_input)
                        elif side_choice == 'b':
                            print(f'Current left minvol: {settings["left_min_vol"]}')
                            print(f'Current right minvol: {settings["right_min_vol"]}')
                            vol_input = input("Enter desired minvol between 0.0 and 1.0: ")
                            assert float(vol_input) >= 0.0 and float(vol_input) <= 1.0
                            print(f'Setting both minvols to {vol_input}...')
                            settings['left_min_vol'] = float(vol_input)
                            settings['right_min_vol'] = float(vol_input)
                    except ValueError:
                        print('\n')
                        print('Numbers between 0.0 and 1.0 only')
                    except AssertionError:
                        print('\n')
                        print('Numbers between 0.0 and 1.0 only')
                elif n_control == 'ma':
                    side_choice = input('[l]eft [r]ight or [b]oth sides?\n')
                    try:
                        if side_choice == 'l':
                            print(f'Current left maxvol: {settings["left_max_vol"]}')
                            vol_input = input("Enter desired left maxvol between 0.0 and 1.0: ")
                            assert float(vol_input) >= 0.0 and float(vol_input) <= 1.0
                            print(f'Setting left maxvol to {vol_input}...')
                            settings['left_max_vol'] = float(vol_input)
                        elif side_choice == 'r':
                            print(f'Current right maxvol: {settings["right_max_vol"]}')
                            vol_input = input("Enter desired right maxvol between 0.0 and 1.0: ")
                            assert float(vol_input) >= 0.0 and float(vol_input) <= 1.0
                            print(f'Setting right maxvol to {vol_input}...')
                            settings['right_max_vol'] = float(vol_input)
                        elif side_choice == 'b':
                            print(f'Current left maxvol: {settings["left_max_vol"]}')
                            print(f'Current right maxvol: {settings["right_max_vol"]}')
                            vol_input = input("Enter desired maxvol between 0.0 and 1.0: ")
                            assert float(vol_input) >= 0.0 and float(vol_input) <= 1.0
                            print(f'Setting both maxvols to {vol_input}...')
                            settings['left_max_vol'] = float(vol_input)
                            settings['right_max_vol'] = float(vol_input)
                    except ValueError:
                        print('\n')
                        print('Numbers between 0.0 and 1.0 only')
                    except AssertionError:
                        print('\n')
                        print('Numbers between 0.0 and 1.0 only')
                elif n_control == 'p':
                    if pause is False:
                        print('Pausing sound')
                        pause = True
                        mixer.pause()
                    else:
                        print('Resuming sound')
                        pause = False
                        mixer.unpause()
                elif n_control == 'r' or n_control == 'rd':
                    ramp_direction = 'up' if n_control == 'r' else 'down'
                    while 1 == 1:
                        print('\n')
                        if settings[f'ramp_{ramp_direction}_enabled']:
                            print(f'[1] Ramp {ramp_direction} currently: Enabled')
                        else:
                            print(f'[1] Ramp {ramp_direction} currently: Disabled')
                        print(f'[2] Ramp {ramp_direction} time: {settings[f"ramp_{ramp_direction}_time"]} seconds')
                        print(f'[3] Ramp {ramp_direction} steps: {settings[f"ramp_{ramp_direction}_steps"]}')
                        print(f'[4] Idle time before ramp {ramp_direction}: {settings[f"idle_time_before_ramp_{ramp_direction}"]} seconds')
                        ramp_edit_choice = input("\nEnter the number matching the option you wish to change (or press enter to leave): ")
                        if ramp_edit_choice == '1':
                            if settings[f'ramp_{ramp_direction}_enabled']:
                                print(f'Disabling ramp {ramp_direction}')
                                settings[f'ramp_{ramp_direction}_enabled'] = False
                            else:
                                print(f'Enabling ramp {ramp_direction}')
                                settings[f'ramp_{ramp_direction}_enabled'] = True
                        elif ramp_edit_choice == '2':
                            time_input = input(f"Enter new ramp {ramp_direction} time in seconds: ")
                            try:
                                settings[f'ramp_{ramp_direction}_time'] = float(time_input)
                                print(f'Setting ramp {ramp_direction} time to: {float(time_input)} seconds')
                            except ValueError:
                                print('\n')
                                print('Numbers only')
                        elif ramp_edit_choice == '3':
                            steps_input = input(f"Enter new number of ramp {ramp_direction} steps: ")
                            try:
                                settings[f'ramp_{ramp_direction}_steps'] = float(steps_input)
                                print(f'Setting ramp {ramp_direction} steps to: {float(steps_input)}')
                            except ValueError:
                                print('\n')
                                print('Numbers only')
                        elif ramp_edit_choice == '4':
                            idle_input = input("Enter new idle time in seconds: ")
                            try:
                                settings[f'idle_time_before_ramp_{ramp_direction}'] = float(idle_input)
                                print(f'Setting idle time to: {float(idle_input)} seconds')
                            except ValueError:
                                print('\n')
                                print('Numbers only')
                        else:
                            break
                if n_control == 'l':
                    configs = []
                    for file in os.listdir(os.getcwd()):
                        if file.endswith('.yaml'):
                            configs.append(file)
                    print('\n')
                    print(f'yaml files found: {configs}')
                    print('\n')
                    config_name_input = input(f"Enter name of the yaml config to load (or press Enter to use '{config_file}'): ")
                    if config_name_input == '':
                        config_name_input = config_file
                    if not config_name_input.endswith('.yaml'):
                        config_name_input += '.yaml'
                    config_file = config_name_input
                    print(f'\nLoading {config_file}...')
                    load_config()
                    reload_mixer()
                if n_control == 's':
                    save_config_name_input = input(f"Enter name of the yaml config to update (or press Enter to use '{config_file}'): ")
                    if save_config_name_input == '':
                        save_config_name_input = config_file
                    if not save_config_name_input.endswith('.yaml'):
                        save_config_name_input += '.yaml'

                    config_file = save_config_name_input
                    print(f'\nUpdating {config_file} with the current settings...')
                    create_config_file()
                    print(f'{config_file} updated.')

                elif n_control == 'c':
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
        elif n == 'u':
            if not server_running:
                udp_port_input = input(f"Enter the UDP port to use (or press Enter to use '{settings['udp_port']}'): ")
                chosen_udp_port = settings['udp_port']
                if udp_port_input == '':
                    pass
                else:
                    try:
                        port_val = int(udp_port_input)
                        if 0 < port_val < 65536:
                            chosen_udp_port = udp_port_input
                        else:
                            print(f"Invalid port number (must be 1-65535). Using current port: {settings['udp_port']}.")
                    except ValueError:
                        print(f"Invalid input. Using current port: {settings['udp_port']}.")

                settings['udp_port'] = chosen_udp_port
                loop_udp_server(chosen_udp_port)
            else:
                loop_udp_server(settings['udp_port'])
        elif n == 's' and looping:
            try:
                print(f'Current loop transition time in seconds: {settings["loop_transition_time"]}')
                loop_time_input = input("Enter desired loop transition time: ")
                print(f'Setting loop transition time to {loop_time_input}...')
                settings['loop_transition_time'] = float(loop_time_input)
            except ValueError:
                print('\n')
                print('Numbers only')
        elif n == 'ma' and looping:
            try:
                print(f'Current max loop: {settings["max_loop"]}')
                max_loop_input = input("Enter desired max loop between 1 and 255: ")
                assert int(max_loop_input) >= 1 and int(max_loop_input) <= 255
                print(f'Setting max loop to {max_loop_input}...')
                settings['max_loop'] = int(max_loop_input)
            except ValueError:
                print('\n')
                print('Numbers only')
            except AssertionError:
                print('\n')
                print('Numbers between 1 and 255 only')
        elif n == 'mi' and looping:
            try:
                print(f'Current min loop: {settings["min_loop"]}')
                min_loop_input = input("Enter desired min loop between 0 and 254: ")
                assert int(min_loop_input) >= 0 and int(min_loop_input) <= 254
                print(f'Setting min loop to {min_loop_input}...')
                settings['min_loop'] = int(min_loop_input)
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
            delay_input = input(f'Enter time in seconds to delay (press Enter for {settings["loop_speed_delay"]}): ')
            try:
                delay_seconds = settings["loop_speed_delay"]
                if delay_input:
                    delay_seconds = int(delay_input)

                print(f'Randomizing speed after {delay_seconds} second delay')
                settings['randomize_loop_speed'] = False
                delay_speed_thread = threading.Thread(target=delay_speed, args=(delay_seconds,))
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
        elif n == 'w':
            if not wsdm_enabled:
                wsdm_port_input = input(f"Enter the WSDM port to use (or press Enter to use '{settings['wsdm_port']}'): ")
                chosen_wsdm_port = settings['wsdm_port']
                if wsdm_port_input == '':
                    pass
                else:
                    try:
                        port_val = int(wsdm_port_input)
                        if 0 < port_val < 65536:
                            chosen_wsdm_port = wsdm_port_input
                        else:
                            print(f"Invalid port number (must be 1-65535). Using current port: {settings['wsdm_port']}.")
                    except ValueError:
                        print(f"Invalid input. Using current port: {settings['wsdm_port']}.")
                
                settings['wsdm_port'] = chosen_wsdm_port
                toggle_wsdm()
            else:
                toggle_wsdm()
        elif n == 'q':
            print('Quitting...')
            if wsdm_enabled:  # Gracefully stop wsdm if enabled
                wsdm_enabled = False
                if wsdm_thread and wsdm_thread.is_alive():
                    wsdm_thread.join(timeout=1)
            if server_running:  # Gracefully stop udp server if enabled
                stop_event.set()
                import socket
                dummy_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                try:
                    dummy_sock.sendto(b"stop", ('localhost', int(settings['udp_port'])))
                except ValueError:
                    pass
                finally:
                    dummy_sock.close()
                if server_thread and server_thread.is_alive():
                    server_thread.join(timeout=1)

            mixer.quit()
            break
