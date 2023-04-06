from pysinewave import SineWave
import vgamepad as vg

lfreq = 987  # Left channel frequency: 987
rfreq = 987  # Right channel frequency: 987

lmaxvol = -8  # Left maximum volume: -8
lminvol = -10  # Left minimum volume: -10
rmaxvol = -8  # Right maximum volume: -8
rminvol = -10  # Right minimum volume: -10

ldps = 150  # Left decibels per second: 150
rdps = 150  # Right decibels per second: 150

half_way = 127.5  # Used to switch channels, Calculate steps: 127.5
extended = False  # If True keep lvol at lmaxvol after half_way, else lminvol
buttons = False  # Press a few buttons on start
verbose = False  # spam volumes
very_verbose = False  # Spam motor states, volumes
pause = False  # Pause all sounds
auto_pause = True  # Pause all sounds when entering the control menu


lsteps = lminvol - lmaxvol
rsteps = rminvol - rmaxvol


lstep = lsteps / half_way
rstep = rsteps / half_way

last_motor = 0

defaults = [
    lfreq, rfreq, lmaxvol, lminvol, rmaxvol, rminvol, ldps, rdps,
    half_way, extended, buttons, verbose, very_verbose
]


def load_defaults(types):
    global lfreq, rfreq, lmaxvol, lminvol, rmaxvol, rminvol, ldps, rdps, half_way, extended, buttons, verbose, very_verbose
    if types == 'c':
        lfreq = defaults[0]
        rfreq = defaults[1]
        lmaxvol = defaults[2]
        lminvol = defaults[3]
        rmaxvol = defaults[4]
        rminvol = defaults[5]
        ldps = defaults[6]
        rdps = defaults[7]
    elif types == 'o':
        half_way = defaults[8]
        extended = defaults[9]
        buttons = defaults[10]
        verbose = defaults[11]
        very_verbose = defaults[12]
    elif types == 'b':
        lfreq = defaults[0]
        rfreq = defaults[1]
        lmaxvol = defaults[2]
        lminvol = defaults[3]
        rmaxvol = defaults[4]
        rminvol = defaults[5]
        ldps = defaults[6]
        rdps = defaults[7]
        half_way = defaults[8]
        extended = defaults[9]
        buttons = defaults[10]
        verbose = defaults[11]
        very_verbose = defaults[12]


def spam_buttons():
    import time
    for i in range(4):
        gamepad.press_button(button=vg.XUSB_BUTTON.XUSB_GAMEPAD_START)
        gamepad.update()
        time.sleep(0.5)
        gamepad.release_button(button=vg.XUSB_BUTTON.XUSB_GAMEPAD_START)
        gamepad.update()
        time.sleep(0.5)


def rumble(client, target, large_motor, small_motor, led_number, user_data):
    """
    Callback function triggered at each received state change
    :param small_motor: integer in [0, 255]
    """
    global last_motor
    if small_motor > 0 or large_motor > 0:
        if very_verbose:
            print(f"large motor: {large_motor}, small motor: {small_motor}")

    # motor has rumble, start
    if large_motor > small_motor:
        # Only care about the motor with most rumble
        small_motor = large_motor
    if small_motor > 255:
        # Shouldn't ever go above 255, just incase
        small_motor = 255
    if small_motor > 0 and small_motor != last_motor:
        if pause:
            small_motor = 0

        SineWave.set_frequency(swl, lfreq)
        SineWave.set_frequency(swr, rfreq)
        swl.sinewave_generator.decibels_per_second = ldps
        swr.sinewave_generator.decibels_per_second = rdps

        # calculate volume
        if small_motor < half_way:
            rvol = rminvol
            lvol = lmaxvol
            lvol += lstep * small_motor
        else:
            if extended:
                lvol = lmaxvol
            else:
                lvol = lminvol
            rvol = rminvol
            rvol -= rstep * (small_motor - half_way)
        if small_motor > 0:
            if very_verbose:
                print(f'real lvol: {lvol}, real rvol: {rvol}')

        # ensure left volume stays within lminmaxvol
        if lvol > lmaxvol:
            lvol = lmaxvol
        elif lvol < lminvol:
            lvol = lminvol

        # ensure right volume stays within rminmaxvol
        if rvol > rmaxvol:
            rvol = rmaxvol
        elif rvol < rminvol:
            rvol = rminvol

        # set the volume
        SineWave.set_volume(swr, rvol)
        SineWave.set_volume(swl, lvol)
        if small_motor > 0:
            last_motor = small_motor
            if verbose:
                print(f'lvol: {lvol}, rvol: {rvol}')

    # no rumble lower volume
    else:
        if small_motor != last_motor:
            SineWave.set_volume(swl, -50)
            SineWave.set_volume(swr, -50)


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
    print('r : Reset options')
    print('q : Quit')


