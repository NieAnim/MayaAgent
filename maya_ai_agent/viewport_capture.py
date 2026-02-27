# -*- coding: utf-8 -*-
"""
Viewport Capture - Capture Maya viewport as base64-encoded image for LLM vision.

IMPORTANT: All functions in this module MUST be called from the MAIN THREAD
because maya.cmds / playblast is not thread-safe.
"""

import base64
import os
import tempfile

import maya.cmds as cmds

from . import config
from .logger import log


def get_active_viewport():
    """
    Get the currently active 3D viewport (modelPanel).

    Returns:
        str or None: Panel name (e.g. 'modelPanel4') or None if not found.
    """
    # Try the panel with focus first
    try:
        panel = cmds.getPanel(withFocus=True)
        if panel and cmds.getPanel(typeOf=panel) == "modelPanel":
            return panel
    except Exception:
        pass

    # Fallback: find any visible modelPanel
    for panel in cmds.getPanel(type="modelPanel") or []:
        try:
            if cmds.modelPanel(panel, query=True, exists=True):
                return panel
        except Exception:
            continue

    return None


def capture_viewport(width=None, height=None, panel=None):
    """
    Capture the active Maya viewport as a PNG image and return base64 data.

    Uses cmds.playblast() for reliable viewport capture with all rendering
    features (textures, shadows, etc.) preserved.

    Args:
        width: Image width in pixels. Default from config or 960.
        height: Image height in pixels. Default from config or 540.
        panel: Specific modelPanel to capture. Default: auto-detect.

    Returns:
        dict with keys:
            - success (bool)
            - image_base64 (str): base64-encoded PNG data (without data URI prefix)
            - width (int)
            - height (int)
            - error (str): only present if success is False
    """
    if width is None:
        width = int(config.get("VISION_WIDTH", "1280"))
    if height is None:
        height = int(config.get("VISION_HEIGHT", "720"))

    # Clamp resolution
    width = max(320, min(3840, width))
    height = max(240, min(2160, height))

    if panel is None:
        panel = get_active_viewport()
    if panel is None:
        return {
            "success": False,
            "error": "No active 3D viewport found.",
            "image_base64": "",
            "width": 0,
            "height": 0,
        }

    # Use a temporary file for the playblast output
    tmp_dir = tempfile.gettempdir()
    tmp_path = os.path.join(tmp_dir, "maya_ai_agent_viewport")

    try:
        # playblast captures the viewport as an image
        result_path = cmds.playblast(
            frame=cmds.currentTime(query=True),
            format="image",
            compression="png",
            quality=95,
            widthHeight=[width, height],
            viewer=False,
            showOrnaments=True,
            offScreen=True,
            completeFilename=tmp_path + ".png",
            editorPanelName=panel,
            percent=100,
        )

        if not result_path:
            return {
                "success": False,
                "error": "playblast returned no file path.",
                "image_base64": "",
                "width": 0,
                "height": 0,
            }

        # playblast may return path without extension or with frame number
        actual_path = result_path
        if not os.path.isfile(actual_path):
            # Try common variations
            for suffix in [".png", ".0.png"]:
                candidate = tmp_path + suffix
                if os.path.isfile(candidate):
                    actual_path = candidate
                    break

        if not os.path.isfile(actual_path):
            return {
                "success": False,
                "error": "Captured file not found: {}".format(actual_path),
                "image_base64": "",
                "width": 0,
                "height": 0,
            }

        # Read and encode
        with open(actual_path, "rb") as f:
            image_data = f.read()

        image_b64 = base64.b64encode(image_data).decode("ascii")

        log.info("Viewport captured: %dx%d, %.1f KB",
                 width, height, len(image_data) / 1024.0)

        return {
            "success": True,
            "image_base64": image_b64,
            "width": width,
            "height": height,
        }

    except Exception as e:
        log.error("Viewport capture failed: %s", str(e))
        return {
            "success": False,
            "error": str(e),
            "image_base64": "",
            "width": 0,
            "height": 0,
        }
    finally:
        # Cleanup temp files
        for suffix in [".png", ".0.png"]:
            path = tmp_path + suffix
            try:
                if os.path.isfile(path):
                    os.remove(path)
            except OSError:
                pass


def capture_viewport_base64_uri(width=None, height=None):
    """
    Convenience wrapper: capture viewport and return a data URI string
    suitable for OpenAI Vision API's image_url field.

    Returns:
        str or None: "data:image/png;base64,..." or None on failure.
    """
    result = capture_viewport(width=width, height=height)
    if result["success"]:
        return "data:image/png;base64," + result["image_base64"]
    return None
