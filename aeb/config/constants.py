# aeb/config/constants.py (Updated)
"""
Contains default configuration dictionaries, audio constants, and other
static values for the Audio E-stim Bridge application.
"""
import copy
import re

# --- Configuration Constants ---
CONFIG_FILE_PATH = 'config.yaml'

# --- Application Constants ---

AUDIO_SAMPLE_RATE: int = 44100
OSCILLOSCOPE_DISPLAY_SAMPLES: int = 1024
CHANNEL_ACTIVITY_EMIT_INTERVAL: float = 0.04  # seconds
NORMALIZED_MIDPOINT: float = 0.5
TCODE_PATTERN: re.Pattern = re.compile(r"([LRVA])([0-9])([0-9]{2})")
BIPOLAR_AXES: set[str] = {"L1", "L2", "R0", "R1", "R2", "V-R0", "V-A0"}


# --- Default Waveform Configuration ---

DEFAULT_WAVE_SETTINGS: dict = {
    'type': 'sine',
    'frequency': 987.0,
    'amplitude': 1.0,
    'duty_cycle': 1.0,
    'ads_attack_time': 0.0,
    'ads_decay_time': 0.0,
    'ads_sustain_level': 1.0,
    'adsr_release_time': 0.1,
    'lfo_enabled': False,
    'lfo_target': 'amplitude',
    'lfo_waveform': 'sine',
    'lfo_frequency': 1.0,
    'lfo_depth': 0.5,
    'filter_enabled': False,
    'filter_type': 'lowpass',
    'filter_cutoff_frequency': 1000.0,
    'filter_resonance_q': 0.707,
    'muted': False,
    'soloed': False,
    'harmonics': [1.0] + [0.0] * 15,
    'additive_waveform': 'sine',
    'sampler_filepath': '',
    'sampler_loop_mode': 'Forward Loop',
    'sampler_loop_start': 0.0,
    'sampler_loop_end': 1.0,
    'sampler_loop_crossfade_ms': 10.0,
    'sampler_frequency': 0.0,
    'sampler_force_pitch': False,
    'sampler_original_pitch': 100.0,
    'pan': 0.0,
    'spatial_mapping': None,
}

# --- Channel-Specific Default Waves ---
DEFAULT_LEFT_WAVE = copy.deepcopy(DEFAULT_WAVE_SETTINGS)
DEFAULT_LEFT_WAVE['pan'] = -1.0

DEFAULT_RIGHT_WAVE = copy.deepcopy(DEFAULT_WAVE_SETTINGS)
DEFAULT_RIGHT_WAVE['pan'] = 1.0


# --- Default Application-Wide Configuration ---

