# aeb/core/modulation_processor.py
"""
Contains the centralized, stateless processing logic for the modulation matrix.
This processor is called by different parts of the application to apply
modulation rules to a set of base parameters.
"""
from typing import TYPE_CHECKING, Optional

import numpy as np

if TYPE_CHECKING:
    from aeb.app_context import AppContext


def apply_modulations_to_parameters(
        app_context: 'AppContext',
        target_prefix: str,
        base_params: dict,
        activation_levels: dict[int, float],
        mod_sources_snapshot: dict,
        channel_key: str = '',
        wave_index: int = -1,
        mod_matrix_override: Optional[list] = None
) -> tuple[dict, bool]:
    """
    Applies modulation rules to a dictionary of base parameters.

    This function uses pre-calculated activation levels and a snapshot of all
    modulation sources to determine the final, modulated value for each
    parameter. It handles 'Gate' logic by detecting if automation exists
    to switch the default state from Open to Closed.

    Args:
        app_context: The central application context.
        target_prefix: The prefix for targets, e.g., 'left.0' or 'Master'.
        base_params: The dictionary of base parameter values for this cycle.
        activation_levels: A dict of {rule_index: activation_level}.
        mod_sources_snapshot: A point-in-time snapshot of all source values.
        channel_key: The channel key, used for context-specific logic.
        wave_index: The wave index, used for context-specific logic.
        mod_matrix_override: An optional, pre-calculated effective matrix.

    Returns:
        A tuple containing the dictionary of effective parameters and a
        boolean indicating if the gate is on.
    """
    eff_params = base_params.copy()
    gate_is_on = True
    gate_mod_values: list[float] = []
    has_gate_automation = False  # Track if any rule targets the gate

    mod_matrix = mod_matrix_override if mod_matrix_override is not None \
        else app_context.config.get('modulation_matrix', [])

    if not mod_matrix:
        return eff_params, gate_is_on

    for idx, rule in enumerate(mod_matrix):
        if not rule.get('enabled', False):
            continue

        if not rule.get('target', '').startswith(target_prefix):
            continue

        try:
            r_param = rule.get('target', '').split('.')[-1]
        except (ValueError, IndexError):
            continue

        # If we see an enabled rule targeting 'gate', we flag it.
        # This will flip the default state to False later, even if this rule
        # is currently inactive (level=0).
        if r_param == 'gate':
            has_gate_automation = True

        level = activation_levels.get(idx, 0.0)
        if level < 0.001:
            continue

        source_val = mod_sources_snapshot.get(rule.get('source'), 0.0)
        mode = rule.get('mode', 'additive')

        # Guard against applying numerical operations to non-numerical types.
        if mode in ['additive', 'multiplicative']:
            target_val = eff_params.get(r_param)
            # Special case for 'gate' which isn't in base_params but is numerical (0.0/1.0)
            if r_param != 'gate' and not isinstance(target_val, (int, float, bool, np.number)):
                if idx not in app_context.warned_mod_rule_indices:
                    param_type = type(target_val).__name__
                    app_context.signals.log_message.emit(
                        f"WARNING: Mod Rule {idx+1} uses mode '{mode}' on a "
                        f"non-numerical parameter '{r_param}' (type: {param_type}). "
                        "Rule will be ignored."
                    )
                    app_context.warned_mod_rule_indices.add(idx)
                continue

        if mode == 'set':
            if level > 0.5:
                amount_val = rule.get('amount')
                value_to_set = None

                if amount_val is not None:
                    try:
                        value_to_set = float(amount_val)
                    except (ValueError, TypeError):
                        value_to_set = str(amount_val)
                else:
                    value_to_set = source_val

                bool_params = {
                    'gate', 'lfo_enabled', 'filter_enabled',
                    'ambient_panning_link_enabled', 'ramp_up_enabled',
                    'ramp_down_enabled', 'long_idle_enabled',
                    'randomize_loop_speed', 'randomize_loop_range'
                }
                if r_param in bool_params:
                    eff_params[r_param] = float(value_to_set) > 0.5
                else:
                    eff_params[r_param] = value_to_set
            continue

        curve = rule.get('curve', 'linear')
        
        # --- Curve Processing ---
        if curve == 'exponential':
            source_val = (source_val ** 2) * np.sign(source_val)
        elif curve == 'logarithmic':
            source_val = np.sqrt(abs(source_val)) * np.sign(source_val)
        elif curve == 'custom':
            try:
                curve_data = rule.get('custom_curve_data')
                if isinstance(curve_data, list) and len(curve_data) >= 2:
                    # Unzip the list of [x, y] pairs into separate arrays
                    # This relies on the convention that x values are sorted.
                    # GenericCurveEditorDialog guarantees sorted output.
                    points = np.array(curve_data)
                    xp = points[:, 0]
                    fp = points[:, 1]
                    
                    # Robust Linear Interpolation
                    # Clamps input to the domain [min(x), max(x)] automatically
                    source_val = float(np.interp(source_val, xp, fp))
                else:
                    # Fallback if data is missing or invalid
                    if idx not in app_context.warned_mod_rule_indices:
                        app_context.signals.log_message.emit(
                            f"WARNING: Rule {idx+1} has invalid custom curve data. Falling back to linear."
                        )
                        app_context.warned_mod_rule_indices.add(idx)
            except Exception:
                # Catch-all for data corruption (e.g. malformed JSON types)
                if idx not in app_context.warned_mod_rule_indices:
                    app_context.signals.log_message.emit(
                        f"ERROR: Failed to process custom curve for Rule {idx+1}."
                    )
                    app_context.warned_mod_rule_indices.add(idx)

        try:
            amount = float(rule.get('amount', 0.0))
        except (ValueError, TypeError):
            amount = 0.0
        mod_value = (source_val * amount) * level

        if r_param == 'gate':
            gate_mod_values.append(mod_value)
        elif r_param.startswith('h') and r_param.endswith('_amp') and 'harmonics' in eff_params:
            try:
                h_idx = int(r_param[1:-4]) - 1
                h_list = eff_params['harmonics']
                if 0 <= h_idx < len(h_list):
                    h_list[h_idx] = np.clip(
                        h_list[h_idx] + mod_value, 0.0, 1.0)
            except (ValueError, IndexError):
                pass
        elif r_param in eff_params:
            if mode == 'additive':
                eff_params[r_param] += mod_value
            elif mode == 'multiplicative':
                eff_params[r_param] *= (1.0 + mod_value)

            min_clamp = float(rule.get('clamp_min', -np.inf))
            max_clamp = float(rule.get('clamp_max', np.inf))

            if isinstance(eff_params.get(r_param), (int, float)):
                eff_params[r_param] = np.clip(
                    eff_params[r_param], min_clamp, max_clamp)

    # Determine final gate state
    # Priority 1: Explicit 'set' mode override (present in eff_params)
    if 'gate' in eff_params:
        gate_is_on = eff_params['gate']
    # Priority 2: Additive/Multiplicative value logic
    elif gate_mod_values:
        gate_is_on = max(gate_mod_values) > 0.5
    # Priority 3: Automation exists but is inactive (e.g. key released) -> Default Closed
    elif has_gate_automation:
        gate_is_on = False
    # Priority 4: No automation -> Default Open
    else:
        gate_is_on = True

    return eff_params, gate_is_on