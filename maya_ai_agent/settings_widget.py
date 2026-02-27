# -*- coding: utf-8 -*-
"""
Settings Widget - Inline settings panel (embedded in sidebar page).
Replaces the old modal SettingsDialog with an in-page configuration view.
"""

from .qt_compat import QtWidgets, QtCore, Qt
from . import config

import json
from urllib import request as urllib_request
from urllib.error import URLError, HTTPError

# ---------------------------------------------------------------------------
# Provider Presets  (each provider now carries a list of recommended models)
# ---------------------------------------------------------------------------

PRESETS = [
    {
        "name": "OpenAI",
        "api_base": "https://api.openai.com/v1",
        "models": ["gpt-4o", "gpt-4o-mini", "gpt-4.1", "gpt-4.1-mini",
                    "gpt-4.1-nano", "o3-mini", "o4-mini"],
        "default_model": "gpt-4o",
        "placeholder_key": "sk-...",
        "hint": "获取 Key：https://platform.openai.com/api-keys",
    },
    {
        "name": "Google Gemini",
        "api_base": "https://generativelanguage.googleapis.com/v1beta/openai",
        "models": ["gemini-2.5-flash", "gemini-2.5-pro", "gemini-2.0-flash",
                    "gemini-2.0-flash-lite"],
        "default_model": "gemini-2.5-flash",
        "placeholder_key": "AIza...",
        "hint": (
            "获取 Key：https://aistudio.google.com/apikey\n"
            "Gemini 提供 OpenAI 兼容接口，直接使用即可。"
        ),
    },
    {
        "name": "DeepSeek",
        "api_base": "https://api.deepseek.com/v1",
        "models": ["deepseek-chat", "deepseek-reasoner"],
        "default_model": "deepseek-chat",
        "placeholder_key": "sk-...",
        "hint": (
            "获取 Key：https://platform.deepseek.com/api_keys\n"
            "⚠ DeepSeek 模型不支持视觉/图片输入。"
        ),
    },
    {
        "name": "Anthropic Claude",
        "api_base": "https://api.anthropic.com/v1",
        "models": ["claude-sonnet-4-20250514", "claude-opus-4-20250514",
                    "claude-3.5-sonnet-20241022"],
        "default_model": "claude-sonnet-4-20250514",
        "placeholder_key": "sk-ant-...",
        "hint": (
            "获取 Key：https://console.anthropic.com/settings/keys\n"
            "⚠ Claude 原生 API 与 OpenAI 不同，\n"
            "如需使用请配合 OpenAI 兼容代理（如 LiteLLM / one-api）。"
        ),
    },
    {
        "name": "OpenRouter",
        "api_base": "https://openrouter.ai/api/v1",
        "models": ["deepseek/deepseek-chat", "google/gemini-2.5-flash",
                    "anthropic/claude-sonnet-4", "openai/gpt-4o",
                    "meta-llama/llama-4-maverick"],
        "default_model": "deepseek/deepseek-chat",
        "placeholder_key": "sk-or-...",
        "hint": "获取 Key：https://openrouter.ai/keys\n聚合平台，可访问几乎所有模型。",
    },
    {
        "name": "Ollama (本地)",
        "api_base": "http://localhost:11434/v1",
        "models": ["qwen2.5:14b", "qwen2.5:7b", "llama3.1:8b",
                    "gemma2:9b", "llava:13b"],
        "default_model": "qwen2.5:14b",
        "placeholder_key": "ollama",
        "hint": (
            "Ollama 本地部署，无需 API Key（填任意值即可）。\n"
            "可用模型取决于你本地 ollama 拉取了哪些。"
        ),
    },
    {
        "name": "自定义 (Custom)",
        "api_base": "",
        "models": [],
        "default_model": "",
        "placeholder_key": "your-api-key",
        "hint": "手动填写所有字段。支持任何 OpenAI 兼容 API。",
    },
]


