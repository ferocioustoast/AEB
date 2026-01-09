# aeb/core/path_utils.py
"""
Contains utility functions for resolving and relativizing file paths,
particularly for audio samples, to ensure scene portability.
"""
import os
from aeb.config.constants import CONFIG_FILE_PATH


def get_samples_dir() -> str:
    """
    Calculates and returns the absolute path to the 'Samples' directory.

    The 'Samples' directory is expected to be in the same root folder as the
    main configuration file.

    Returns:
        The absolute path to the canonical Samples directory.
    """
    config_dir = os.path.dirname(os.path.abspath(CONFIG_FILE_PATH))
    samples_dir = os.path.join(config_dir, "Samples")
    os.makedirs(samples_dir, exist_ok=True)
    return samples_dir


def relativize_sampler_path(absolute_path: str) -> str:
    """
    Converts an absolute file path to a relative one if it's inside the
    canonical 'Samples' directory.

    Args:
        absolute_path: The full, absolute path to the sample file.

    Returns:
        The filename if the file is in the Samples directory, otherwise the
        original absolute path.
    """
    if not isinstance(absolute_path, str) or not absolute_path:
        return ""
    try:
        samples_dir = get_samples_dir()
        if os.path.commonpath([absolute_path, samples_dir]) == samples_dir:
            return os.path.basename(absolute_path)
    except ValueError:
        # This can happen if paths are on different drives on Windows
        pass
    return absolute_path


def resolve_sampler_path(stored_path: str) -> str:
    """
    Converts a stored path (which may be relative) to a full, absolute path.

    Args:
        stored_path: The path string as stored in a scene file.

    Returns:
        A fully resolved, absolute path to the sample file. Returns an empty
        string if the input is empty or invalid.
    """
    if not isinstance(stored_path, str) or not stored_path:
        return ""
    if os.path.isabs(stored_path):
        return stored_path
    return os.path.join(get_samples_dir(), stored_path)