# Maya AI Agent

An AI-powered assistant panel for Autodesk Maya, integrating LLM with Function Calling to automate Maya operations through natural language.

> Compatible with Maya 2022 – 2025+ (Python 3 / PySide2 & PySide6)

---

## Features

### Core Architecture
- **Three-layer response strategy**: Command Shortcuts → Response Cache → LLM API
- **26 built-in tools** across 7 categories with `@tool` decorator auto-registration
- **`execute_python_code`** universal fallback — any Maya operation the AI can imagine
- **Prompt Caching optimization** — static system prompt + dynamic context separation maximizes API cache hit rate
- **Sliding window context** — keeps last 10 conversation rounds without breaking tool call sequences

### UI & Interaction
- Dockable workspace panel (docks beside Attribute Editor by default)
- SSE streaming response with smooth text append (no flickering)
- Markdown rendering with syntax-highlighted code blocks
- DeepSeek Reasoner thought chain display (purple bubble)
- Confirmation dialog before executing any Maya operation
- Stop generation button for long responses

### Multi-Provider Support
| Provider | Default Model |
|----------|---------------|
| OpenAI | `gpt-4o` |
| DeepSeek | `deepseek-chat` |
| Google Gemini | `gemini-2.5-flash` |
| Anthropic Claude | `claude-sonnet-4-20250514` |
| Ollama (Local) | `qwen2.5:14b` |
| OpenRouter | `deepseek/deepseek-chat` |
| Custom | Any OpenAI-compatible endpoint |

### Token & History Management
- **Token usage tracking**: per-request / per-session / all-time total (persistent)
- **JSONL chat history** with session-based recording and fuzzy search
- **Resume conversation**: restore a full historical session and continue chatting
- **Response caching**: identical queries return instantly from local cache

---

## Built-in Tools (26)

### Maya Basics (3)
| Tool | Description |
|------|-------------|
| `zero_out_transforms` | Reset translate/rotate to 0, scale to 1 |
| `create_locator_at_selection` | Create locator at selected object's position |
| `set_keyframe` | Set keyframe on specified frame/attribute |

### Animation (3)
| Tool | Description |
|------|-------------|
| `euler_filter` | Fix gimbal lock with Euler angle filter |
| `mirror_controller_pose` | Mirror pose using L_/R_, Left/Right naming |
| `smooth_animation_curves` | Reduce noise by iterative neighbor averaging |

### Rigging (7)
| Tool | Description |
|------|-------------|
| `create_joints` | Create joint chains with name/position/parent |
| `bind_skin` | Smooth bind mesh to joints |
| `copy_skin_weights` | Transfer skin weights between meshes |
| `create_constraint` | Parent/Point/Orient/Scale/Aim/PoleVector constraints |
| `create_ik_handle` | IK handles (RP/SC/Spline solvers) |
| `add_blendshape` | Add BlendShape deformer |
| `orient_joints` | Reorient joint axes |

### Workflow (8)
| Tool | Description |
|------|-------------|
| `batch_rename` | Template/find-replace/prefix-suffix batch rename |
| `smart_select` | Select by name pattern, node type, hierarchy |
| `qa_check_transforms` | QA check if controllers are zeroed out |
| `create_controllers_for_joints` | Auto-create NURBS circle controllers |
| `delete_objects` | Delete objects with optional history cleanup |
| `freeze_transformations` | Freeze translate/rotate/scale |
| `center_pivot` | Center pivot to bounding box |
| `delete_history` | Delete construction history |

### Import / Export (2)
| Tool | Description |
|------|-------------|
| `export_fbx` | Export FBX with animation/skin/blendshape options |
| `import_fbx` | Import FBX (add/merge/exmerge modes) |

### Motion Capture (2)
| Tool | Description |
|------|-------------|
| `generate_root_motion` | Extract root motion from pelvis for UE |
| `cleanup_finger_animation` | Clean AI mocap finger noise (16+ skeleton types) |

### Code Execution (1)
| Tool | Description |
|------|-------------|
| `execute_python_code` | Execute arbitrary Python in Maya (with safety checks) |

---

## Command Shortcuts (Zero-latency)

These bypass the LLM entirely for instant execution:

| Command (CN / EN) | Action |
|-------------------|--------|
| 清零 / zero out | Reset transforms |
| 打帧 / set key | Set keyframe |
| 在第N帧打帧 | Set keyframe at frame N |
| 创建locator | Create locator at selection |
| 欧拉滤波 / euler filter | Euler angle filter |
| 冻结 / freeze | Freeze transformations |
| 居中轴心 / center pivot | Center pivot |
| 删除历史 / delete history | Delete history |
| qa检查 / 检查归零 | QA check transforms |
| 删除 / delete | Delete selected objects |

