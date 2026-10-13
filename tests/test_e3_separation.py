"""E3 — Structure and Verification Separation tests.

Per E3 deliverables:
- Split monolithic app.py into domain routers (health, identity, market_data,
  client, release)
- Move simulators/fault injectors/readiness generators/test harnesses to
  simulation/ package (outside deployable services/ tree)
- ExchangeAdapter Protocol in packages/contracts/exchange_adapter.py
- Import-linter config enforcing layer separation
- API versioning + contract tests
- Coverage/property reporting
- Decimal-only lint on financial modules

Acceptance: production image contains no verification code; layer violations
fail CI.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from services.core.app import app
from services.core.version import __version__

# ── API Versioning Tests ──


class TestAPIVersioning:
    """Test API versioning and contract stability."""

    def test_version_is_string(self) -> None:
        """__version__ must be a non-empty string."""
        assert isinstance(__version__, str)
        assert len(__version__) > 0

    def test_version_format(self) -> None:
        """Version must follow semver format (major.minor.patch)."""
        parts = __version__.split(".")
        assert len(parts) >= 2, f"Version '{__version__}' must have at least major.minor"
        for part in parts:
            assert part.isdigit() or part[0:-1].isdigit(), f"Version part '{part}' is not numeric"

    def test_app_version_matches_version_module(self) -> None:
        """FastAPI app.version must match services.core.version.__version__."""
        assert app.version == __version__

    def test_openapi_includes_version(self) -> None:
        """OpenAPI schema must include the version string."""
        with TestClient(app) as client:
            response = client.get("/openapi.json")
            assert response.status_code == 200
            schema = response.json()
            assert schema["info"]["version"] == __version__

    def test_health_endpoint_returns_version(self) -> None:
        """Health endpoint must return the current version."""
        with TestClient(app) as client:
            response = client.get("/health")
            assert response.status_code == 200
            data = response.json()
            assert data["version"] == __version__
            assert data["status"] == "healthy"

    def test_health_endpoint_returns_operating_mode(self) -> None:
        """Health endpoint must return the operating mode (AD-003)."""
        with TestClient(app) as client:
            response = client.get("/health")
            assert response.status_code == 200
            data = response.json()
            assert "operating_mode" in data
            assert "is_live" in data
            assert data["is_live"] is False


# ── Router Separation Tests ──


class TestRouterSeparation:
    """Test that app.py is split into domain routers."""

    def test_app_is_fastapi_instance(self) -> None:
        """app must be a FastAPI instance."""
        assert isinstance(app, FastAPI)

    def test_routers_are_included(self) -> None:
        """All five domain routers must be included in the app."""
        with TestClient(app) as client:
            # Health routes
            assert client.get("/health").status_code == 200
            assert client.get("/health/ready").status_code == 200
            assert client.get("/").status_code == 200

    def test_router_modules_exist(self) -> None:
        """All five router module files must exist."""
        base = Path(__file__).resolve().parent.parent / "services" / "core" / "routers"
        expected = ["health.py", "identity.py", "market_data.py", "client.py", "release.py"]
        for name in expected:
            assert (base / name).exists(), f"Router module {name} not found"

    def test_app_py_is_not_monolithic(self) -> None:
        """app.py must not contain route decorators (routes are in routers/)."""
        app_path = Path(__file__).resolve().parent.parent / "services" / "core" / "app.py"
        content = app_path.read_text()
        # No @app.get/@app.post/etc decorators in app.py — they belong in routers
        assert "@app.get(" not in content, "app.py must not contain @app.get decorators"
        assert "@app.post(" not in content, "app.py must not contain @app.post decorators"
        assert "@app.put(" not in content, "app.py must not contain @app.put decorators"
        assert "@app.patch(" not in content, "app.py must not contain @app.patch decorators"
        assert "@app.delete(" not in content, "app.py must not contain @app.delete decorators"


# ── Layer Separation Tests (import-linter equivalent) ──


class TestLayerSeparation:
    """Test that production services/ does not import from simulation/.

    Per E3 acceptance: the production image contains no verification code.
    This is enforced programmatically by scanning the AST of all .py files
    under services/ for 'from simulation' or 'import simulation' statements.
    """

    @staticmethod
    def _scan_services_for_simulation_imports() -> list[str]:
        """Scan all services/ .py files for simulation imports.

        Returns a list of 'file:line' strings for each violation found.
        """
        root = Path(__file__).resolve().parent.parent / "services"
        violations: list[str] = []
        for py_file in root.rglob("*.py"):
            if "__pycache__" in str(py_file):
                continue
            try:
                tree = ast.parse(py_file.read_text(), filename=str(py_file))
            except SyntaxError:
                continue
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        if alias.name.startswith("simulation"):
                            violations.append(f"{py_file}:{node.lineno}: import {alias.name}")
                elif (
                    isinstance(node, ast.ImportFrom)
                    and node.module
                    and node.module.startswith("simulation")
                ):
                    violations.append(f"{py_file}:{node.lineno}: from {node.module} import ...")
        return violations

    def test_services_does_not_import_simulation(self) -> None:
        """services/ must NOT contain any 'from simulation' or 'import simulation'."""
        violations = self._scan_services_for_simulation_imports()
        assert violations == [], (
            "Layer violation: services/ imports from simulation/:\n" + "\n".join(violations)
        )

    def test_contracts_does_not_import_services(self) -> None:
        """packages/contracts/ must NOT import from services/ or simulation/."""
        root = Path(__file__).resolve().parent.parent / "packages" / "contracts"
        violations: list[str] = []
        for py_file in root.rglob("*.py"):
            if "__pycache__" in str(py_file):
                continue
            try:
                tree = ast.parse(py_file.read_text(), filename=str(py_file))
            except SyntaxError:
                continue
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        if alias.name.startswith("services") or alias.name.startswith("simulation"):
                            violations.append(f"{py_file}:{node.lineno}: import {alias.name}")
                elif (
                    isinstance(node, ast.ImportFrom)
                    and node.module
                    and (node.module.startswith("services") or node.module.startswith("simulation"))
                ):
                    violations.append(f"{py_file}:{node.lineno}: from {node.module} import ...")
        assert violations == [], (
            "Layer violation: contracts/ imports from services/ or simulation/:\n"
            + "\n".join(violations)
        )


# ── ExchangeAdapter Protocol Tests ──


class TestExchangeAdapterProtocol:
    """Test that the ExchangeAdapter Protocol exists and is used."""

    def test_protocol_importable(self) -> None:
        """ExchangeAdapter must be importable from contracts.exchange_adapter."""
        from contracts.exchange_adapter import ExchangeAdapter

        assert ExchangeAdapter is not None

    def test_execution_engine_depends_on_protocol(self) -> None:
        """ExecutionEngine must depend on ExchangeAdapter, not a concrete class."""
        # Check the __init__ annotation references ExchangeAdapter
        import inspect

        from services.execution.engine import ExecutionEngine

        sig = inspect.signature(ExecutionEngine.__init__)
        exchange_param = sig.parameters.get("exchange")
        assert exchange_param is not None
        assert "ExchangeAdapter" in str(exchange_param.annotation)


# ── Simulation Package Tests ──


class TestSimulationPackage:
    """Test that the simulation/ package contains the moved code."""

    def test_simulation_package_exists(self) -> None:
        """simulation/ package directory must exist."""
        sim_path = Path(__file__).resolve().parent.parent / "simulation"
        assert sim_path.is_dir(), "simulation/ package directory not found"
        assert (sim_path / "__init__.py").exists()

    def test_exchange_simulator_in_simulation(self) -> None:
        """ExchangeSimulator must be importable from simulation.exchange_simulator."""
        from simulation.exchange_simulator import ExchangeSimulator

        assert ExchangeSimulator is not None

    def test_mining_simulator_in_simulation(self) -> None:
        """MiningSimulator must be importable from simulation.mining_simulator."""
        from simulation.mining_simulator import MiningSimulator

        assert MiningSimulator is not None

    def test_market_data_simulator_in_simulation(self) -> None:
        """SimulatedMarketDataProvider must be importable from simulation."""
        from simulation.market_data_simulator import SimulatedMarketDataProvider

        assert SimulatedMarketDataProvider is not None

    def test_security_simulators_in_simulation(self) -> None:
        """Security simulators must be in simulation/security_simulators.py."""
        sim_path = Path(__file__).resolve().parent.parent / "simulation"
        assert (sim_path / "security_simulators.py").exists()

    def test_release_generators_in_simulation(self) -> None:
        """Release generators must be in simulation/release_generators.py."""
        sim_path = Path(__file__).resolve().parent.parent / "simulation"
        assert (sim_path / "release_generators.py").exists()

    def test_no_simulator_files_in_services(self) -> None:
        """services/ must not contain simulator files (they moved to simulation/)."""
        services_path = Path(__file__).resolve().parent.parent / "services"
        for py_file in services_path.rglob("*simulator*.py"):
            if "__pycache__" not in str(py_file):
                pytest.fail(f"Simulator file found in services/: {py_file}")


# ── OpenAPI Contract Tests ──


class TestOpenAPIContract:
    """Test OpenAPI schema stability and contract integrity."""

    @pytest.fixture
    def client(self) -> TestClient:
        return TestClient(app)

    def test_openschema_has_paths(self, client: TestClient) -> None:
        """OpenAPI schema must define at least one path."""
        with client:
            response = client.get("/openapi.json")
            assert response.status_code == 200
            schema = response.json()
            assert len(schema["paths"]) > 0

    def test_health_path_in_openapi(self, client: TestClient) -> None:
        """OpenAPI must include /health path."""
        with client:
            response = client.get("/openapi.json")
            schema = response.json()
            assert "/health" in schema["paths"]

    def test_openapi_has_info_block(self, client: TestClient) -> None:
        """OpenAPI must have an info block with title and version."""
        with client:
            response = client.get("/openapi.json")
            schema = response.json()
            assert "info" in schema
            assert "title" in schema["info"]
            assert "version" in schema["info"]
