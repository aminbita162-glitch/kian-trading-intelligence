"""Secret scan test — verifies no secrets are committed.

Per AD-019, Section 10.2: never store plaintext financial credentials
in source code, Git, or ordinary logs.
"""

import os
import re

# Patterns that indicate potential secrets
# Note: matches assignments or key-value pairs, NOT bare string literals in
# class/enum definitions (e.g., EXCHANGE_API_KEY = "exchange_api_key" is
# an enum value, not a credential).
SECRET_PATTERNS = [
    re.compile(
        r"(?i)(api[_-]?key|api[_-]?secret|access[_-]?token|secret[_-]?key)\s*[:=]\s*['\"][^'\"]{20,}['\"]"
    ),
    re.compile(r"-----BEGIN\s+(RSA\s+)?PRIVATE\s+KEY-----"),
    re.compile(r"ghp_[A-Za-z0-9]{36,}"),
    re.compile(r"gho_[A-Za-z0-9]{36,}"),
    re.compile(r"sk-[A-Za-z0-9]{20,}"),
    re.compile(r"AKIA[0-9A-Z]{16}"),
]

# File extensions and names to scan
SCANABLE_EXTENSIONS = {
    ".py",
    ".ts",
    ".tsx",
    ".js",
    ".jsx",
    ".json",
    ".yaml",
    ".yml",
    ".toml",
    ".env",
    ".cfg",
    ".ini",
    ".md",
}
SKIP_DIRS = {
    ".git",
    "node_modules",
    "__pycache__",
    ".venv",
    "venv",
    "dist",
    "build",
    ".ruff_cache",
    ".mypy_cache",
    ".pytest_cache",
}
SKIP_FILES = {".gitignore", ".env.example"}


def _scan_file(filepath: str) -> list[str]:
    """Scan a single file for secret patterns. Returns list of findings."""
    findings: list[str] = []
    try:
        with open(filepath, encoding="utf-8") as f:
            content = f.read()
        for i, line in enumerate(content.splitlines(), start=1):
            for pattern in SECRET_PATTERNS:
                if pattern.search(line):
                    findings.append(f"{filepath}:{i}: {line.strip()[:80]}")
    except (UnicodeDecodeError, PermissionError):
        pass
    return findings


def _collect_scanable_files(root: str) -> list[str]:
    """Collect all files to scan, skipping binary/cache dirs."""
    files: list[str] = []
    for dirpath, dirnames, filenames in os.walk(root):
        # Skip cache dirs in-place
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for filename in filenames:
            if filename in SKIP_FILES:
                continue
            ext = os.path.splitext(filename)[1]
            if ext in SCANABLE_EXTENSIONS or filename.endswith(".env"):
                files.append(os.path.join(dirpath, filename))
    return files


class TestSecretScan:
    def test_no_secrets_in_repository(self) -> None:
        """Verify no potential secrets are present in source files."""
        repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        files = _collect_scanable_files(repo_root)
        all_findings: list[str] = []
        for filepath in files:
            findings = _scan_file(filepath)
            all_findings.extend(findings)
        if all_findings:
            msg = "Potential secrets found:\n" + "\n".join(all_findings)
            raise AssertionError(msg)

    def test_env_files_not_committed(self) -> None:
        """Verify .env files are gitignored and not present."""
        repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        env_files = []
        for dirpath, dirnames, filenames in os.walk(repo_root):
            dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
            for filename in filenames:
                if filename == ".env" or (
                    filename.startswith(".env.") and not filename.endswith(".example")
                ):
                    env_files.append(os.path.join(dirpath, filename))
        assert env_files == [], f".env files found (should be gitignored): {env_files}"
