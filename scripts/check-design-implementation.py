#!/usr/bin/env python3
"""
Design-Implementation Gap Checker

Scans design documents for defined components/interfaces and compares
against the actual codebase to generate a gap report.

Usage:
    python scripts/check-design-implementation.py

Output:
    - docs/reports/design-implementation-gap.md (human-readable)
    - docs/reports/design-implementation-gap.json (machine-readable)
"""

import re
import json
from pathlib import Path
from datetime import datetime
from dataclasses import dataclass, field, asdict
from typing import Optional
from enum import Enum


class ImplementationStatus(Enum):
    IMPLEMENTED = "implemented"
    NOT_IMPLEMENTED = "not_implemented"
    PARTIAL = "partial"


@dataclass
class DesignItem:
    """Represents a designed component/interface"""
    name: str
    item_type: str  # interface, enum, type, component, api
    source_file: str
    source_line: int
    status: ImplementationStatus = ImplementationStatus.NOT_IMPLEMENTED
    implementation_path: Optional[str] = None
    notes: str = ""


@dataclass
class GapReport:
    """Final gap report"""
    generated_at: str
    total_designed: int = 0
    total_implemented: int = 0
    total_partial: int = 0
    total_not_implemented: int = 0
    items: list = field(default_factory=list)


# ============ Configuration ============

PROJECT_ROOT = Path(__file__).parent.parent
DESIGN_DOCS = [
    PROJECT_ROOT / "docs/features/virtual-road-test/implementation.md",
    PROJECT_ROOT / "docs/features/virtual-road-test/architecture.md",
]
CODE_DIRS = {
    "types": PROJECT_ROOT / "gui/src/types",
    "components": PROJECT_ROOT / "gui/src/components",
    "api": PROJECT_ROOT / "gui/src/api",
    "schemas": PROJECT_ROOT / "api-service/app/schemas",
}
OUTPUT_DIR = PROJECT_ROOT / "docs/reports"


# ============ Markdown Parser ============

def extract_typescript_definitions(content: str, source_file: str) -> list[DesignItem]:
    """Extract TypeScript interface/enum/type definitions from markdown code blocks"""
    items = []

    # Find all TypeScript code blocks
    ts_blocks = re.findall(r'```typescript\n(.*?)```', content, re.DOTALL)

    for block in ts_blocks:
        # Find line number for this block in original content
        block_start = content.find(block)
        line_num = content[:block_start].count('\n') + 1

        # Extract exports
        patterns = [
            (r'export\s+interface\s+(\w+)', 'interface'),
            (r'export\s+enum\s+(\w+)', 'enum'),
            (r'export\s+type\s+(\w+)', 'type'),
            (r'export\s+class\s+(\w+)', 'class'),
        ]

        for pattern, item_type in patterns:
            for match in re.finditer(pattern, block):
                name = match.group(1)
                # Calculate approximate line number within block
                match_line = block[:match.start()].count('\n')
                items.append(DesignItem(
                    name=name,
                    item_type=item_type,
                    source_file=str(source_file),
                    source_line=line_num + match_line,
                ))

    return items


def extract_component_names(content: str, source_file: str) -> list[DesignItem]:
    """Extract component names from markdown section headers"""
    items = []

    # Pattern: ### X.X ComponentName (EnglishName)
    # or file paths like: TopologyConfigurator/
    patterns = [
        (r'###\s+[\d.]+\s+(\w+配置器)\s*\((\w+)\)', 'component'),
        (r'###\s+[\d.]+\s+(\w+编辑器)\s*\((\w+)\)', 'component'),
        (r'├──\s+(\w+)/\s+#\s+(.+)', 'component'),
        (r'(\w+Configurator)', 'component'),
        (r'(\w+Editor)(?!\s*\()', 'component'),
    ]

    lines = content.split('\n')
    for i, line in enumerate(lines):
        for pattern, item_type in patterns:
            matches = re.findall(pattern, line)
            for match in matches:
                name = match[1] if isinstance(match, tuple) and len(match) > 1 else match
                if isinstance(match, tuple):
                    name = match[1] if match[1] else match[0]
                else:
                    name = match

                # Filter out common false positives
                if name in ['StepEditor', 'BaseEditor', 'DefaultEditor']:
                    continue

                # Avoid duplicates
                if not any(item.name == name for item in items):
                    items.append(DesignItem(
                        name=name,
                        item_type=item_type,
                        source_file=str(source_file),
                        source_line=i + 1,
                    ))

    return items


