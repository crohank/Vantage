"""
Prompt Manager

Loads, renders, and version-manages prompt templates stored as YAML files.
"""

import os
import re
import yaml
from typing import Dict, Any, Optional, List


PROMPTS_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "prompts")


def _prompt_path(name: str, version: int) -> str:
    """Return the file path for a given prompt name and version."""
    return os.path.join(PROMPTS_DIR, f"{name}_v{version}.yaml")


def load_prompt(name: str, version: Optional[int] = None) -> Dict[str, Any]:
    """
    Load a prompt template by name and optional version.
    If version is None, loads the latest version available.

    Args:
        name: Prompt name (e.g., "risk_analysis")
        version: Specific version number, or None for latest

    Returns:
        Dict with keys: name, version, template, variables, model_target, temperature, description
    """
    if version is not None:
        path = _prompt_path(name, version)
        if not os.path.exists(path):
            raise FileNotFoundError(f"Prompt not found: {path}")
        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)

    # Find latest version
    versions = list_versions(name)
    if not versions:
        raise FileNotFoundError(f"No prompt versions found for: {name}")
    latest = max(versions)
    return load_prompt(name, latest)


def render_prompt(name: str, variables: Dict[str, Any], version: Optional[int] = None) -> str:
    """
    Load a prompt template and render it with the given variables.

    Args:
        name: Prompt name
        variables: Dict of variable values to substitute
        version: Optional specific version

    Returns:
        Rendered prompt string
    """
    prompt_data = load_prompt(name, version)
    template = prompt_data.get("template", "")

    # Use format_map for safe substitution (missing keys stay as {key})
    class SafeDict(dict):
        def __missing__(self, key):
            return f"{{{key}}}"

    return template.format_map(SafeDict(**variables))


def list_versions(name: str) -> List[int]:
    """
    List all available versions for a given prompt name.

    Args:
        name: Prompt name

    Returns:
        Sorted list of version numbers
    """
    if not os.path.isdir(PROMPTS_DIR):
        return []

    versions = []
    pattern = re.compile(rf"^{re.escape(name)}_v(\d+)\.yaml$")
    for filename in os.listdir(PROMPTS_DIR):
        match = pattern.match(filename)
        if match:
            versions.append(int(match.group(1)))
    return sorted(versions)


def get_prompt_metadata(name: str, version: Optional[int] = None) -> Dict[str, Any]:
    """
    Get metadata for a prompt without the full template.

    Returns:
        Dict with name, version, model_target, temperature, description
    """
    data = load_prompt(name, version)
    return {
        "name": data.get("name"),
        "version": data.get("version"),
        "model_target": data.get("model_target"),
        "temperature": data.get("temperature"),
        "description": data.get("description"),
        "variables": data.get("variables", []),
    }
