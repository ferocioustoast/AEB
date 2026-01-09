# aeb/services/tcode_parser.py
"""
Handles the parsing of T-Code data strings and updating the shared T-Code
state within the AppContext.
"""
import logging
import time
from typing import TYPE_CHECKING

import numpy as np

from aeb.config.constants import BIPOLAR_AXES, TCODE_PATTERN

if TYPE_CHECKING:
    from aeb.app_context import AppContext


def parse_tcode_string(app_context: 'AppContext', tcode_str: str) -> bool:
    """
    Parses a T-Code string, updates state atomically, and returns True if any
    values changed. This function is optimized to minimize lock contention.

    Args:
        app_context: The central application context.
        tcode_str: The T-Code string to parse.

    Returns:
        True if any T-Code axis value was changed, False otherwise.
    """
    updates: dict[str, float] = {}
    for match in TCODE_PATTERN.finditer(tcode_str.upper()):
        axis_key, norm_val = _parse_tcode_match(match)
        if axis_key:
            updates[axis_key] = norm_val

    if not updates:
        return False

    was_updated = False
    log_messages = []
    store = app_context.modulation_source_store

    with app_context.tcode_axes_lock:
        for axis_key, norm_val in updates.items():
            if axis_key not in app_context.tcode_axes_states:
                continue

            if abs(app_context.tcode_axes_states[axis_key] - norm_val) > 1e-5:
                was_updated = True
                app_context.tcode_axes_states[axis_key] = norm_val
                mod_source_key = f"TCode: {axis_key}"
                store.set_source(mod_source_key, norm_val)
                log_messages.append(f"{axis_key}:{norm_val:.3f}")

    if was_updated:
        app_context.last_tcode_update_time = time.perf_counter()
        if app_context.config.get('print_motor_states', False) and log_messages:
            logging.info("TCODE: %s", " | ".join(log_messages))

    return was_updated


def _parse_tcode_match(match) -> tuple[str | None, float | None]:
    """
    Parses a single regex match from a T-Code string into a key and
    normalized value.

    Args:
        match: A regex match object from TCODE_PATTERN.

    Returns:
        A tuple of (axis_key, normalized_value), or (None, None) on error.
    """
    try:
        axis_char = match.group(1)
        axis_num = match.group(2)
        intensity_str = match.group(3)
        axis_key = f"{axis_char}{axis_num}"
        intensity_int = int(intensity_str)
        normalized_value = _normalize_tcode_value(axis_key, intensity_int)
        return axis_key, normalized_value
    except (ValueError, IndexError):
        return None, None


def _normalize_tcode_value(axis_key: str, intensity_int: int) -> float:
    """
    Normalizes a T-Code intensity (0-99) to the correct unipolar/bipolar
    range.

    Args:
        axis_key: The T-Code axis identifier (e.g., "L0", "R1").
        intensity_int: The integer intensity value (0-99).

    Returns:
        The normalized float value.
    """
    if axis_key in BIPOLAR_AXES:
        # Bipolar axes: -1.0 to 1.0, with 50 as the center (0.0)
        if intensity_int < 50:
            return float(np.interp(intensity_int, [0, 49], [-1.0, 0.0]))
        return float(np.interp(intensity_int, [50, 99], [0.0, 1.0]))

    # Unipolar axes: 0.0 to 1.0
    return intensity_int / 99.0