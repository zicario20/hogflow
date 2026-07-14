import ast
import importlib
import io
import sys
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

SOURCE_ROOT = Path(__file__).resolve().parents[1] / "src" / "hogflow"
INTERNAL_PACKAGES = {
    "config",
    "core",
    "counting",
    "detection",
    "domain",
    "pipeline",
    "sessions",
    "storage",
    "tracking",
    "video",
}
FORBIDDEN_IMPORTS = {
    "core": {
        "config",
        "counting",
        "video",
        "detection",
        "tracking",
        "pipeline",
        "sessions",
        "storage",
        "domain",
    },
    "config": {
        "counting",
        "video",
        "detection",
        "tracking",
        "pipeline",
        "sessions",
        "storage",
        "domain",
    },
    "counting": {
        "video",
        "detection",
        "tracking",
        "pipeline",
        "sessions",
        "storage",
    },
    "domain": {
        "config",
        "counting",
        "video",
        "detection",
        "tracking",
        "pipeline",
        "sessions",
        "storage",
    },
}


def _module_parts(path: Path) -> tuple[str, ...]:
    relative_parts = path.relative_to(SOURCE_ROOT).with_suffix("").parts
    module_parts = ("hogflow", *relative_parts)
    if module_parts[-1] == "__init__":
        return module_parts[:-1]
    return module_parts


def _target_package(module_parts: tuple[str, ...]) -> str | None:
    if (
        len(module_parts) >= 2
        and module_parts[0] == "hogflow"
        and module_parts[1] in INTERNAL_PACKAGES
    ):
        return module_parts[1]
    return None


def _resolved_from_module(
    node: ast.ImportFrom,
    source_module: tuple[str, ...],
    *,
    source_is_package: bool,
) -> tuple[str, ...]:
    if node.level == 0:
        return tuple(node.module.split(".")) if node.module else ()

    source_package = source_module if source_is_package else source_module[:-1]
    parent_steps = node.level - 1
    if parent_steps > len(source_package):
        return ()
    base = source_package[: len(source_package) - parent_steps]
    if node.module:
        return (*base, *node.module.split("."))
    return base


def _internal_imports(
    tree: ast.AST,
    source_module: tuple[str, ...],
    *,
    source_is_package: bool,
) -> list[tuple[int, str]]:
    imports: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                target = _target_package(tuple(alias.name.split(".")))
                if target is not None:
                    imports.append((node.lineno, target))
        elif isinstance(node, ast.ImportFrom):
            resolved_module = _resolved_from_module(
                node,
                source_module,
                source_is_package=source_is_package,
            )
            target = _target_package(resolved_module)
            if target is not None:
                imports.append((node.lineno, target))
            elif resolved_module == ("hogflow",):
                for alias in node.names:
                    if alias.name in INTERNAL_PACKAGES:
                        imports.append((node.lineno, alias.name))
    return imports


def test_internal_package_dependencies_follow_declared_boundaries() -> None:
    violations: list[str] = []
    for source_file in sorted(SOURCE_ROOT.rglob("*.py")):
        if "__pycache__" in source_file.parts or source_file.name.endswith("_generated.py"):
            continue

        source_module = _module_parts(source_file)
        source_package = source_module[1] if len(source_module) >= 2 else None
        forbidden_targets = FORBIDDEN_IMPORTS.get(source_package, set())
        tree = ast.parse(source_file.read_text(encoding="utf-8"), filename=str(source_file))
        for line_number, target_package in _internal_imports(
            tree,
            source_module,
            source_is_package=source_file.name == "__init__.py",
        ):
            if target_package in forbidden_targets:
                relative_file = source_file.relative_to(SOURCE_ROOT.parent)
                violations.append(
                    f"{relative_file}:{line_number}: package {source_package!r} "
                    f"must not import {target_package!r}"
                )

    assert not violations, "Architecture dependency violations:\n" + "\n".join(violations)


def test_internal_import_parser_handles_supported_import_forms() -> None:
    tree = ast.parse(
        "\n".join(
            (
                "import hogflow.video",
                "from hogflow.video import generic_counter",
                "from hogflow import video",
                "from ..tracking import adapter",
                "import logging",
            )
        )
    )

    imports = _internal_imports(
        tree,
        ("hogflow", "core", "sample"),
        source_is_package=False,
    )

    assert {target for _line, target in imports} == {"tracking", "video"}


def test_foundation_package_imports_do_not_write_to_stdout_or_stderr() -> None:
    package_names = (
        "hogflow.core",
        "hogflow.config",
        "hogflow.counting",
        "hogflow.detection",
        "hogflow.tracking",
        "hogflow.pipeline",
        "hogflow.sessions",
        "hogflow.storage",
        "hogflow.domain",
    )

    for package_name in package_names:
        stdout = io.StringIO()
        stderr = io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            existing_module = sys.modules.get(package_name)
            if existing_module is None:
                importlib.import_module(package_name)
            else:
                importlib.reload(existing_module)

        assert stdout.getvalue() == "", f"{package_name} wrote to stdout during import"
        assert stderr.getvalue() == "", f"{package_name} wrote to stderr during import"
