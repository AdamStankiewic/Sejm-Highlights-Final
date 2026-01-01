"""Template registry for Shorts generation.

This module provides a clean registration system for video templates,
making it easy to add new layouts and expose them to the GUI.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional, Type

from .base import TemplateBase

# Try to import templates, fail gracefully if MoviePy not available
try:
    from .gaming import GamingTemplate
except (ImportError, ModuleNotFoundError):
    GamingTemplate = None

try:
    from .universal import UniversalTemplate
except (ImportError, ModuleNotFoundError):
    UniversalTemplate = None


@dataclass
class TemplateMetadata:
    """Metadata for a registered template"""
    name: str  # Internal name (e.g., "gaming")
    display_name: str  # User-friendly name for GUI (e.g., "Gaming Facecam")
    description: str  # Short description
    template_class: Type[TemplateBase]  # Actual template class
    preview_image: Optional[Path] = None  # Optional preview screenshot
    requires_face_detection: bool = False  # Whether template uses face detection
    recommended_for: str = ""  # E.g., "Gaming streams", "IRL content"


# Global template registry
_REGISTRY: Dict[str, TemplateMetadata] = {}


def register_template(
    name: str,
    display_name: str,
    description: str,
    template_class: Type[TemplateBase],
    preview_image: Optional[Path] = None,
    requires_face_detection: bool = False,
    recommended_for: str = ""
):
    """Register a new template in the global registry

    Args:
        name: Internal template name
        display_name: User-friendly display name
        description: Short description
        template_class: Template class (must inherit from TemplateBase)
        preview_image: Optional path to preview image
        requires_face_detection: Whether template needs face detection
        recommended_for: Use case recommendation

    Example:
        register_template(
            name="gaming",
            display_name="Gaming Facecam",
            description="Auto-detect facecam, PIP layout for gaming streams",
            template_class=GamingTemplate,
            requires_face_detection=True,
            recommended_for="Gaming streams with facecam"
        )
    """
    _REGISTRY[name] = TemplateMetadata(
        name=name,
        display_name=display_name,
        description=description,
        template_class=template_class,
        preview_image=preview_image,
        requires_face_detection=requires_face_detection,
        recommended_for=recommended_for
    )


def get_template(name: str, **kwargs) -> TemplateBase:
    """Get template instance by name

    Args:
        name: Template name
        **kwargs: Arguments to pass to template constructor

    Returns:
        Template instance

    Raises:
        ValueError: If template not found
    """
    if name not in _REGISTRY:
        available = ', '.join(_REGISTRY.keys())
        raise ValueError(
            f"Template '{name}' not found. Available templates: {available}"
        )

    metadata = _REGISTRY[name]
    return metadata.template_class(**kwargs)


def list_templates() -> Dict[str, TemplateMetadata]:
    """Get all registered templates

    Returns:
        Dict mapping template names to metadata
    """
    return _REGISTRY.copy()


def get_template_metadata(name: str) -> Optional[TemplateMetadata]:
    """Get metadata for specific template

    Args:
        name: Template name

    Returns:
        TemplateMetadata or None if not found
    """
    return _REGISTRY.get(name)


# Register built-in templates (only if import succeeded)
if GamingTemplate is not None:
    register_template(
        name="gaming",
        display_name="Gaming Facecam",
        description="Auto-detect facecam and create PIP layout. Best for gaming streams.",
        template_class=GamingTemplate,
        requires_face_detection=True,
        recommended_for="Gaming streams with visible facecam"
    )

if UniversalTemplate is not None:
    register_template(
        name="universal",
        display_name="Universal Crop",
        description="Simple 9:16 center crop. Works with any content.",
        template_class=UniversalTemplate,
        requires_face_detection=False,
        recommended_for="General content, talks, IRL streams without facecam"
    )


# Expose commonly used items
__all__ = [
    'TemplateBase',
    'TemplateMetadata',
    'GamingTemplate',
    'UniversalTemplate',
    'register_template',
    'get_template',
    'list_templates',
    'get_template_metadata',
]
