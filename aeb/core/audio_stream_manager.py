# aeb/core/audio_stream_manager.py
"""
Contains functions for managing the application's audio stream, including
starting, stopping, and reconfiguring the connection to the sound device.
"""
from typing import TYPE_CHECKING, Optional

import numpy as np

from aeb.core.audio_engine import AudioGenerator
from aeb.ui.widgets.audio_general_tab import LUT_RESOLUTION

if TYPE_CHECKING:
    from aeb.app_context import AppContext
    from aeb.core.audio_callback_handler import AudioCallbackHandler


def start_audio_stream(
        app_context: 'AppContext',
        handler: 'AudioCallbackHandler',
        sc_device_id: Optional[str] = None
) -> bool:
    """
    Initializes and starts the main audio output stream.

    Args:
        app_context: The central application context.
        handler: An instance of AudioCallbackHandler to process audio blocks.
        sc_device_id: The soundcard device ID string to use for output.

    Returns:
        True if the stream started successfully, False otherwise.
    """
    import sounddevice as sd  # Lazy import for COM initialization order
    with app_context.audio_stream_lock:
        _stop_existing_audio_stream(app_context)
        sd_device_index, device_name = _get_sd_device_index(
            app_context, sc_device_id
        )
        blocksize = int(app_context.config.get('audio_buffer_size', 256))
        latency = app_context.config.get('audio_latency', 'low')

        update_audio_generators(app_context)

        try:
            log_msg = (f"Starting audio stream on '{device_name}'. "
                       f"Blocksize: {blocksize}, Latency: {latency}")
            app_context.signals.log_message.emit(log_msg)

            app_context.audio_stream = sd.OutputStream(
                samplerate=handler.sample_rate,
                blocksize=blocksize,
                device=sd_device_index,
                channels=2,
                dtype='float32',
                latency=latency,
                callback=handler.process_audio_block
            )
            app_context.audio_stream.start()

            actual_device = sd.query_devices(app_context.audio_stream.device)
            app_context.signals.log_message.emit(
                f"Audio stream started successfully on: {actual_device['name']}"
            )
            return True
        except Exception as e:
            app_context.signals.log_message.emit(
                f"Failed to start audio stream: {e}"
            )
            app_context.audio_stream = None
            return False


def stop_audio_stream(app_context: 'AppContext'):
    """
    Stops and closes the active audio output stream.

    Args:
        app_context: The central application context.
    """
    with app_context.audio_stream_lock:
        _stop_existing_audio_stream(app_context)


def reload_sound_engine_and_waveforms(app_context: 'AppContext'):
    """
    Reloads all generator configurations and updates channel activity.

    Args:
        app_context: The central application context.
    """
    update_audio_generators(app_context)
    app_context.signals.channel_activity.emit(
        app_context.actual_motor_vol_l,
        app_context.actual_motor_vol_r
    )


def update_audio_generators(app_context: 'AppContext'):
    """
    Performs a stateful, non-destructive update of the audio generators.

    This function compares the current wave configurations in settings with
    the existing generator objects, updating, adding, or removing them as
    needed to match the desired state. It also manages the pre-calculation
    of Spatial Mapping LUTs.

    Args:
        app_context: The central application context.
    """
    with app_context.audio_callback_configs_lock:
        active_scene = app_context.config.get_active_scene_dict()
        sound_wave_settings = active_scene.get('sound_waves', {})
        for ch in ['left', 'right', 'ambient']:
            new_configs = sound_wave_settings.get(ch, [])
            existing_gens = app_context.source_channel_generators.get(ch, [])
            num_new, num_existing = len(new_configs), len(existing_gens)

            for i in range(min(num_new, num_existing)):
                existing_gens[i].update_config(new_configs[i])
                _update_spatial_mapping_lut_for_generator(
                    app_context, ch, i, new_configs[i]
                )

            if num_new > num_existing:
                for i in range(num_existing, num_new):
                    new_gen = AudioGenerator(app_context, new_configs[i])
                    existing_gens.append(new_gen)
                    _update_spatial_mapping_lut_for_generator(
                        app_context, ch, i, new_configs[i]
                    )
            elif num_new < num_existing:
                for i in range(num_new, num_existing):
                    key = f"{ch}.{i}"
                    if key in app_context.spatial_mapping_luts:
                        del app_context.spatial_mapping_luts[key]
                app_context.source_channel_generators[ch] = existing_gens[:num_new]

    num_l = len(app_context.source_channel_generators['left'])
    num_r = len(app_context.source_channel_generators['right'])
    num_a = len(app_context.source_channel_generators['ambient'])
    app_context.signals.log_message.emit(
        f"Source generators updated (non-destructive): "
        f"{num_l} L / {num_r} R / {num_a} A."
    )


