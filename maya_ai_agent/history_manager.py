# -*- coding: utf-8 -*-
"""
History Manager - Persistent storage for chat history (long-term memory).

Stores complete conversation records to the Maya user app directory so that
chat history survives across Maya sessions.

Storage format: JSON Lines (one JSON object per line) for append-friendly I/O.
Each record contains:
    - session_id: unique identifier for the conversation session
    - timestamp: ISO-8601 timestamp
    - user_input: the user's raw text
    - assistant_reply: the AI's text response
    - tools_used: list of tool names invoked (empty for pure Q&A)
    - is_shortcut: whether this was a local shortcut execution

Features:
    - Append-only writes (no full file rewrites)
    - Lazy loading with in-memory index for search
    - Keyword search across user inputs and AI replies
    - Text similarity matching for cache integration
    - Automatic file rotation when too large (configurable)
"""

import os
import re
import json
import time
import datetime
import hashlib
import difflib


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# Max file size before rotation (default: 5 MB)
MAX_FILE_SIZE = 5 * 1024 * 1024

# Max number of records to keep in memory for search
MAX_MEMORY_RECORDS = 2000

# Similarity threshold for fuzzy Q&A matching (0.0 ~ 1.0)
SIMILARITY_THRESHOLD = 0.75


# ---------------------------------------------------------------------------
# Singleton Manager
# ---------------------------------------------------------------------------

