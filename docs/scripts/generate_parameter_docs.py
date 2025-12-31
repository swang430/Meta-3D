#!/usr/bin/env python3
"""
Auto-generate parameter reference documentation from Pydantic schemas.

Usage:
    cd api-service
    python ../docs/scripts/generate_parameter_docs.py

Output:
    docs/features/virtual-road-test/parameter-reference-generated.md
"""

import ast
import os
import sys
from pathlib import Path
from typing import Dict, List, Any, Optional
from datetime import datetime

# Add api-service to path
API_SERVICE_PATH = Path(__file__).parent.parent.parent / "api-service"
sys.path.insert(0, str(API_SERVICE_PATH))


def extract_pydantic_fields(file_path: Path) -> Dict[str, List[Dict[str, Any]]]:
    """Extract field definitions from a Python file containing Pydantic models."""

    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()

    try:
        tree = ast.parse(content)
    except SyntaxError:
        return {}

    models = {}

    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            # Check if it's a Pydantic model (inherits from BaseModel)
            is_pydantic = False
            for base in node.bases:
                if isinstance(base, ast.Name) and base.id in ('BaseModel', 'Base'):
                    is_pydantic = True
                    break

            if not is_pydantic:
                continue

            fields = []
            docstring = ast.get_docstring(node)

            for item in node.body:
                if isinstance(item, ast.AnnAssign) and item.target:
                    field_name = item.target.id if isinstance(item.target, ast.Name) else None
                    if not field_name or field_name.startswith('_'):
                        continue

                    # Extract type annotation
                    type_str = ast.unparse(item.annotation) if item.annotation else "Any"

                    # Extract default value and Field() info
                    default = None
                    description = None
                    required = True

                    if item.value:
                        value_str = ast.unparse(item.value)

                        # Parse Field() calls
                        if isinstance(item.value, ast.Call):
                            if isinstance(item.value.func, ast.Name) and item.value.func.id == 'Field':
                                # Extract Field arguments
                                for arg in item.value.args:
                                    if isinstance(arg, ast.Constant):
                                        if arg.value is ...:
                                            required = True
                                        else:
                                            default = arg.value
                                            required = False

                                for kwarg in item.value.keywords:
                                    if kwarg.arg == 'default':
                                        if isinstance(kwarg.value, ast.Constant):
                                            default = kwarg.value.value
                                        required = False
                                    elif kwarg.arg == 'description':
                                        if isinstance(kwarg.value, ast.Constant):
                                            description = kwarg.value.value
                        else:
                            # Direct value assignment
                            if isinstance(item.value, ast.Constant):
                                default = item.value.value
                                required = False

                    # Handle Optional types
                    if 'Optional' in type_str:
                        required = False

                    fields.append({
                        'name': field_name,
                        'type': type_str,
                        'default': default,
                        'description': description,
                        'required': required
                    })

            if fields:
                models[node.name] = {
                    'docstring': docstring,
                    'fields': fields
                }

    return models


def format_type(type_str: str) -> str:
    """Format type annotation for display."""
    # Simplify common types
    type_str = type_str.replace('typing.', '')
    type_str = type_str.replace('Optional[', '').rstrip(']')
    type_str = type_str.replace('List[', 'list[')
    type_str = type_str.replace('Dict[', 'dict[')
    return type_str


def generate_markdown_table(model_name: str, model_info: Dict) -> str:
    """Generate markdown table for a model."""
    lines = []

    # Model header
    docstring = model_info.get('docstring', '')
    lines.append(f"### {model_name}")
    if docstring:
        lines.append(f"\n{docstring}\n")
    lines.append("")

    # Table header
    lines.append("| Parameter | Type | Required | Default | Description |")
    lines.append("|-----------|------|----------|---------|-------------|")

    # Table rows
    for field in model_info['fields']:
        name = f"`{field['name']}`"
        type_str = format_type(field['type'])
        required = "Yes" if field['required'] else "No"
        default = str(field['default']) if field['default'] is not None else "-"
        description = field['description'] or "-"

        lines.append(f"| {name} | {type_str} | {required} | {default} | {description} |")

    lines.append("")
    return "\n".join(lines)


def generate_documentation() -> str:
    """Generate complete parameter documentation."""

    schemas_path = API_SERVICE_PATH / "app" / "schemas"

    # Schema files to process (in order)
    schema_files = [
        ("road_test/scenario.py", "Virtual Road Test - Scenario"),
        ("test_plan.py", "Test Management"),
        ("calibration.py", "Calibration"),
        ("instrument.py", "Instrument"),
        ("channel_params.py", "Channel Parameters"),
        ("probe.py", "Probe"),
        ("sync.py", "Synchronization"),
    ]

    lines = [
        "# Parameter Reference (Auto-Generated)",
        "",
        f"> Generated at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "> Source: `api-service/app/schemas/`",
        "",
        "This document is auto-generated from Pydantic schema definitions.",
        "Run `python docs/scripts/generate_parameter_docs.py` to regenerate.",
        "",
        "---",
        ""
    ]

    toc_lines = ["## Table of Contents\n"]
    content_lines = []

    for file_path, section_name in schema_files:
        full_path = schemas_path / file_path
        if not full_path.exists():
            continue

        models = extract_pydantic_fields(full_path)
        if not models:
            continue

        # Add section header
        section_id = section_name.lower().replace(' ', '-').replace('/', '-')
        toc_lines.append(f"- [{section_name}](#{section_id})")

        content_lines.append(f"## {section_name}")
        content_lines.append(f"\nSource: `{file_path}`\n")

        for model_name, model_info in models.items():
            # Skip internal/response models for cleaner docs
            if any(x in model_name for x in ['Response', 'List', 'Summary']):
                continue

            content_lines.append(generate_markdown_table(model_name, model_info))

        content_lines.append("---\n")

    lines.extend(toc_lines)
    lines.append("\n---\n")
    lines.extend(content_lines)

    return "\n".join(lines)


def main():
    """Main entry point."""

    # Change to api-service directory for imports
    os.chdir(API_SERVICE_PATH)

    # Generate documentation
    doc_content = generate_documentation()

    # Output path
    output_path = Path(__file__).parent.parent / "features" / "virtual-road-test" / "parameter-reference-generated.md"

    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(doc_content)

    print(f"Generated: {output_path}")
    print(f"Lines: {len(doc_content.splitlines())}")


if __name__ == "__main__":
    main()
