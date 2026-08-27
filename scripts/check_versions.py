#!/usr/bin/env python3
"""
Version Consistency Checker for energy-forecast-dk.

Checks that all version references across the project are consistent
before allowing a commit.
"""

import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# ── Version locations ──────────────────────────────────────────────
# Each entry: (file_path, regex_pattern, version_group_index, description)
VERSION_CHECKS = [
    # pyproject.toml: version = "x.y.z"
    (
        PROJECT_ROOT / "pyproject.toml",
        r'^version\s*=\s*"(\d+\.\d+\.\d+)"',
        1,
        "pyproject.toml (project version)",
    ),
    # serve_model.py: version="x.y.z"
    (
        PROJECT_ROOT / "src" / "energy_forecast" / "serving" / "serve_model.py",
        r'version\s*=\s*"(\d+\.\d+\.\d+)"',
        1,
        "serve_model.py (FastAPI version)",
    ),
    # Dockerfile: python:x.x-slim
    (
        PROJECT_ROOT / "Dockerfile",
        r"FROM\s+python:(\d+\.\d+)-slim",
        1,
        "Dockerfile (Python base image)",
    ),
]

# ── Canonical version file ─────────────────────────────────────────
# pyproject.toml is the single source of truth for the project version
CANONICAL_VERSION_FILE = PROJECT_ROOT / "pyproject.toml"
CANONICAL_VERSION_PATTERN = r'^version\s*=\s*"(\d+\.\d+\.\d+)"'


def extract_version(file_path: Path, pattern: str, group: int = 1) -> str | None:
    """Extract version string from a file using a regex pattern."""
    if not file_path.exists():
        return None
    content = file_path.read_text(encoding="utf-8")
    match = re.search(pattern, content, re.MULTILINE)
    if match:
        return match.group(group)
    return None


def extract_python_version(file_path: Path) -> str | None:
    """Extract Python version from Dockerfile (e.g. 3.11)."""
    if not file_path.exists():
        return None
    content = file_path.read_text(encoding="utf-8")
    match = re.search(r"FROM\s+python:(\d+\.\d+)-slim", content, re.MULTILINE)
    if match:
        return match.group(1)
    return None


def get_required_python_version() -> str | None:
    """Get the required Python version from pyproject.toml (e.g. 3.10)."""
    pyproject = PROJECT_ROOT / "pyproject.toml"
    if not pyproject.exists():
        return None
    content = pyproject.read_text(encoding="utf-8")
    match = re.search(r'requires-python\s*=\s*">=(\d+\.\d+)"', content, re.MULTILINE)
    if match:
        return match.group(1)
    return None


def check_versions() -> list[str]:
    """
    Run all version checks and return a list of error messages.
    Empty list means all checks passed.
    """
    errors: list[str] = []

    # 1. Check that canonical version exists
    canonical_version = extract_version(
        CANONICAL_VERSION_FILE, CANONICAL_VERSION_PATTERN
    )
    if canonical_version is None:
        errors.append(
            "FAIL: Cannot find project version in pyproject.toml"
        )
        return errors

    print(f"  Project version (pyproject.toml): {canonical_version}")

    # 2. Check FastAPI version matches project version
    api_version = extract_version(
        PROJECT_ROOT / "src" / "energy_forecast" / "serving" / "serve_model.py",
        r'version\s*=\s*"(\d+\.\d+\.\d+)"',
    )
    if api_version is None:
        errors.append(
            "WARN: Cannot find FastAPI version in serve_model.py"
        )
    elif api_version != canonical_version:
        errors.append(
            f"FAIL: FastAPI version ({api_version}) != project version ({canonical_version})\n"
            f"       File: src/energy_forecast/serving/serve_model.py:18\n"
            f"       Fix:  Update version=\"{canonical_version}\" to match pyproject.toml"
        )
    else:
        print(f"  FastAPI version (serve_model.py): {api_version} [OK]")

    # 3. Check Dockerfile Python version >= required Python version
    dockerfile_python = extract_python_version(PROJECT_ROOT / "Dockerfile")
    required_python = get_required_python_version()

    if dockerfile_python is None:
        errors.append("WARN: Cannot find Python version in Dockerfile")
    elif required_python is None:
        errors.append("WARN: Cannot find requires-python in pyproject.toml")
    else:
        # Compare versions (e.g., 3.11 >= 3.10)
        docker_parts = [int(x) for x in dockerfile_python.split(".")]
        required_parts = [int(x) for x in required_python.split(".")]
        if tuple(docker_parts) >= tuple(required_parts):
            print(
                f"  Dockerfile Python ({dockerfile_python}) >= required ({required_python}) [OK]"
            )
        else:
            errors.append(
                f"FAIL: Dockerfile Python ({dockerfile_python}) < required ({required_python})\n"
                f"       File: Dockerfile\n"
                f"       Fix:  Update base image to python:{required_python}-slim or higher"
            )

    # 4. Check pyproject.toml structure
    pyproject = PROJECT_ROOT / "pyproject.toml"
    if pyproject.exists():
        content = pyproject.read_text(encoding="utf-8")
        # Check for required fields
        required_fields = ["name", "version", "description", "requires-python"]
        for field in required_fields:
            if field not in content:
                errors.append(
                    f"WARN: Missing '{field}' in pyproject.toml [project] section"
                )
        print(f"  pyproject.toml structure: [OK]")

    # 5. Check __init__.py exists
    init_file = PROJECT_ROOT / "src" / "energy_forecast" / "__init__.py"
    if not init_file.exists():
        errors.append(
            "WARN: Missing src/energy_forecast/__init__.py"
        )
    else:
        print(f"  Package __init__.py: [OK]")

    # 6. Check for hardcoded version strings in source
    src_dir = PROJECT_ROOT / "src" / "energy_forecast"
    if src_dir.exists():
        for py_file in src_dir.rglob("*.py"):
            content = py_file.read_text(encoding="utf-8")
            # Look for common version patterns that might be stale
            matches = re.findall(
                r'(?:__version__|VERSION|version)\s*=\s*["\'](\d+\.\d+\.\d+)["\']',
                content,
            )
            for v in matches:
                if v != canonical_version:
                    rel_path = py_file.relative_to(PROJECT_ROOT)
                    errors.append(
                        f"FAIL: Stale version '{v}' in {rel_path}\n"
                        f"       Expected: {canonical_version}"
                    )

    return errors


def main() -> int:
    """Main entry point. Returns 0 on success, 1 on failure."""
    print("=" * 60)
    print("  Version Consistency Check")
    print("=" * 60)
    print()

    errors = check_versions()

    print()
    if errors:
        print("=" * 60)
        print("  ERRORS FOUND:")
        print("=" * 60)
        for err in errors:
            print(f"  {err}")
            print()
        print("=" * 60)
        print(f"  Total errors: {len(errors)}")
        print("=" * 60)
        return 1
    else:
        print("=" * 60)
        print("  All version checks PASSED!")
        print("=" * 60)
        return 0


if __name__ == "__main__":
    sys.exit(main())