class HistoryManager:
    """
    Manages persistent chat history storage and retrieval.

    Usage:
        mgr = HistoryManager.instance()
        mgr.append(user_input="清零", assistant_reply="已完成归零",
                    tools_used=["zero_out_transforms"])
        results = mgr.search("清零")
    """

    _instance = None

    @classmethod
    def instance(cls):
        """Get or create the singleton instance."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def __init__(self):
        self._records = []       # In-memory record list
        self._loaded = False     # Whether we've loaded from disk
        self._history_dir = None
        self._history_file = None
        self._session_id = self._generate_session_id()

    # ----- File Path -------------------------------------------------------

    def _get_history_dir(self):
        """Get the history storage directory (Maya user app dir)."""
        if self._history_dir is not None:
            return self._history_dir

        try:
            import maya.cmds as cmds
            user_dir = cmds.internalVar(userAppDir=True)
        except Exception:
            # Fallback: use the package directory
            user_dir = os.path.dirname(os.path.abspath(__file__))

        history_dir = os.path.join(user_dir, "maya_ai_agent")
        if not os.path.isdir(history_dir):
            os.makedirs(history_dir)

        self._history_dir = history_dir
        return history_dir

    def _get_history_file(self):
        """Get the main history file path."""
        if self._history_file is not None:
            return self._history_file

        self._history_file = os.path.join(
            self._get_history_dir(), "agent_history.jsonl"
        )
        return self._history_file

    @staticmethod
    def _generate_session_id():
        """Generate a unique session ID based on timestamp."""
        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        h = hashlib.md5(str(time.time()).encode()).hexdigest()[:6]
        return "{}_{}".format(ts, h)

    # ----- Load / Save -----------------------------------------------------

    def _ensure_loaded(self):
        """Lazy-load history from disk on first access."""
        if self._loaded:
            return
        self._loaded = True
        self._load_from_disk()

    def _load_from_disk(self):
        """Load all records from the JSONL file into memory."""
        filepath = self._get_history_file()
        if not os.path.isfile(filepath):
            return

        records = []
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        record = json.loads(line)
                        records.append(record)
                    except json.JSONDecodeError:
                        continue
        except IOError:
            return

        # Keep only the most recent records in memory
        if len(records) > MAX_MEMORY_RECORDS:
            records = records[-MAX_MEMORY_RECORDS:]

        self._records = records

    def _append_to_disk(self, record):
        """Append a single record to the JSONL file."""
        filepath = self._get_history_file()

        # Check file rotation
        self._maybe_rotate(filepath)

        try:
            with open(filepath, "a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
        except IOError:
            pass

    def _maybe_rotate(self, filepath):
        """Rotate the history file if it exceeds the max size."""
        if not os.path.isfile(filepath):
            return
        try:
            size = os.path.getsize(filepath)
        except OSError:
            return

        if size < MAX_FILE_SIZE:
            return

        # Rotate: rename current file with timestamp suffix
        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        rotated = filepath.replace(".jsonl", "_{}.jsonl".format(ts))
        try:
            os.rename(filepath, rotated)
        except OSError:
            pass

    # ----- Public API: Write -----------------------------------------------

    def append(self, user_input, assistant_reply,
               tools_used=None, is_shortcut=False):
        """
        Append a conversation record.

        Args:
            user_input (str): The user's raw text.
            assistant_reply (str): The AI's response text.
            tools_used (list[str] or None): List of tool names invoked.
            is_shortcut (bool): Whether this was a local shortcut.
        """
        self._ensure_loaded()

        record = {
            "session_id": self._session_id,
            "timestamp": datetime.datetime.now().isoformat(),
            "user_input": user_input,
            "assistant_reply": assistant_reply,
            "tools_used": tools_used or [],
            "is_shortcut": is_shortcut,
        }

        self._records.append(record)

        # Trim in-memory records
        if len(self._records) > MAX_MEMORY_RECORDS:
            self._records = self._records[-MAX_MEMORY_RECORDS:]

        # Persist to disk
        self._append_to_disk(record)

    # ----- Public API: Read ------------------------------------------------

    def get_all_records(self):
        """Get all in-memory records (most recent last)."""
        self._ensure_loaded()
        return list(self._records)

    def get_session_records(self, session_id=None):
        """Get records for a specific session (default: current)."""
        self._ensure_loaded()
        sid = session_id or self._session_id
        return [r for r in self._records if r.get("session_id") == sid]

    def search(self, keyword):
        """
        Search history records by keyword (case-insensitive).

        Args:
            keyword (str): Search term.

        Returns:
            list[dict]: Matching records (most recent first).
        """
        self._ensure_loaded()
        if not keyword:
            return list(reversed(self._records))

        keyword_lower = keyword.lower()
        results = []
        for r in self._records:
            user = (r.get("user_input") or "").lower()
            reply = (r.get("assistant_reply") or "").lower()
            tools = " ".join(r.get("tools_used") or []).lower()
            if (keyword_lower in user
                    or keyword_lower in reply
                    or keyword_lower in tools):
                results.append(r)

        # Most recent first
        results.reverse()
        return results

    # ----- Public API: Similarity Matching ---------------------------------

    def find_similar_qa(self, query):
        """
        Find a similar past Q&A (no tools used) using text similarity.

        This is used by the QA cache integration layer: before hitting the LLM,
        we check if a very similar question was asked before and answered
        without any tool calls. If so, we can reuse the answer.

        Args:
            query (str): The user's new query.

        Returns:
            str or None: The previous AI reply if a similar Q&A is found,
                         otherwise None.
        """
        self._ensure_loaded()
        if not query:
            return None

        normalized = self._normalize(query)
        if not normalized:
            return None

        best_score = 0.0
        best_reply = None

        for r in reversed(self._records):
            # Only consider pure Q&A (no tools used)
            if r.get("tools_used"):
                continue
            if r.get("is_shortcut"):
                continue

            past_input = r.get("user_input", "")
            past_normalized = self._normalize(past_input)
            if not past_normalized:
                continue

            # Quick reject: if lengths differ too much, skip
            len_ratio = len(normalized) / max(len(past_normalized), 1)
            if len_ratio < 0.3 or len_ratio > 3.0:
                continue

            score = difflib.SequenceMatcher(
                None, normalized, past_normalized
            ).ratio()

            if score > best_score:
                best_score = score
                best_reply = r.get("assistant_reply", "")

        if best_score >= SIMILARITY_THRESHOLD and best_reply:
            return best_reply

        return None

    @staticmethod
    def _normalize(text):
        """Normalize text for similarity comparison."""
        text = text.strip().lower()
        # Remove punctuation but keep CJK and alphanumeric
        text = re.sub(r'[^\w\u4e00-\u9fff]+', '', text)
        return text

    # ----- Public API: Stats -----------------------------------------------

    def get_stats(self):
        """Get history statistics."""
        self._ensure_loaded()
        total = len(self._records)
        sessions = len(set(r.get("session_id", "") for r in self._records))
        tool_records = sum(1 for r in self._records if r.get("tools_used"))
        qa_records = total - tool_records
        return {
            "total_records": total,
            "total_sessions": sessions,
            "tool_records": tool_records,
            "qa_records": qa_records,
            "current_session": self._session_id,
        }

    def clear_all(self):
        """Clear all history (memory + disk)."""
        self._records.clear()
        filepath = self._get_history_file()
        try:
            if os.path.isfile(filepath):
                os.remove(filepath)
        except IOError:
            pass