---

## Setup

### 1. Load into Maya

Make sure the project directory is in Maya's Python path, then run in **Script Editor (Python)**:

```python
import sys
sys.path.insert(0, r"/path/to/Maya Agent")

from maya_ai_agent.main import launch
launch()
```

Or add to a shelf button for one-click access.

### 2. Configure API Key (inside Maya)

On first launch, the plugin will **auto-create** a default `.env` config file — no need to manually copy or edit any files.

1. The chat panel will prompt you to configure settings and **auto-switch to the Settings page**
2. Select a **provider preset** (DeepSeek / Gemini / OpenAI / Ollama / OpenRouter / ...)
3. Click **Apply** to fill in Base URL and Model
4. Enter your **API Key**
5. Click **Test Connection** to verify → then **Save**

> You can also manually edit `maya_ai_agent/.env` if preferred.

---

## Context Awareness

Every request automatically injects real-time Maya state:

| Context | Info |
|---------|------|
| **Scene** | File name, unsaved changes, up axis, linear unit |
| **Timeline** | Current frame, playback range, FPS |
| **Selection** | Selected objects with name, type, shape (up to 50) |
| **Statistics** | DAG nodes, transforms, meshes, joints, cameras, lights, curves |

---

## Project Structure

```
maya_ai_agent/
├── __init__.py          # Version info
├── main.py              # Launch & workspace docking
├── chat_widget.py       # Main chat UI (streaming, tool calls, history)
├── settings_widget.py   # Settings page (providers, test connection, token stats)
├── settings_dialog.py   # Settings dialog wrapper
├── llm_worker.py        # LLM API worker thread (streaming, retry, usage)
├── prompt_builder.py    # System prompt + tool schema + context injection
├── context_fetcher.py   # Real-time Maya scene context
├── tool_registry.py     # @tool decorator & global registry
├── command_shortcut.py  # Zero-latency shortcut commands
├── action_executor.py   # Safe tool execution with undo chunks
├── confirm_dialog.py    # User confirmation before Maya operations
├── history_manager.py   # JSONL session-based history
├── history_widget.py    # History browser with search & resume
├── response_cache.py    # LRU response cache
├── markdown_renderer.py # Markdown → HTML rendering
├── logger.py            # Structured logging ([MayaAIAgent] prefix)
├── config.py            # .env config management
├── qt_compat.py         # PySide2/PySide6 compatibility
└── tools/
    ├── __init__.py          # Safe import & tool module loading
    ├── maya_tools.py        # Basic Maya operations
    ├── anim_tools.py        # Animation tools
    ├── rigging_tools.py     # Rigging tools
    ├── workflow_tools.py    # Naming, QA, batch operations
    ├── export_tools.py      # FBX import/export
    ├── mocap_tools.py       # Motion capture processing
    └── execute_code_tool.py # Arbitrary Python execution
```

---

## Changelog

### v1.3.0 — Token Tracking & History Resume
- Token usage panel in Settings (current / session / all-time persistent total)
- Top bar mini token label with live usage display
- **Continue Conversation** button in history to restore full session context
- Resumed sessions maintain complete LLM conversation history
- **In-Maya setup**: auto-create `.env` on first launch, configure API Key directly in Settings page (no manual file editing needed)

### v1.2.0 — Streaming & Quality of Life
- Streaming output optimization (no flickering, smooth append)
- Token usage statistics (prompt / completion / total)
- **Test Connection** button in settings
- DeepSeek `reasoning_content` thought chain display
- Cache path fix (Maya user dir instead of package dir)
- Auto-retry on 429/500/502/503 (up to 3 attempts)
- Structured logging system (`[MayaAIAgent]` prefix)
- `stream_options` with auto-fallback for unsupported providers
- Markdown renderer for rich text formatting

### v1.1.0 — Modular Tool System
- Safe import mechanism (`_safe_import`) — one broken tool won't break others
- 7 tool categories with automatic discovery and registration
- Tool registry with `@tool` decorator

### v1.0.0 — Initial Release
- LLM-powered AI assistant docked in Maya
- Multi-provider support (OpenAI, DeepSeek, Gemini, Ollama, OpenRouter)
- 26 built-in tools with Function Calling
- Command shortcuts for zero-latency common operations
- SSE streaming responses with Markdown rendering
- JSONL persistent chat history with fuzzy search
- Response caching for repeated queries
- Real-time Maya context awareness
- Confirmation dialog before executing operations
- PySide2/PySide6 compatibility (Maya 2022+)

---

## License

MIT