def extract_api_functions(content: str, source_file: str) -> list[DesignItem]:
    """Extract API function definitions from markdown"""
    items = []

    # Pattern: export async function fetchXXX
    ts_blocks = re.findall(r'```typescript\n(.*?)```', content, re.DOTALL)

    for block in ts_blocks:
        block_start = content.find(block)
        line_num = content[:block_start].count('\n') + 1

        # Find API function exports
        pattern = r'export\s+async\s+function\s+(\w+)'
        for match in re.finditer(pattern, block):
            name = match.group(1)
            match_line = block[:match.start()].count('\n')
            items.append(DesignItem(
                name=name,
                item_type='api_function',
                source_file=str(source_file),
                source_line=line_num + match_line,
            ))

    return items


# ============ Code Scanner ============

def scan_typescript_files(directory: Path) -> set[str]:
    """Scan TypeScript files for exported definitions"""
    exports = set()

    if not directory.exists():
        return exports

    for ts_file in directory.rglob("*.ts"):
        try:
            content = ts_file.read_text(encoding='utf-8')

            # Find exports
            patterns = [
                r'export\s+(?:interface|enum|type|class)\s+(\w+)',
                r'export\s+(?:const|function|async\s+function)\s+(\w+)',
            ]

            for pattern in patterns:
                for match in re.finditer(pattern, content):
                    exports.add(match.group(1))
        except Exception as e:
            print(f"Warning: Could not read {ts_file}: {e}")

    return exports


def scan_tsx_components(directory: Path) -> set[str]:
    """Scan TSX files for component definitions"""
    components = set()

    if not directory.exists():
        return components

    for tsx_file in directory.rglob("*.tsx"):
        try:
            content = tsx_file.read_text(encoding='utf-8')

            # Find exported function components
            patterns = [
                r'export\s+(?:default\s+)?function\s+(\w+)',
                r'export\s+const\s+(\w+)\s*[=:]',
            ]

            for pattern in patterns:
                for match in re.finditer(pattern, content):
                    name = match.group(1)
                    if name[0].isupper():  # Components start with uppercase
                        components.add(name)

            # Also add directory-based components
            if tsx_file.name == "index.tsx":
                components.add(tsx_file.parent.name)

        except Exception as e:
            print(f"Warning: Could not read {tsx_file}: {e}")

    return components


def scan_python_schemas(directory: Path) -> set[str]:
    """Scan Python files for Pydantic model definitions"""
    models = set()

    if not directory.exists():
        return models

    for py_file in directory.rglob("*.py"):
        try:
            content = py_file.read_text(encoding='utf-8')

            # Find class definitions that inherit from BaseModel or similar
            pattern = r'class\s+(\w+)\s*\('
            for match in re.finditer(pattern, content):
                models.add(match.group(1))

        except Exception as e:
            print(f"Warning: Could not read {py_file}: {e}")

    return models


def find_implementation(item: DesignItem, all_exports: dict) -> tuple[ImplementationStatus, Optional[str]]:
    """Check if a design item is implemented in the codebase"""
    name = item.name

    # Check in all export sets
    for location, exports in all_exports.items():
        if name in exports:
            return ImplementationStatus.IMPLEMENTED, location

        # Check for partial matches (e.g., NetworkTopology might be in types as part of another file)
        for export in exports:
            if name.lower() in export.lower() or export.lower() in name.lower():
                if len(name) > 5 and len(export) > 5:  # Avoid short false matches
                    return ImplementationStatus.PARTIAL, f"{location} (similar: {export})"

    return ImplementationStatus.NOT_IMPLEMENTED, None