def _update_spatial_mapping_lut_for_generator(
        app_context: 'AppContext', channel: str, index: int, config: dict):
    """
    Calculates and stores a Spatial Mapping LUT for a generator if needed.

    Args:
        app_context: The central application context.
        channel: The channel key of the generator.
        index: The index of the generator on the channel.
        config: The configuration dictionary for the generator.
    """
    key = f"{channel}.{index}"
    spatial_map = config.get('spatial_mapping')
    is_enabled = isinstance(spatial_map, dict) and spatial_map.get('enabled', False)

    if not is_enabled:
        if key in app_context.spatial_mapping_luts:
            del app_context.spatial_mapping_luts[key]
        return

    try:
        left_curve = sorted(spatial_map.get('left_curve', []))
        right_curve = sorted(spatial_map.get('right_curve', []))

        if not (left_curve and right_curve):
            raise ValueError("Curves are missing or empty.")

        x_pos = np.linspace(0, 1, LUT_RESOLUTION)
        xp_l, fp_l = np.array(left_curve).T
        xp_r, fp_r = np.array(right_curve).T

        lut_left = np.interp(x_pos, xp_l, fp_l)
        lut_right = np.interp(x_pos, xp_r, fp_r)

        app_context.spatial_mapping_luts[key] = {
            'lut_left': lut_left,
            'lut_right': lut_right,
        }
    except Exception as e:
        app_context.signals.log_message.emit(
            f"Error generating Spatial Map LUT for {key}: {e}")
        if key in app_context.spatial_mapping_luts:
            del app_context.spatial_mapping_luts[key]


def _stop_existing_audio_stream(app_context: 'AppContext'):
    """
    Safely stops and closes the current audio stream if it exists.

    Args:
        app_context: The central application context.
    """
    if app_context.audio_stream:
        try:
            app_context.signals.log_message.emit("Stopping audio stream...")
            app_context.audio_stream.stop()
            app_context.audio_stream.close()
            app_context.signals.log_message.emit("Audio stream stopped.")
        except Exception as e:
            app_context.signals.log_message.emit(
                f"Exception stopping stream: {e}"
            )
        finally:
            app_context.audio_stream = None


def _get_sd_device_index(
        app_context: 'AppContext', sc_device_id: Optional[str]
) -> tuple[Optional[int], str]:
    """
    Finds the sounddevice integer index for a soundcard string ID.

    Args:
        app_context: The central application context.
        sc_device_id: The string ID from the soundcard library.

    Returns:
        A tuple of (sounddevice_index, device_name).
    """
    import soundcard as sc          # Lazy import for COM initialization order
    import sounddevice as sd       # Lazy import for COM initialization order
    if not sc_device_id:
        return None, "System Default"
    try:
        name_to_match = sc.get_speaker(sc_device_id).name
        sd_devices = sd.query_devices()
        for i, dev in enumerate(sd_devices):
            if dev['name'] == name_to_match and dev['max_output_channels'] > 0:
                return i, name_to_match
        app_context.signals.log_message.emit(
            f"Warning: Could not find sounddevice match for '{name_to_match}'. "
            "Using system default."
        )
        return None, "System Default"
    except Exception as e:
        app_context.signals.log_message.emit(
            f"Error finding device for ID '{sc_device_id}': {e}. "
            "Using system default."
        )
        return None, "System Default"