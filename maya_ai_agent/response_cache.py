# -*- coding: utf-8 -*-
"""
Response Cache - Local cache for pure Q&A responses (no tool calls).

When the user asks a knowledge question (e.g., "Maya 怎么导出 FBX") and the LLM
responds with text only (no tool calls), we cache the Q&A pair locally.
Next time the same (or very similar) question is asked, we return the cached
response instantly — zero API cost, zero latency.

Cache storage: JSON file in the package directory.
Cache key: normalized user query string (lowered, stripped, punctuation removed).

Features:
    - Automatic TTL expiry (configurable, default 7 days)
    - Max cache size with LRU eviction
    - Only caches responses where NO tools were called
    - Simple normalization for fuzzy matching
"""

import os
import re
import json
import time
import hashlib


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# Cache TTL in seconds (default: 7 days)
CACHE_TTL = 7 * 24 * 3600

# Maximum number of cached entries
MAX_CACHE_SIZE = 200

# Cache file location — use Maya's user directory instead of the package dir
# so that the package directory stays clean and read-only deployments work.
def _get_cache_dir():
    """Return a writable cache directory under the user's Maya prefs."""
    # Try Maya's user app dir first
    try:
        import maya.cmds as cmds
        maya_app_dir = cmds.internalVar(userAppDir=True)
        cache_dir = os.path.join(maya_app_dir, "maya_ai_agent")
    except Exception:
        # Fallback to ~/.maya_ai_agent
        cache_dir = os.path.join(os.path.expanduser("~"), ".maya_ai_agent")
    if not os.path.isdir(cache_dir):
        os.makedirs(cache_dir)
    return cache_dir

_CACHE_DIR = None  # Lazy-initialized
_CACHE_FILE = None

def _ensure_cache_path():
    global _CACHE_DIR, _CACHE_FILE
    if _CACHE_FILE is None:
        _CACHE_DIR = _get_cache_dir()
        _CACHE_FILE = os.path.join(_CACHE_DIR, ".response_cache.json")


# ---------------------------------------------------------------------------
# Normalization
# ---------------------------------------------------------------------------

# Regex to strip punctuation and whitespace for normalization
_STRIP_RE = re.compile(r'[^\w\u4e00-\u9fff]+', re.UNICODE)


def normalize_query(query):
    """
    Normalize a user query for cache key generation.
    - Lowercase
    - Strip whitespace and punctuation
    - Remove common filler words

    Args:
        query (str): Raw user input.

    Returns:
        str: Normalized key string.
    """
    text = query.strip().lower()
    # Remove punctuation but keep CJK characters and alphanumeric
    text = _STRIP_RE.sub('', text)
    return text


def _query_hash(normalized):
    """Generate a short hash for the normalized query."""
    return hashlib.md5(normalized.encode("utf-8")).hexdigest()[:16]


# ---------------------------------------------------------------------------
# Cache I/O
# ---------------------------------------------------------------------------

_memory_cache = None  # In-memory cache dict


def _load_cache():
    """Load cache from disk into memory."""
    global _memory_cache
    if _memory_cache is not None:
        return _memory_cache

    _ensure_cache_path()
    if os.path.isfile(_CACHE_FILE):
        try:
            with open(_CACHE_FILE, "r", encoding="utf-8") as f:
                _memory_cache = json.load(f)
        except (json.JSONDecodeError, IOError):
            _memory_cache = {}
    else:
        _memory_cache = {}

    return _memory_cache


def _save_cache():
    """Persist in-memory cache to disk."""
    global _memory_cache
    if _memory_cache is None:
        return

    _ensure_cache_path()
    try:
        with open(_CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(_memory_cache, f, ensure_ascii=False, indent=2)
    except IOError:
        pass  # Silently fail on write errors


def _evict_expired():
    """Remove expired entries."""
    cache = _load_cache()
    now = time.time()
    expired_keys = [
        k for k, v in cache.items()
        if now - v.get("timestamp", 0) > CACHE_TTL
    ]
    for k in expired_keys:
        del cache[k]


def _evict_lru():
    """Evict oldest entries if cache exceeds max size."""
    cache = _load_cache()
    if len(cache) <= MAX_CACHE_SIZE:
        return

    # Sort by last_access time, remove oldest
    sorted_keys = sorted(
        cache.keys(),
        key=lambda k: cache[k].get("last_access", 0),
    )
    to_remove = len(cache) - MAX_CACHE_SIZE
    for k in sorted_keys[:to_remove]:
        del cache[k]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def lookup(query):
    """
    Look up a cached response for the given query.

    Performs a two-layer search:
        1. Exact match in the local JSON cache (fast, hash-based)
        2. Fuzzy similarity match in the persistent history (difflib-based)

    Args:
        query (str): Raw user input.

    Returns:
        str or None: Cached response text, or None if not found/expired.
    """
    normalized = normalize_query(query)
    if not normalized:
        return None

    # --- Layer 1: Exact match in local JSON cache ---
    key = _query_hash(normalized)
    cache = _load_cache()
    entry = cache.get(key)

    if entry is not None:
        # Check TTL
        if time.time() - entry.get("timestamp", 0) > CACHE_TTL:
            del cache[key]
        elif entry.get("normalized") == normalized:
            # Hit! Update last access time
            entry["last_access"] = time.time()
            entry["hit_count"] = entry.get("hit_count", 0) + 1
            return entry.get("response")

    # --- Layer 2: Fuzzy match in persistent history ---
    try:
        from .history_manager import HistoryManager
        mgr = HistoryManager.instance()
        similar_reply = mgr.find_similar_qa(query)
        if similar_reply:
            return similar_reply
    except Exception:
        pass

    return None


def store(query, response):
    """
    Store a Q&A pair in the cache.
    Only call this for pure text responses (no tool calls were made).

    Args:
        query (str): Raw user input.
        response (str): LLM response text.
    """
    normalized = normalize_query(query)
    if not normalized:
        return
    if not response or len(response) < 10:
        return  # Don't cache trivially short responses

    key = _query_hash(normalized)
    cache = _load_cache()

    now = time.time()
    cache[key] = {
        "normalized": normalized,
        "query": query.strip(),
        "response": response,
        "timestamp": now,
        "last_access": now,
        "hit_count": 0,
    }

    # Evict if needed
    _evict_expired()
    _evict_lru()

    # Persist
    _save_cache()


def clear_cache():
    """Clear the entire response cache."""
    global _memory_cache
    _memory_cache = {}
    _ensure_cache_path()
    try:
        if os.path.isfile(_CACHE_FILE):
            os.remove(_CACHE_FILE)
    except IOError:
        pass


def get_cache_stats():
    """Get cache statistics."""
    cache = _load_cache()
    total_hits = sum(v.get("hit_count", 0) for v in cache.values())
    return {
        "entries": len(cache),
        "total_hits": total_hits,
        "max_size": MAX_CACHE_SIZE,
        "ttl_days": CACHE_TTL / 86400,
    }