# ============ Report Generator ============

def generate_markdown_report(report: GapReport) -> str:
    """Generate a human-readable markdown report"""

    implemented_pct = (report.total_implemented / report.total_designed * 100) if report.total_designed > 0 else 0
    partial_pct = (report.total_partial / report.total_designed * 100) if report.total_designed > 0 else 0
    not_impl_pct = (report.total_not_implemented / report.total_designed * 100) if report.total_designed > 0 else 0

    md = f"""# 设计-实现差距报告

> 自动生成时间: {report.generated_at}
>
> 此报告由 `scripts/check-design-implementation.py` 自动生成

---

## 摘要

| 指标 | 数量 | 百分比 |
|------|------|--------|
| 设计组件总数 | {report.total_designed} | 100% |
| ✅ 已实现 | {report.total_implemented} | {implemented_pct:.1f}% |
| ⚠️ 部分实现 | {report.total_partial} | {partial_pct:.1f}% |
| ❌ 未实现 | {report.total_not_implemented} | {not_impl_pct:.1f}% |

---

## 详细列表

### ❌ 未实现组件

| 名称 | 类型 | 设计文档位置 |
|------|------|-------------|
"""

    not_implemented = [i for i in report.items if i['status'] == 'not_implemented']
    for item in sorted(not_implemented, key=lambda x: (x['item_type'], x['name'])):
        source = Path(item['source_file']).name
        md += f"| `{item['name']}` | {item['item_type']} | {source}:L{item['source_line']} |\n"

    if not not_implemented:
        md += "| (无) | - | - |\n"

    md += """
### ⚠️ 部分实现组件

| 名称 | 类型 | 设计文档位置 | 备注 |
|------|------|-------------|------|
"""

    partial = [i for i in report.items if i['status'] == 'partial']
    for item in sorted(partial, key=lambda x: (x['item_type'], x['name'])):
        source = Path(item['source_file']).name
        md += f"| `{item['name']}` | {item['item_type']} | {source}:L{item['source_line']} | {item.get('notes', '')} |\n"

    if not partial:
        md += "| (无) | - | - | - |\n"

    md += """
### ✅ 已实现组件

| 名称 | 类型 | 实现位置 |
|------|------|---------|
"""

    implemented = [i for i in report.items if i['status'] == 'implemented']
    for item in sorted(implemented, key=lambda x: (x['item_type'], x['name'])):
        impl_path = item.get('implementation_path', '-')
        md += f"| `{item['name']}` | {item['item_type']} | {impl_path} |\n"

    if not implemented:
        md += "| (无) | - | - |\n"

    md += """
---

## 优先修复建议

基于组件类型的修复优先级:

1. **TypeScript 类型定义** (interface/type/enum) - 影响类型安全
2. **React 组件** - 影响用户界面功能
3. **API 函数** - 影响数据交互

---

## 如何使用此报告

1. 查看"未实现组件"列表
2. 在 `Master-Progress-Tracker.md` 中添加跟踪项
3. 按优先级实现缺失组件
4. 重新运行此脚本验证进度

```bash
# 运行检查脚本
python scripts/check-design-implementation.py
```
"""

    return md


def generate_json_report(report: GapReport) -> str:
    """Generate a machine-readable JSON report"""
    return json.dumps(asdict(report), indent=2, ensure_ascii=False)


# ============ Main ============

