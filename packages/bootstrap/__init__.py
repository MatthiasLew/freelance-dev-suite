"""Bootstrap package — project scaffolding from templates."""

from .scaffolder import ProjectScaffolder, ScaffoldResult, scaffold_project
from .templates import (
    TEMPLATES,
    TemplateInfo,
    generate_template_files,
    get_template,
    list_templates,
)

__all__ = [
    "TEMPLATES",
    "ProjectScaffolder",
    "ScaffoldResult",
    "TemplateInfo",
    "generate_template_files",
    "get_template",
    "list_templates",
    "scaffold_project",
]
