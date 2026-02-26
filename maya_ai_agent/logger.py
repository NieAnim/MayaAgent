# -*- coding: utf-8 -*-
"""
Centralized logging for Maya AI Agent.

Uses Python's built-in logging module instead of print() so that:
    - Log levels can be controlled (DEBUG / INFO / WARNING / ERROR)
    - Output goes to Maya's Script Editor via a StreamHandler
    - Timestamps and module names are included automatically

Usage:
    from .logger import log
    log.info("Something happened")
    log.warning("Watch out: %s", detail)
    log.error("Failed: %s", err)
"""

import logging

LOG_NAME = "MayaAIAgent"
LOG_FORMAT = "[%(name)s %(levelname)s] %(message)s"

log = logging.getLogger(LOG_NAME)

if not log.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter(LOG_FORMAT))
    log.addHandler(handler)
    log.setLevel(logging.DEBUG)
    log.propagate = False