_SETTINGS_STYLE = """
QWidget#SettingsPanel {
    background-color: #1e1e1e;
}

QGroupBox {
    color: #cccccc;
    font-size: 13px;
    font-weight: bold;
    border: 1px solid #3c3c3c;
    border-radius: 6px;
    margin-top: 12px;
    padding: 16px 12px 12px 12px;
}

QGroupBox::title {
    subcontrol-origin: margin;
    subcontrol-position: top left;
    padding: 0 8px;
    color: #cccccc;
}

QLabel {
    color: #bbbbbb;
    font-size: 12px;
}

QLineEdit {
    background-color: #2d2d2d;
    color: #d4d4d4;
    border: 1px solid #3c3c3c;
    border-radius: 4px;
    padding: 6px 8px;
    font-size: 12px;
    selection-background-color: #264f78;
}

QLineEdit:focus {
    border-color: #0078d4;
}

QComboBox {
    background-color: #2d2d2d;
    color: #d4d4d4;
    border: 1px solid #3c3c3c;
    border-radius: 4px;
    padding: 5px 8px;
    font-size: 12px;
}

QComboBox::drop-down {
    border: none;
    width: 20px;
}

QComboBox QAbstractItemView {
    background-color: #2d2d2d;
    color: #d4d4d4;
    border: 1px solid #3c3c3c;
    selection-background-color: #264f78;
}

QSpinBox {
    background-color: #2d2d2d;
    color: #d4d4d4;
    border: 1px solid #3c3c3c;
    border-radius: 4px;
    padding: 5px 8px;
    font-size: 12px;
}

QCheckBox {
    color: #bbbbbb;
    font-size: 12px;
    spacing: 6px;
}

QCheckBox::indicator {
    width: 14px;
    height: 14px;
    border: 1px solid #555555;
    border-radius: 3px;
    background-color: #2d2d2d;
}

QCheckBox::indicator:checked {
    background-color: #0078d4;
    border-color: #0078d4;
}

QPushButton#saveBtn {
    background-color: #0078d4;
    color: white;
    border: none;
    border-radius: 6px;
    padding: 8px 24px;
    font-size: 13px;
    font-weight: bold;
}

QPushButton#saveBtn:hover {
    background-color: #1a8ae8;
}

QPushButton#testBtn {
    background-color: #3c3c3c;
    color: #d4d4d4;
    border: 1px solid #555555;
    border-radius: 6px;
    padding: 8px 18px;
    font-size: 13px;
    font-weight: bold;
}

QPushButton#testBtn:hover {
    background-color: #505050;
}

QPushButton#testBtn:disabled {
    color: #666666;
}

QPushButton#applyPresetBtn {
    background-color: #3c3c3c;
    color: #d4d4d4;
    border: 1px solid #555555;
    border-radius: 4px;
    padding: 5px 12px;
    font-size: 12px;
}

QPushButton#applyPresetBtn:hover {
    background-color: #505050;
}

QLabel#hintLabel {
    color: #888888;
    font-size: 11px;
    background-color: #252526;
    border-radius: 4px;
    padding: 8px;
}

QLabel#statusMsg {
    color: #4ec9b0;
    font-size: 12px;
    padding: 4px 0;
}
"""


