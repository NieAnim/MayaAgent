## Maya AI Agent v1.0.0 - Initial Release

An AI-powered assistant panel for Autodesk Maya, integrating LLM with Function Calling to automate Maya operations.

### Features
- 🎯 Three-layer response strategy: shortcuts → cache → LLM API
- 🔧 20+ built-in Maya tools (rigging, animation, export, mocap)
- 🐍 `execute_python_code` universal fallback for unlimited Maya operations
- 📡 SSE streaming response display
- 🪟 Dockable Maya workspace panel (Maya 2022-2025+)
- 💬 JSONL persistent chat history with fuzzy matching
- ⚙️ Configurable API endpoint (OpenAI, Ollama, etc.)
- 🔀 PySide2/PySide6 compatibility layer

### Setup
1. Copy `maya_ai_agent/.env.example` to `maya_ai_agent/.env`
2. Fill in your API key
3. In Maya Script Editor run:
   ```python
   from maya_ai_agent.main import launch
   launch()
