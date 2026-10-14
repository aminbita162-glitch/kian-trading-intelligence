"""E3 — Decimal-only lint for financial modules.

Per E3 deliverable: financial modules must use Decimal (not float) for
all monetary calculations. This test scans the AST of financial service
modules and asserts that no float literals or float() calls appear in
financial computation code.

Per AD-007: exact decimal representation for financial values.
Per Section 05.2: quantity is a string for exact decimal representation.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

# Financial modules that must use Decimal, not float
FINANCIAL_MODULES = [
    "services/ledger/__init__.py",
    "services/ledger/persistence.py",
    "services/ledger/persistent_ledger.py",
    "services/risk_kernel/kernel.py",
    "services/risk_kernel/persistent_kernel.py",
    "packages/contracts/ledger.py",
    "packages/contracts/risk.py",
]

# Allowed float patterns (in docstrings, comments, or type annotations)
# We only flag float() calls and float literals in actual code, not strings


def _find_float_usage(filepath: Path) -> list[str]:
    """Find float() calls and float literals in a Python file.

    Returns a list of violation descriptions.
    """
    content = filepath.read_text()
    try:
        tree = ast.parse(content, filename=str(filepath))
    except SyntaxError:
        return []

    violations: list[str] = []

    for node in ast.walk(tree):
        # Flag float() calls
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name) and func.id == "float":
                violations.append(f"{filepath}:{node.lineno}: float() call — use Decimal() instead")
        # Flag float literals (e.g., 0.1, 50000.0) in financial code
        # But NOT in docstrings, comments, or string literals
        if isinstance(node, ast.Constant) and isinstance(node.value, float):
            # Skip if it's in a default value of a non-financial parameter
            # We flag all float literals in financial modules
            violations.append(
                f"{filepath}:{node.lineno}: float literal {node.value} — use Decimal or string"
            )

    return violations


class TestDecimalOnlyLint:
    """Test that financial modules use Decimal, not float."""

    @pytest.mark.parametrize("module_path", FINANCIAL_MODULES)
    def test_no_float_calls_in_financial_modules(self, module_path: str) -> None:
        """Financial modules must not use float() calls."""
        root = Path(__file__).resolve().parent.parent
        filepath = root / module_path
        if not filepath.exists():
            pytest.skip(f"Module {module_path} not found")
        violations = _find_float_usage(filepath)
        float_calls = [v for v in violations if "float() call" in v]
        assert float_calls == [], (
            f"float() calls found in financial module {module_path}:\n" + "\n".join(float_calls)
        )

    @pytest.mark.parametrize("module_path", FINANCIAL_MODULES)
    def test_no_float_literals_in_financial_modules(self, module_path: str) -> None:
        """Financial modules must not use float literals — use Decimal or string."""
        root = Path(__file__).resolve().parent.parent
        filepath = root / module_path
        if not filepath.exists():
            pytest.skip(f"Module {module_path} not found")
        violations = _find_float_usage(filepath)
        float_literals = [v for v in violations if "float literal" in v]
        assert float_literals == [], (
            f"Float literals found in financial module {module_path}:\n" + "\n".join(float_literals)
        )