def main():
    print("=" * 60)
    print("Design-Implementation Gap Checker")
    print("=" * 60)

    # Collect all design items
    all_items: list[DesignItem] = []

    print("\n[1/4] Parsing design documents...")
    for doc_path in DESIGN_DOCS:
        if not doc_path.exists():
            print(f"  Warning: {doc_path} not found")
            continue

        print(f"  - {doc_path.name}")
        content = doc_path.read_text(encoding='utf-8')

        # Extract different types of definitions
        items = extract_typescript_definitions(content, doc_path)
        print(f"    Found {len(items)} TypeScript definitions")
        all_items.extend(items)

        api_items = extract_api_functions(content, doc_path)
        print(f"    Found {len(api_items)} API functions")
        all_items.extend(api_items)

        comp_items = extract_component_names(content, doc_path)
        print(f"    Found {len(comp_items)} component names")
        all_items.extend(comp_items)

    # Deduplicate by name
    seen_names = set()
    unique_items = []
    for item in all_items:
        if item.name not in seen_names:
            seen_names.add(item.name)
            unique_items.append(item)
    all_items = unique_items

    print(f"\nTotal unique design items: {len(all_items)}")

    # Scan codebase
    print("\n[2/4] Scanning codebase...")
    all_exports = {}

    # TypeScript types
    types_exports = scan_typescript_files(CODE_DIRS["types"])
    print(f"  - types/: {len(types_exports)} exports")
    all_exports["gui/src/types"] = types_exports

    # TSX components
    comp_exports = scan_tsx_components(CODE_DIRS["components"])
    print(f"  - components/: {len(comp_exports)} components")
    all_exports["gui/src/components"] = comp_exports

    # API functions
    api_exports = scan_typescript_files(CODE_DIRS["api"])
    print(f"  - api/: {len(api_exports)} exports")
    all_exports["gui/src/api"] = api_exports

    # Python schemas
    schema_exports = scan_python_schemas(CODE_DIRS["schemas"])
    print(f"  - schemas/: {len(schema_exports)} models")
    all_exports["api-service/app/schemas"] = schema_exports

    # Match design items against implementation
    print("\n[3/4] Comparing design vs implementation...")
    for item in all_items:
        status, impl_path = find_implementation(item, all_exports)
        item.status = status
        item.implementation_path = impl_path
        if impl_path and "similar" in str(impl_path):
            item.notes = impl_path

    # Generate report
    print("\n[4/4] Generating reports...")

    report = GapReport(
        generated_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        total_designed=len(all_items),
        total_implemented=sum(1 for i in all_items if i.status == ImplementationStatus.IMPLEMENTED),
        total_partial=sum(1 for i in all_items if i.status == ImplementationStatus.PARTIAL),
        total_not_implemented=sum(1 for i in all_items if i.status == ImplementationStatus.NOT_IMPLEMENTED),
        items=[{
            'name': i.name,
            'item_type': i.item_type,
            'source_file': i.source_file,
            'source_line': i.source_line,
            'status': i.status.value,
            'implementation_path': i.implementation_path,
            'notes': i.notes,
        } for i in all_items]
    )

    # Write reports
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    md_report = generate_markdown_report(report)
    md_path = OUTPUT_DIR / "design-implementation-gap.md"
    md_path.write_text(md_report, encoding='utf-8')
    print(f"  - Markdown report: {md_path}")

    json_report = generate_json_report(report)
    json_path = OUTPUT_DIR / "design-implementation-gap.json"
    json_path.write_text(json_report, encoding='utf-8')
    print(f"  - JSON report: {json_path}")

    # Print summary
    print("\n" + "=" * 60)
    print("Summary")
    print("=" * 60)
    print(f"  Total designed:     {report.total_designed}")
    print(f"  ✅ Implemented:     {report.total_implemented} ({report.total_implemented/report.total_designed*100:.1f}%)")
    print(f"  ⚠️  Partial:         {report.total_partial} ({report.total_partial/report.total_designed*100:.1f}%)")
    print(f"  ❌ Not implemented: {report.total_not_implemented} ({report.total_not_implemented/report.total_designed*100:.1f}%)")
    print("=" * 60)

    # List top unimplemented items
    not_impl = [i for i in all_items if i.status == ImplementationStatus.NOT_IMPLEMENTED]
    if not_impl:
        print("\nTop unimplemented items:")
        for item in not_impl[:10]:
            print(f"  - {item.name} ({item.item_type})")
        if len(not_impl) > 10:
            print(f"  ... and {len(not_impl) - 10} more")

    print(f"\nFull report: {md_path}")

    return report


if __name__ == "__main__":
    main()