def print_controls():
    print('\n')
    print(f'f  : Edit the left {[lfreq]} and/or right {[rfreq]} frequency')
    print(f'mi : Edit the left {[lminvol]} and/or right {[rminvol]} minimum volume')
    print(f'ma : Edit the left {[lmaxvol]} and/or right {[rmaxvol]} maximum volume')
    print(f'd  : Edit the left {[ldps]} and/or right {[rdps]} decibels per second')
    print('c  : Leave the control menu')
    print('r : Reset options')
    if pause:
        print('p  : Toggle the sound on and [off]')
    else:
        print('p  : Toggle the sound [on] and off')


if __name__ == '__main__':
    # set left and right channels
    # decibels_per_second set really high to try and avoid init sound
    swl = SineWave(pitch_per_second=100, decibels_per_second=10000,
                   channels=2, channel_side='l')
    swr = SineWave(pitch_per_second=100, decibels_per_second=10000,
                   channels=2, channel_side='r')

    # set volume -100, frequencies, start sound
    SineWave.set_volume(swl, -100)
    SineWave.set_volume(swr, -100)
    SineWave.set_frequency(swl, lfreq)
    SineWave.set_frequency(swr, rfreq)
    swl.play()
    swr.play()

    # start 360 controller, set rumble callback
    gamepad = vg.VX360Gamepad()

    gamepad.register_notification(callback_function=rumble)

    print("Running...")

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
        elif n == 'r':
            print('[o]ptions [c]ontrols or [b]oth?')
            n = input("")
            if n == 'o':
                print(f'Resetting options...')
                load_defaults('o')
            elif n == 'c':
                print(f'Resetting controls...')
                load_defaults('c')
            elif n == 'b':
                print(f'Resetting options...')
                load_defaults('b')
        elif n == 'p':
            if pause is False:
                swl.sinewave_generator.decibels_per_second = 10000
                swr.sinewave_generator.decibels_per_second = 10000
                SineWave.set_volume(swl, -100)
                SineWave.set_volume(swr, -100)
                print('Pausing sound...')
                pause = True
                swl.stop()
                swr.stop()
            else:
                swl.sinewave_generator.decibels_per_second = 100
                swr.sinewave_generator.decibels_per_second = 100
                print('Resuming sound...')
                pause = False
                swl.play()
                swr.play()
        elif n == 'c':
            if auto_pause:
                print('Auto Pausing...')
                pause = True
                swl.stop()
                swr.stop()
            while 1 == 1:
                print_controls()
                n = input("\n")
                if n == 'f':
                    print('[l]eft [r]ight or [b]oth sides?')
                    n = input("")
                    try:
                        if n == 'l':
                            print(f'Current left frequency: {lfreq}')
                            n = input("Enter desired left frequency: ")
                            print(f'Setting left frequency to {n}...')
                            lfreq = float(n)
                        elif n == 'r':
                            print(f'Current right frequency: {rfreq}')
                            n = input("Enter desired right frequency: ")
                            print(f'Setting right frequency to {n}...')
                            rfreq = float(n)
                        elif n == 'b':
                            print(f'Current left frequency: {lfreq}')
                            print(f'Current right frequency: {rfreq}')
                            n = input("Enter desired frequency: ")
                            print(f'Setting both frequencies to {n}...')
                            lfreq = float(n)
                            rfreq = float(n)
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
                        swl.sinewave_generator.decibels_per_second = 10000
                        swr.sinewave_generator.decibels_per_second = 10000
                        SineWave.set_volume(swl, -100)
                        SineWave.set_volume(swr, -100)
                        print('Pausing sound...')
                        pause = True
                        swl.stop()
                        swr.stop()
                    else:
                        swl.sinewave_generator.decibels_per_second = 100
                        swr.sinewave_generator.decibels_per_second = 100
                        print('Resuming sound...')
                        pause = False
                        swl.play()
                        swr.play()
                elif n == 'd':
                    print('[l]eft [r]ight or [b]oth sides?')
                    n = input("")
                    try:
                        if n == 'l':
                            print(f'Current left dps: {ldps}')
                            n = input("Enter desired left dps: ")
                            print(f'Setting left dps to {n}...')
                            ldps = float(n)
                        elif n == 'r':
                            print(f'Current right dps: {rdps}')
                            n = input("Enter desired right dps: ")
                            print(f'Setting right dps to {n}...')
                            rdps = float(n)
                        elif n == 'b':
                            print(f'Current left dps: {ldps}')
                            print(f'Current right dps: {rdps}')
                            n = input("Enter desired dps: ")
                            print(f'Setting both dps to {n}...')
                            ldps = float(n)
                            rdps = float(n)
                    except ValueError:
                        print('\n')
                        print('Numbers only')
                elif n == 'r':
                    print('[o]ptions [c]ontrols or [b]oth?')
                    n = input("")
                    if n == 'o':
                        print(f'Resetting options...')
                        load_defaults('o')
                    elif n == 'c':
                        print(f'Resetting controls...')
                        load_defaults('c')
                    elif n == 'b':
                        print(f'Resetting options...')
                        load_defaults('b')
                elif n == 'c':
                    break

        elif n == 'q':
            print('Quitting...')
            break
