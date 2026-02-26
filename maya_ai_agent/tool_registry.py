# -*- coding: utf-8 -*-
"""
Tool Registry - Central registry for all Maya tools available to the AI Agent.

Each tool is registered with:
    - A Python callable (the actual implementation)
    - An OpenAI-compatible JSON Schema (for Function Calling)

Tools are discovered and registered at import time.
"""


class ToolRegistry:
    """Singleton registry that holds all available tools."""

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._tools = {}
        return cls._instance

    def register(self, name, func, schema):
        """
        Register a tool.

        Args:
            name (str): Unique tool name (must match schema function name).
            func (callable): Python function to execute.
            schema (dict): OpenAI-compatible tool schema.
        """
        self._tools[name] = {
            "func": func,
            "schema": schema,
        }

    def get_func(self, name):
        """Get the callable for a registered tool."""
        entry = self._tools.get(name)
        return entry["func"] if entry else None

    def get_all_schemas(self):
        """Get list of all tool schemas for the LLM API request."""
        return [entry["schema"] for entry in self._tools.values()]

    def get_all_names(self):
        """Get list of all registered tool names."""
        return list(self._tools.keys())

    def has_tool(self, name):
        """Check if a tool is registered."""
        return name in self._tools

    def clear(self):
        """Clear all registered tools (for testing)."""
        self._tools.clear()


# Module-level convenience accessor
registry = ToolRegistry()


def tool(name, description, parameters):
    """
    Decorator to register a function as an AI-callable tool.

    Usage:
        @tool(
            name="my_tool",
            description="Does something useful",
            parameters={
                "type": "object",
                "properties": {
                    "arg1": {"type": "string", "description": "..."},
                },
                "required": ["arg1"],
            },
        )
        def my_tool(arg1):
            ...

    Args:
        name: Unique tool name.
        description: Human-readable description for the LLM.
        parameters: JSON Schema for the function parameters.
    """
    def decorator(func):
        schema = {
            "type": "function",
            "function": {
                "name": name,
                "description": description,
                "parameters": parameters,
            },
        }
        registry.register(name, func, schema)
        return func
    return decorator