DEFAULT_SETTINGS: dict = {
    # This key now defines the canonical list of all modulation sources.
    'modulation_sources': {
        "TCode: L0": 0.0, "TCode: L1": 0.0, "TCode: L2": 0.0,
        "TCode: R0": 0.0, "TCode: R1": 0.0, "TCode: R2": 0.0,
        "TCode: V0": 0.0, "TCode: A0": 0.0, "TCode: A1": 0.0, "TCode: A2": 0.0,
        "TCode: V-R0": 0.0, "TCode: V-V0": 0.0,
        
        # V-L1 is now Inertial (0.5 is Center/Rest). 
        "TCode: V-L1": 0.5,
        
        # V-A0 is Pneumatics (Bipolar: -1.0 Compression, +1.0 Suction)
        "TCode: V-A0": 0.0,
        
        "Internal: Loop": 0.0,
        "Internal: X360 Small Motor": 0.0, "Internal: X360 Large Motor": 0.0,
        "Internal: Time": 0.0, "Internal: Random": 0.0,
        "Internal: Primary Motion Driver": 0.0,
        "Internal: Left Channel Output Level": 0.0,
        "Internal: Right Channel Output Level": 0.0,
        
        # Somatic State Engine Sources
        "Internal: System Excitation": 0.0,
        "Internal: Kinetic Stress": 0.0,
        
        # Viscoelastic Physics Sources
        "Internal: Tension": 0.0,
        "Internal: Shear": 0.0,

        # Geometric Motion Analysis
        "Internal: Motion Span": 0.0,

        # Drift (Organic/Pink Noise)
        "Internal: Drift": 0.0,

        # Transient Impulse (Virtual Ripple Physics)
        "Internal: Transient Impulse": 0.0,
        
        "Primary Motion: Position": 0.0,
        "Primary Motion: Velocity": 0.0,
        "Primary Motion: Speed": 0.0, "Primary Motion: Acceleration": 0.0,
        "Screen Flow: Position": 0.0, "Screen Flow: Rhythm": 0.0, "Screen Flow: Intensity": 0.0,
    },

    # System LFOs
    'system_lfos': [],

    # Audio Engine & Output
    'sound_waves': {
        'left': [DEFAULT_LEFT_WAVE],
        'right': [DEFAULT_RIGHT_WAVE],
        'ambient': [],
    },
    'selected_audio_output_device_name': '',
    'audio_buffer_size': 64,
    'audio_latency': 'low',
    'left_max_vol': 1.0,
    'left_min_vol': 0.0,
    'right_max_vol': 1.0,
    'right_min_vol': 0.0,
    'left_amplitude': 1.0,
    'right_amplitude': 1.0,
    'ambient_amplitude': 1.0,
    'panning_law': 'tactile_power',
    'positional_mapping': None,
    'positional_ambient_mapping': None,
    'stereo_width': 1.0,
    'pan_offset': 0.0,
    'ambient_panning_link_enabled': False,
    'zonal_pressure': 1.0,
    'spatial_phase_offset': 0.0,
    'generator_headroom_limit': 1.0,
    'channel_safety_limit': 1.0,

    # Servers & TCode Input
    'udp_port': 8000,
    'udp_auto_start': False,
    'wsdm_port': 54817,
    'wsdm_auto_start': False,
    'wsdm_auto_retry': True,
    'wsdm_retry_delay': 10,
    'controller_enabled': False,
    'controller_auto_start': False,

    # Volume Ramping
    'ramp_up_enabled': True,
    'ramp_up_time': 0.3,
    'ramp_up_steps': 20,
    'ramp_down_enabled': True,
    'ramp_down_time': 0.3,
    'ramp_down_steps': 20,
    'idle_time_before_ramp_down': 0.5,
    'ramp_down_activity_threshold': 0.01,
    'long_idle_enabled': True,
    'long_idle_trigger_time': 3.0,
    'long_idle_initial_amp': 0.5,
    'long_idle_ramp_time': 5.0,

    # Internal Loop Generator
    'loop_motion_type': 'sine',
    'static_loop_time_s': 0.5,
    'randomize_loop_speed': False,
    'loop_speed_fastest': 0.05,
    'loop_speed_ramp_time_min': 15.0,
    'loop_speed_interval_sec': 1.0,
    'delay_loop_speed': False,
    'loop_speed_delay': 60,
    'randomize_loop_range': False,
    'delay_loop_range': False,
    'loop_range_delay_sec': 60,
    'loop_range_interval_min_s': 10.0,
    'loop_range_interval_max_s': 30.0,
    'loop_range_transition_time_s': 1.0,
    'min_loop': 1,
    'max_loop': 255,
    'slowest_loop_speed': 2.0,
    'loop_ranges': {0: [1, 255], 1: [1, 55], 2: [201, 255]},

    # Drift Generator (Organic Motion)
    'internal_drift_speed': 0.5,
    'internal_drift_octaves': 2,

    # Live Sync: Screen Flow
    'screen_flow_enabled_on_startup': False,
    'screen_flow_region': None,
    'screen_flow_capture_fps': 30,
    'screen_flow_analysis_width': 128,
    'screen_flow_motion_axis': 'vertical',
    'screen_flow_show_preview': True,
    'screen_flow_rhythm_min_hz': 0.5,
    'screen_flow_rhythm_max_hz': 10.0,
    'screen_flow_intensity_gain': 1.0,
    'screen_flow_intensity_smoothing': 0.2,
    'screen_flow_stability_threshold': 0.1,


    # Live Sync: Audio Input
    'selected_audio_input_device_name': '',
    'audio_analysis_channels': [],

    # Modulation Matrix Advanced Sources
    'internal_time_period_s': 30.0,
    'internal_random_rate_hz': 1.0,
    'env_follower_attack_ms': 10.0,
    'env_follower_release_ms': 100.0,
    'motion_norm_window_s': 8.0,
    'motion_speed_floor': 10.0,
    'motion_accel_floor': 50.0,
    'motion_jolt_floor': 2500.0,
    'motion_span_decay_s': 3.0,
    'velocity_smoothing': 0.1,
    
    # Somatic State Engine (Thermodynamic Integration)
    'somatic_excitation_buildup_s': 60.0,
    'somatic_excitation_decay_s': 30.0,
    'somatic_excitation_cooldown_s': 3.0,
    'somatic_stress_attack_s': 0.1,
    'somatic_stress_release_s': 0.5,

    # Viscoelastic Physics (Skin Model)
    'internal_tension_limit': 0.1,
    'internal_tension_release_rate': 0.5,

    # Transient Impulse (Virtual Ripple Physics)
    'impulse_mass': 0.2,
    'impulse_spring': 50.0,
    'impulse_damping': 2.0,
    'impulse_input_gain': 1.0,

    # Motion Feel
    'motion_feel_L1_enabled': False,
    'motion_feel_L1_amount': 0.4,
    'motion_feel_L2_enabled': False,
    'motion_feel_L2_timbre_hz': 1500.0,
    'motion_feel_L2_sharpness': 0.5,
    'motion_feel_R0_enabled': False,
    'motion_feel_R0_detune_hz': 5.0,
    'motion_feel_R1_enabled': False,
    'motion_feel_R1_filter_hz': 1000.0,
    'motion_feel_R2_enabled': False,
    'motion_feel_R2_balance': 0.3,
    'motion_feel_R2_crossover_hz': 600.0,
    'motion_feel_VR0_enabled': False,
    'motion_feel_VR0_detune_hz': 6.0,
    'motion_feel_VL1_enabled': False,
    'motion_feel_VL1_amount': 0.5,
    'motion_feel_VV0_enabled': False,
    'motion_feel_VV0_q_mod': 4.0,
    
    # V-A0 Motion Feel (Easy Mode Pneumatics)
    'motion_feel_VA0_enabled': False,
    'motion_feel_VA0_muffle_hz': 1000.0,  # Filter reduction on insertion
    'motion_feel_VA0_suction_boost': 0.5, # Amplitude boost on withdrawal

    # Virtual Axis Synthesis
    'vas_vr0_stiffness': 200.0,
    'vas_vr0_damping': 15.0,
    'vas_vv0_stiffness': 300.0,
    'vas_vv0_damping': 20.0,
    
    # V-L1 Inertial Physics
    'vas_inertia_mass': 0.5,
    'vas_inertia_spring': 40.0,
    'vas_inertia_damping': 4.0,
    
    # V-A0 Pneumatics Physics
    'vas_va0_smoothing': 0.2,

    # Miscellaneous
    'program_list': [],
    'launch_programs_on_startup': False,
    'print_motor_states': False,
    'use_discrete_channels': False,
    'modulation_matrix': [],
    'preset_metadata': None,
    'hotkeys': [],
    'global_actions': [],
    'global_hotkeys': [],
    'scene_playlist': {},
}

# --- Configuration Scopes (Global vs. Scene) ---

GLOBAL_SETTINGS_KEYS = {
    'selected_audio_output_device_name',
    'selected_audio_input_device_name',
    'audio_buffer_size',
    'audio_latency',
    'udp_port',
    'udp_auto_start',
    'wsdm_port',
    'wsdm_auto_start',
    'wsdm_auto_retry',
    'wsdm_retry_delay',
    'controller_auto_start',
    'program_list',
    'launch_programs_on_startup',
    'screen_flow_region',
    'screen_flow_enabled_on_startup',
    'global_hotkeys',
    'global_actions',
}

SCENE_SETTINGS_KEYS = set(DEFAULT_SETTINGS.keys()) - GLOBAL_SETTINGS_KEYS
SCENE_SETTINGS_KEYS.add('positional_mapping')
SCENE_SETTINGS_KEYS.add('positional_ambient_mapping')