class SettingsWidget(QtWidgets.QWidget):
    """Inline settings panel with per-provider memory and model presets."""

    # Config key prefix for per-provider storage, e.g. PROVIDER_OpenAI_API_KEY
    _PROVIDER_KEY_PREFIX = "PROVIDER_"

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("SettingsPanel")
        self.setStyleSheet(_SETTINGS_STYLE)
        self._switching_provider = False  # guard to prevent save-on-switch loops
        self._build_ui()
        self._load_current()

    # =====================================================================
    #  Per-provider config helpers
    # =====================================================================

    @staticmethod
    def _provider_config_key(provider_name, field):
        """Return the .env key for a per-provider setting.

        Example: _provider_config_key("Google Gemini", "API_KEY")
                 -> "PROVIDER_Google_Gemini_API_KEY"
        """
        safe_name = provider_name.replace(" ", "_").replace("(", "").replace(")", "")
        return "PROVIDER_{}_{}".format(safe_name, field)

    def _save_provider_config(self, provider_name, api_key, model, max_tokens):
        """Persist settings for a specific provider."""
        data = {
            self._provider_config_key(provider_name, "API_KEY"): api_key,
            self._provider_config_key(provider_name, "MODEL"): model,
            self._provider_config_key(provider_name, "MAX_TOKENS"): str(max_tokens),
        }
        config.save_config(data)

    def _load_provider_config(self, provider_name):
        """Load saved settings for a specific provider. Returns dict or None."""
        cfg = config.load_config(force_reload=False)
        key_key = self._provider_config_key(provider_name, "API_KEY")
        model_key = self._provider_config_key(provider_name, "MODEL")
        tokens_key = self._provider_config_key(provider_name, "MAX_TOKENS")

        # Only return if at least the api_key was ever saved for this provider
        if key_key in cfg or model_key in cfg:
            return {
                "api_key": cfg.get(key_key, ""),
                "model": cfg.get(model_key, ""),
                "max_tokens": cfg.get(tokens_key, "4096"),
            }
        return None

    # =====================================================================
    #  UI Build
    # =====================================================================

    def _build_ui(self):
        scroll = QtWidgets.QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QtWidgets.QFrame.NoFrame)
        scroll.setStyleSheet("QScrollArea { background-color: #1e1e1e; border: none; }")

        content = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(content)
        layout.setContentsMargins(16, 12, 16, 16)
        layout.setSpacing(8)

        # --- Title ---
        title = QtWidgets.QLabel("设置")
        title.setStyleSheet(
            "color: #cccccc; font-size: 16px; font-weight: bold; padding-bottom: 4px;"
        )
        layout.addWidget(title)

        # --- Provider Group ---
        provider_group = QtWidgets.QGroupBox("服务商")
        provider_layout = QtWidgets.QVBoxLayout(provider_group)
        provider_layout.setSpacing(8)

        row = QtWidgets.QHBoxLayout()
        row.addWidget(QtWidgets.QLabel("服务商:"))
        self.preset_combo = QtWidgets.QComboBox()
        for p in PRESETS:
            self.preset_combo.addItem(p["name"])
        row.addWidget(self.preset_combo, stretch=1)
        provider_layout.addLayout(row)

        self.hint_label = QtWidgets.QLabel("")
        self.hint_label.setObjectName("hintLabel")
        self.hint_label.setWordWrap(True)
        self.hint_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        provider_layout.addWidget(self.hint_label)

        layout.addWidget(provider_group)

        # --- API Config Group ---
        api_group = QtWidgets.QGroupBox("API 配置")
        api_layout = QtWidgets.QFormLayout(api_group)
        api_layout.setSpacing(10)
        api_layout.setLabelAlignment(Qt.AlignRight)

        self.api_key_edit = QtWidgets.QLineEdit()
        self.api_key_edit.setEchoMode(QtWidgets.QLineEdit.Password)
        self.api_key_edit.setPlaceholderText("sk-...")
        api_layout.addRow("API Key:", self.api_key_edit)

        self.api_base_edit = QtWidgets.QLineEdit()
        self.api_base_edit.setPlaceholderText("https://api.openai.com/v1")
        api_layout.addRow("Base URL:", self.api_base_edit)

        # Model: editable combo box (presets + custom input)
        self.model_combo = QtWidgets.QComboBox()
        self.model_combo.setEditable(True)
        self.model_combo.setInsertPolicy(QtWidgets.QComboBox.NoInsert)
        self.model_combo.lineEdit().setPlaceholderText("选择或输入模型名称")
        api_layout.addRow("模型名称:", self.model_combo)

        self.max_tokens_spin = QtWidgets.QSpinBox()
        self.max_tokens_spin.setRange(256, 128000)
        self.max_tokens_spin.setValue(4096)
        self.max_tokens_spin.setSingleStep(256)
        api_layout.addRow("最大 Tokens:", self.max_tokens_spin)

        layout.addWidget(api_group)

        # --- Options ---
        self.show_key_cb = QtWidgets.QCheckBox("显示 API Key")
        self.show_key_cb.toggled.connect(self._toggle_key_visibility)
        layout.addWidget(self.show_key_cb)

        # --- Token Usage Group ---
        usage_group = QtWidgets.QGroupBox("Token 用量统计")
        usage_layout = QtWidgets.QVBoxLayout(usage_group)
        usage_layout.setSpacing(6)

        self._usage_current_label = QtWidgets.QLabel("本次请求: —")
        self._usage_current_label.setStyleSheet("color: #d4d4d4; font-size: 12px;")
        usage_layout.addWidget(self._usage_current_label)

        self._usage_session_label = QtWidgets.QLabel("本轮累计: 0")
        self._usage_session_label.setStyleSheet(
            "color: #4ec9b0; font-size: 13px; font-weight: bold;"
        )
        usage_layout.addWidget(self._usage_session_label)

        self._usage_alltime_label = QtWidgets.QLabel("历史总计: 0")
        self._usage_alltime_label.setStyleSheet(
            "color: #dcdcaa; font-size: 13px; font-weight: bold;"
        )
        usage_layout.addWidget(self._usage_alltime_label)

        self._usage_detail_label = QtWidgets.QLabel(
            "Prompt: — | Completion: — | Total: —"
        )
        self._usage_detail_label.setStyleSheet("color: #888888; font-size: 11px;")
        self._usage_detail_label.setWordWrap(True)
        usage_layout.addWidget(self._usage_detail_label)

        layout.addWidget(usage_group)

        # Load persisted all-time total
        self._alltime_tokens = int(config.get("ALLTIME_TOKENS", "0"))
        self._usage_alltime_label.setText(
            "历史总计: {} tokens".format(self._alltime_tokens)
        )

        # --- Save & Test buttons ---
        btn_row = QtWidgets.QHBoxLayout()
        btn_row.addStretch()

        self._status_msg = QtWidgets.QLabel("")
        self._status_msg.setObjectName("statusMsg")
        btn_row.addWidget(self._status_msg)

        test_btn = QtWidgets.QPushButton("测试连接")
        test_btn.setObjectName("testBtn")
        test_btn.clicked.connect(self._on_test_connection)
        btn_row.addWidget(test_btn)

        save_btn = QtWidgets.QPushButton("保存设置")
        save_btn.setObjectName("saveBtn")
        save_btn.clicked.connect(self._on_save)
        btn_row.addWidget(save_btn)
        layout.addLayout(btn_row)

        layout.addStretch()

        scroll.setWidget(content)

        outer = QtWidgets.QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)

        # Connect provider switch AFTER building all widgets
        self.preset_combo.currentIndexChanged.connect(self._on_preset_changed)

    # =====================================================================
    #  Provider Switch
    # =====================================================================

    def _on_preset_changed(self, index):
        """Called when user switches provider. Saves current provider's state,
        then loads the new provider's state (or defaults)."""
        if self._switching_provider:
            return
        self._switching_provider = True
        try:
            self._apply_provider(index)
        finally:
            self._switching_provider = False

    def _apply_provider(self, index):
        """Apply provider preset at *index*: fill Base URL, models, and
        restore per-provider saved config (API Key, model choice)."""
        if index < 0 or index >= len(PRESETS):
            return

        preset = PRESETS[index]

        # Update hint
        self.hint_label.setText(preset["hint"])

        # Update Base URL
        if preset["api_base"]:
            self.api_base_edit.setText(preset["api_base"])
        else:
            self.api_base_edit.clear()

        # Update placeholder
        self.api_key_edit.setPlaceholderText(preset["placeholder_key"])

        # Populate model combo with preset models
        self.model_combo.blockSignals(True)
        self.model_combo.clear()
        for m in preset.get("models", []):
            self.model_combo.addItem(m)
        # Always allow typing custom model names
        self.model_combo.setEditable(True)
        self.model_combo.blockSignals(False)

        # Try to restore per-provider saved config
        saved = self._load_provider_config(preset["name"])
        if saved:
            self.api_key_edit.setText(saved["api_key"])
            self._set_model_text(saved["model"])
            try:
                self.max_tokens_spin.setValue(int(saved["max_tokens"]))
            except (ValueError, TypeError):
                self.max_tokens_spin.setValue(4096)
        else:
            # No saved config for this provider: use defaults, clear key
            self.api_key_edit.clear()
            self._set_model_text(preset.get("default_model", ""))
            self.max_tokens_spin.setValue(4096)

    def _set_model_text(self, model_name):
        """Set the model combo to show *model_name*, selecting it from the list
        if possible, otherwise putting it in the edit field."""
        if not model_name:
            self.model_combo.setCurrentIndex(0 if self.model_combo.count() > 0 else -1)
            return
        idx = self.model_combo.findText(model_name)
        if idx >= 0:
            self.model_combo.setCurrentIndex(idx)
        else:
            self.model_combo.setEditText(model_name)

    def _current_model_text(self):
        """Return the current model name from the editable combo."""
        return self.model_combo.currentText().strip()

    def _toggle_key_visibility(self, checked):
        self.api_key_edit.setEchoMode(
            QtWidgets.QLineEdit.Normal if checked else QtWidgets.QLineEdit.Password
        )

    # =====================================================================
    #  Load / Save
    # =====================================================================

    def _load_current(self):
        """Load the active global config and auto-select provider."""
        cfg = config.load_config(force_reload=True)
        api_key = cfg.get("OPENAI_API_KEY", "")
        if api_key == "your_api_key_here":
            api_key = ""

        api_base = cfg.get("OPENAI_API_BASE", "https://api.openai.com/v1")
        model = cfg.get("OPENAI_MODEL", "gpt-4o")
        max_tokens = cfg.get("OPENAI_MAX_TOKENS", "4096")

        # Find matching provider
        matched_idx = len(PRESETS) - 1  # default to Custom
        api_base_lower = api_base.lower().rstrip("/")
        for i, preset in enumerate(PRESETS):
            if preset["api_base"] and preset["api_base"].lower().rstrip("/") == api_base_lower:
                matched_idx = i
                break

        # Apply provider (this will try to load per-provider saved data)
        self._switching_provider = True
        self.preset_combo.setCurrentIndex(matched_idx)
        self._switching_provider = False

        # Override with actual global values (these are the "current active" ones)
        self.api_key_edit.setText(api_key)
        self.api_base_edit.setText(api_base)

        # Populate model combo for the matched preset
        preset = PRESETS[matched_idx]
        self.model_combo.blockSignals(True)
        self.model_combo.clear()
        for m in preset.get("models", []):
            self.model_combo.addItem(m)
        self.model_combo.setEditable(True)
        self.model_combo.blockSignals(False)
        self._set_model_text(model)

        try:
            self.max_tokens_spin.setValue(int(max_tokens))
        except (ValueError, TypeError):
            self.max_tokens_spin.setValue(4096)

        # Update hint
        self.hint_label.setText(preset["hint"])

    def reload_config(self):
        """Public method called when switching to the settings tab."""
        self._load_current()
        self._status_msg.setText("")

    def _on_save(self):
        api_key = self.api_key_edit.text().strip()
        api_base = self.api_base_edit.text().strip()
        model = self._current_model_text()
        max_tokens = self.max_tokens_spin.value()

        if not api_base:
            api_base = "https://api.openai.com/v1"
        if not model:
            model = "gpt-4o"

        # Save global active config
        data = {
            "OPENAI_API_KEY": api_key,
            "OPENAI_API_BASE": api_base,
            "OPENAI_MODEL": model,
            "OPENAI_MAX_TOKENS": str(max_tokens),
        }
        config.save_config(data)

        # Also save per-provider config so it's remembered on switch
        idx = self.preset_combo.currentIndex()
        if 0 <= idx < len(PRESETS):
            self._save_provider_config(PRESETS[idx]["name"], api_key, model, max_tokens)

        if not api_key:
            self._status_msg.setStyleSheet("color: #dcdcaa; font-size: 12px;")
            self._status_msg.setText("✓ 已保存（API Key 为空，对话前请填写）")
        else:
            self._status_msg.setStyleSheet("color: #4ec9b0; font-size: 12px;")
            self._status_msg.setText("✓ 已保存")

        QtCore.QTimer.singleShot(3000, lambda: self._status_msg.setText(""))

    # =====================================================================
    #  Test Connection
    # =====================================================================

    def _on_test_connection(self):
        """Test API connectivity with a minimal request."""
        api_key = self.api_key_edit.text().strip()
        api_base = self.api_base_edit.text().strip() or "https://api.openai.com/v1"
        model = self._current_model_text() or "gpt-4o"

        if not api_key:
            self._status_msg.setStyleSheet("color: #f44747; font-size: 12px;")
            self._status_msg.setText("请先填写 API Key")
            return

        self._status_msg.setStyleSheet("color: #888888; font-size: 12px;")
        self._status_msg.setText("测试连接中...")
        QtWidgets.QApplication.processEvents()

        url = api_base.rstrip("/") + "/chat/completions"
        payload = {
            "model": model,
            "messages": [{"role": "user", "content": "Hi"}],
            "max_tokens": 5,
        }
        headers = {
            "Content-Type": "application/json",
            "Authorization": "Bearer {}".format(api_key),
        }

        try:
            data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            req = urllib_request.Request(url, data=data, headers=headers, method="POST")
            with urllib_request.urlopen(req, timeout=15) as resp:
                body = resp.read().decode("utf-8")
                result = json.loads(body)
                model_used = result.get("model", model)
                self._status_msg.setStyleSheet("color: #4ec9b0; font-size: 12px;")
                self._status_msg.setText("✓ 连接成功 (model: {})".format(model_used))
        except HTTPError as e:
            hints = {
                401: "API Key 无效",
                403: "权限不足",
                404: "端点/模型不存在",
                429: "请求过快",
            }
            hint = hints.get(e.code, "HTTP {}".format(e.code))
            self._status_msg.setStyleSheet("color: #f44747; font-size: 12px;")
            self._status_msg.setText("✗ 连接失败: {}".format(hint))
        except URLError as e:
            self._status_msg.setStyleSheet("color: #f44747; font-size: 12px;")
            self._status_msg.setText("✗ 网络错误: {}".format(e.reason))
        except Exception as e:
            self._status_msg.setStyleSheet("color: #f44747; font-size: 12px;")
            self._status_msg.setText("✗ 错误: {}".format(str(e)[:80]))

        QtCore.QTimer.singleShot(8000, lambda: self._status_msg.setText(""))

    # =====================================================================
    #  Token Usage (called externally by ChatWidget)
    # =====================================================================

    def update_usage(self, prompt_tokens, completion_tokens, total_tokens, session_total):
        """Update the token usage display. Called by ChatWidget._on_usage."""
        self._usage_current_label.setText(
            "本次请求: {} tokens".format(total_tokens)
        )
        self._usage_session_label.setText(
            "本轮累计: {} tokens".format(session_total)
        )
        self._usage_detail_label.setText(
            "Prompt: {} | Completion: {} | Total: {}".format(
                prompt_tokens, completion_tokens, total_tokens
            )
        )
        self._alltime_tokens += total_tokens
        self._usage_alltime_label.setText(
            "历史总计: {} tokens".format(self._alltime_tokens)
        )
        config.save_config({"ALLTIME_TOKENS": str(self._alltime_tokens)})

    def reset_usage(self):
        """Reset the token usage display (e.g. on new conversation)."""
        self._usage_current_label.setText("本次请求: —")
        self._usage_session_label.setText("本轮累计: 0")
        self._usage_detail_label.setText("Prompt: — | Completion: — | Total: —")
