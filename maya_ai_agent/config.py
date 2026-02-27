# -*- coding: utf-8 -*-
"""
Configuration manager.
Loads settings from .env file using a simple parser (no external dependency).
"""

import os


_CONFIG_CACHE = {}


_DEFAULT_CONFIG = {
    "OPENAI_API_KEY": "",
    "OPENAI_API_BASE": "https://api.openai.com/v1",
    "OPENAI_MODEL": "gpt-4o",
    "OPENAI_MAX_TOKENS": "4096",
    "UI_FONT_SIZE": "13",
    "VISION_WIDTH": "1280",
    "VISION_HEIGHT": "720",
    "VISION_DETAIL": "high",
}


def _find_env_file():
    """Locate the .env file relative to this package.

    If the file does not exist yet, create one with safe defaults so
    the user can configure everything from inside Maya's settings panel
    without manually editing files.
    """
    package_dir = os.path.dirname(os.path.abspath(__file__))
    env_path = os.path.join(package_dir, ".env")
    if os.path.isfile(env_path):
        return env_path

    # Auto-create a default .env so the plugin can be loaded directly
    try:
        lines = ["# Maya AI Agent Configuration\n"]
        for key, value in _DEFAULT_CONFIG.items():
            lines.append("{}={}\n".format(key, value))
        with open(env_path, "w", encoding="utf-8") as f:
            f.writelines(lines)
        return env_path
    except OSError:
        return None


def _parse_env_file(filepath):
    """Parse a simple KEY=VALUE .env file."""
    result = {}
    with open(filepath, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip()
            # Remove surrounding quotes if present
            if len(value) >= 2 and value[0] == value[-1] and value[0] in ('"', "'"):
                value = value[1:-1]
            result[key] = value
    return result


def load_config(force_reload=False):
    """Load configuration from .env file, with caching."""
    global _CONFIG_CACHE
    if _CONFIG_CACHE and not force_reload:
        return dict(_CONFIG_CACHE)

    env_path = _find_env_file()
    if env_path:
        _CONFIG_CACHE = _parse_env_file(env_path)
    else:
        _CONFIG_CACHE = {}
    return dict(_CONFIG_CACHE)


def get(key, default=None):
    """Get a single config value."""
    config = load_config()
    return config.get(key, os.environ.get(key, default))


def save_config(data):
    """Save configuration back to .env file.

    Merges *data* into the existing config so that keys not present in
    *data* (e.g. UI_FONT_SIZE) are preserved.
    """
    package_dir = os.path.dirname(os.path.abspath(__file__))
    env_path = os.path.join(package_dir, ".env")

    # Load existing config first to preserve unmodified keys
    existing = {}
    if os.path.isfile(env_path):
        existing = _parse_env_file(env_path)

    # Merge: new data overrides existing keys, existing keys are kept
    merged = dict(existing)
    merged.update(data)

    lines = []
    lines.append("# Maya AI Agent Configuration\n")
    for key, value in merged.items():
        lines.append("{}={}\n".format(key, value))

    with open(env_path, "w", encoding="utf-8") as f:
        f.writelines(lines)

    # Invalidate cache
    global _CONFIG_CACHE
    _CONFIG_CACHE = {}
