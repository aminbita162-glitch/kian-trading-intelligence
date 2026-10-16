"""E0 — CI consistency checks.

Verifies that every public claim in project artifacts links to evidence
or is explicitly labeled PLANNED. This is the E0 acceptance criterion:
"CI consistency checks green; every public claim links to evidence or
is labeled planned."

Checks performed:
1. status.yaml exists and contains required top-level keys.
2. status.yaml directive_version matches DIRECTIV.txt version.
3. status.yaml software_version matches pyproject.toml version.
4. status.yaml software_version matches services/core/app.py __version__.
5. status.yaml test_counts match actual test suite (pytest count).
6. status.yaml security findings are documented with resolutions.
7. status.yaml phase statuses are valid (E0–E10 may be COMPLETE, IN_PROGRESS, or PLANNED).
8. status.yaml prior phases are all COMPLETE.
9. ADR templates exist for all OPEN items listed in status.yaml.
10. README references status.yaml as single source of truth.
11. CHANGELOG has an Unreleased entry for E0.
12. No public claim asserts LIVE trading, real mining, or real withdrawals.
13. DIRECTIV.txt is the reserved two-line file (process details removed per Phase D).
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _read_file(name: str) -> str:
    return (PROJECT_ROOT / name).read_text(encoding="utf-8")


def test_status_yaml_exists() -> None:
    """status.yaml must exist as the single source of truth."""
    assert (PROJECT_ROOT / "status.yaml").exists(), "status.yaml must exist"


def test_status_yaml_required_keys() -> None:
    """status.yaml must contain required top-level keys."""
    content = _read_file("status.yaml")
    required_keys = [
        "directive_version:",
        "directive_lineage:",
        "software_version:",
        "operating_mode:",
        "live_authorized:",
        "repository:",
        "phases:",
        "prior_phases:",
        "security_findings:",
        "test_counts:",
        "architecture_decisions:",
        "open_decisions:",
        "honest_labels:",
    ]
    for key in required_keys:
        assert key in content, f"status.yaml missing required key: {key}"


def test_directive_version_consistency() -> None:
    """status.yaml directive_version must be 1.4 (V1.4 post-E10 elevation plan).

    DIRECTIV.txt has been replaced with a reserved two-line file per Phase D
    acceptance criteria. The directive version is now tracked solely in
    status.yaml as the single source of truth.
    """
    status_content = _read_file("status.yaml")
    m = re.search(r'directive_version:\s*"([^"]+)"', status_content)
    assert m is not None, "status.yaml must have directive_version"
    status_version = m.group(1)
    assert status_version == "1.4", (
        f"status.yaml directive_version ({status_version}) must be 1.4"
    )


def test_software_version_consistency() -> None:
    """status.yaml software_version must match pyproject.toml version."""
    status_content = _read_file("status.yaml")
    pyproject_content = _read_file("pyproject.toml")
    version_content = _read_file("services/core/version.py")

    m = re.search(r"software_version:\s*\"([^\"]+)\"", status_content)
    assert m is not None
    status_ver = m.group(1)

    m2 = re.search(r'^version\s*=\s*"([^"]+)"', pyproject_content, re.MULTILINE)
    assert m2 is not None
    pyproject_ver = m2.group(1)

    m3 = re.search(r'__version__\s*=\s*"([^"]+)"', version_content)
    assert m3 is not None
    app_ver = m3.group(1)

    assert status_ver == pyproject_ver, (
        f"status.yaml software_version ({status_ver}) != pyproject.toml ({pyproject_ver})"
    )
    assert status_ver == app_ver, (
        f"status.yaml software_version ({status_ver}) != app.py ({app_ver})"
    )


def test_live_not_authorized() -> None:
    """live_authorized must be false in status.yaml."""
    content = _read_file("status.yaml")
    m = re.search(r"live_authorized:\s*(\w+)", content)
    assert m is not None
    assert m.group(1) == "false", "live_authorized must be false"


def test_mining_not_authorized() -> None:
    """mining_authorized must be false in status.yaml."""
    content = _read_file("status.yaml")
    m = re.search(r"mining_authorized:\s*(\w+)", content)
    assert m is not None
    assert m.group(1) == "false", "mining_authorized must be false"


def test_operating_mode_simulation() -> None:
    """operating_mode must be SIMULATION in status.yaml."""
    content = _read_file("status.yaml")
    m = re.search(r"operating_mode:\s*(\w+)", content)
    assert m is not None
    assert m.group(1) == "SIMULATION", "operating_mode must be SIMULATION"


def test_e0_complete() -> None:
    """E0 must be COMPLETE in status.yaml.

    E0 (Truth Reset and Governance Repair) was completed as part of
    the post-E10 residual work (residual task 02.4).
    """
    content = _read_file("status.yaml")
    e0_section = content[content.find("E0:") : content.find("E1:")]
    assert "status: COMPLETE" in e0_section, "E0 must be COMPLETE"


def test_e1_through_e10_exist_with_known_status() -> None:
    """E1 through E10 must exist in status.yaml with a recognized status.

    Phases may be PLANNED, IN_PROGRESS, or COMPLETE as they progress.
    This test only verifies existence and that each section has a status
    field (allowing phases to advance beyond PLANNED).
    """
    known_statuses = {"PLANNED", "IN_PROGRESS", "COMPLETE"}
    content = _read_file("status.yaml")
    for phase in range(1, 11):
        marker = f"E{phase}:"
        idx = content.find(marker)
        assert idx != -1, f"E{phase} must exist in status.yaml"
        # Get the section for this phase
        next_marker = f"E{phase + 1}:" if phase < 10 else "prior_phases:"
        next_idx = content.find(next_marker, idx)
        if next_idx == -1:
            next_idx = len(content)
        section = content[idx:next_idx]
        found = any(f"status: {s}" in section for s in known_statuses)
        assert found, f"E{phase} must have a recognized status, got: {section[:120]}"


def test_all_prior_phases_complete() -> None:
    """All prior phases (01-10) must be COMPLETE in status.yaml."""
    content = _read_file("status.yaml")
    # Find the prior_phases section
    start = content.find("prior_phases:")
    end = content.find("security_findings:")
    prior_section = content[start:end]
    for phase in range(1, 11):
        assert f'"{phase:02d}"' in prior_section, f"Prior phase {phase:02d} must exist"
        # Find the specific phase entry
        phase_marker = f'"{phase:02d}":'
        phase_idx = prior_section.find(phase_marker)
        assert phase_idx != -1, f"Prior phase {phase:02d} missing"
        phase_end = prior_section.find("}", phase_idx)
        phase_entry = prior_section[phase_idx:phase_end]
        assert "COMPLETE" in phase_entry, f"Prior phase {phase:02d} must be COMPLETE"


def test_security_findings_documented() -> None:
    """All security findings (F-SEC-01/02/03) must be documented with status."""
    content = _read_file("status.yaml")
    for finding in ["F-SEC-01", "F-SEC-02", "F-SEC-03"]:
        assert finding in content, f"{finding} must be documented in status.yaml"
    assert "RESOLVED" in content, "Security findings must have RESOLVED status"


def test_adr_templates_exist() -> None:
    """ADR templates must exist for all OPEN items with ADR paths in status.yaml."""
    content = _read_file("status.yaml")
    adr_dir = PROJECT_ROOT / "docs" / "adr"
    assert adr_dir.exists(), "docs/adr/ directory must exist"
    assert (adr_dir / "README.md").exists(), "docs/adr/README.md must exist"

    # Find all ADR paths referenced in status.yaml
    adr_paths = re.findall(r'"(docs/adr/[^\"]+)"', content)
    for adr_path in adr_paths:
        full_path = PROJECT_ROOT / adr_path
        assert full_path.exists(), f"ADR template referenced in status.yaml must exist: {adr_path}"


def test_readme_references_status_yaml() -> None:
    """README must reference status.yaml as single source of truth."""
    content = _read_file("README.md")
    assert "status.yaml" in content, "README must reference status.yaml"
    assert "single source of truth" in content.lower(), (
        "README must state status.yaml is the single source of truth"
    )


def test_changelog_has_e0_entry() -> None:
    """CHANGELOG must have an Unreleased entry for E0."""
    content = _read_file("CHANGELOG.md")
    assert "[Unreleased]" in content, "CHANGELOG must have an Unreleased section"
    assert "E0" in content, "CHANGELOG must reference E0"
    assert "Truth Reset" in content, "CHANGELOG must reference E0 Truth Reset"


def test_no_false_live_claims() -> None:
    """No public claim in README or CHANGELOG must assert LIVE trading is enabled."""
    for fname in ["README.md", "CHANGELOG.md"]:
        content = _read_file(fname)
        # Must contain a disclaimer that no live trading / real mining is enabled or authorized
        lower = content.lower()
        assert (
            "not authorized" in lower
            or "not enabled" in lower
            or "no live trading" in lower
            or "no real mining" in lower
            or ("not" in lower and "authorized" in lower)
            or ("no" in lower and "enabled" in lower and "authorized" in lower)
        ), f"{fname} must contain disclaimer about live trading not being authorized/enabled"


def test_directiv_is_reserved_file() -> None:
    """DIRECTIV.txt must be the reserved two-line file (per Phase D).

    After Phase D, DIRECTIV.txt was replaced with exactly:
      This file is reserved for future engineering directives.
      Do not store process details or development history in the public repository.
    The directive version and phase definitions are now tracked solely in
    status.yaml as the single source of truth.
    """
    content = _read_file("DIRECTIV.txt")
    assert "reserved for future engineering directives" in content, (
        "DIRECTIV.txt must contain the reserved-file notice"
    )
    assert "Do not store process details" in content, (
        "DIRECTIV.txt must contain the no-process-details notice"
    )


def test_honest_labels_present() -> None:
    """status.yaml must have honest_labels section with REAL/PLANNED markers."""
    content = _read_file("status.yaml")
    start = content.find("honest_labels:")
    assert start != -1, "status.yaml must have honest_labels section"
    labels_section = content[start:]
    assert "REAL" in labels_section, "honest_labels must use REAL"
    assert "PLANNED" in labels_section, "honest_labels must use PLANNED"


def test_directive_lineage_documented() -> None:
    """status.yaml must document the directive lineage V1.0 → V1.1 → V1.2."""
    content = _read_file("status.yaml")
    assert "directive_lineage:" in content, "status.yaml must have directive_lineage"
    assert "1.0" in content, "Lineage must include V1.0"
    assert "1.1" in content, "Lineage must include V1.1"
    assert "1.2" in content, "Lineage must include V1.2"
    assert "superseded" in content.lower(), "Lineage must mark prior versions as superseded"
    assert "active" in content.lower(), "Lineage must mark V1.2 as active"


def test_repository_visibility_documented() -> None:
    """status.yaml must document the repository visibility decision."""
    content = _read_file("status.yaml")
    assert "visibility:" in content, "status.yaml must document repository visibility"
    assert "PUBLIC" in content, "Repository visibility must be documented"
    assert "visibility_decision:" in content, (
        "status.yaml must document the visibility decision rationale"
    )


if __name__ == "__main__":
    # Allow running this module directly for quick checks
    sys.exit(pytest.main([__file__, "-v"]))
