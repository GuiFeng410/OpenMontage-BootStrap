"""Focused contracts for the staged repository refactor."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import backlot
import openmontage
from backlot.server import create_app
from lib.pipeline_loader import load_pipeline
from lib.resources import get_resources
from openmontage import product_version
from openmontage.mcp import CONTRACT_VERSION
from openmontage.mcp.bootstrap.server import mcp
from openmontage.mcp.bootstrap.tools import list_bootstrap_tools
from openmontage.mcp.common.version import version_fields


ROOT = Path(__file__).resolve().parents[2]
EXPECTED_COMMERCIAL_STAGES = [
    "brief_locked",
    "assets_gate",
    "sample_review",
    "segment_build",
    "draft_review",
    "final_compose",
    "delivery_signoff",
]
REQUIRED_PRODUCE_TOOLS = {
    "produce_init_project",
    "produce_approve_checkpoint",
    "produce_runner_tick",
    "produce_read_state",
    "produce_compose_start",
}
EXPECTED_BACKLOT_ROUTES = {
    "/api/health",
    "/api/runtime/stop",
    "/api/library/release-runner",
    "/api/keys/refresh",
    "/api/project/{project_id}/start-production",
    "/api/library/create-project",
    "/api/library/continue-project",
    "/api/projects",
    "/intents",
    "/api/project/{project_id}/interaction-intents",
    "/api/project/{project_id}/state",
    "/api/project/{project_id}/events",
    "/api/library/events",
    "/thumb/{project_id}/{file_path:path}",
    "/media/{project_id}/{file_path:path}",
    "/p/{project_id}",
    "/p/{project_path:path}",
    "/",
}


def test_product_version_comes_from_release_manifest() -> None:
    manifest = json.loads(
        (ROOT / "distribution/manifests/release-manifest.json").read_text(
            encoding="utf-8"
        )
    )

    assert openmontage.__version__ == manifest["version"]
    assert backlot.__version__ == manifest["version"]
    assert version_fields()["openmontage_version"] == manifest["version"]


def test_product_version_does_not_replace_contract_version() -> None:
    assert CONTRACT_VERSION == "0.1.0"
    assert version_fields()["contract_version"] == CONTRACT_VERSION


def test_product_version_falls_back_to_installed_distribution_metadata(
    tmp_path: Path,
    monkeypatch,
) -> None:
    requested: list[str] = []

    def fake_distribution_version(name: str) -> str:
        requested.append(name)
        return "0.6.0"

    monkeypatch.setattr(
        product_version,
        "RELEASE_MANIFEST",
        tmp_path / "missing-release-manifest.json",
    )
    monkeypatch.setattr(
        product_version,
        "distribution_version",
        fake_distribution_version,
        raising=False,
    )

    assert product_version.get_product_version() == "0.6.0"
    assert requested == ["openmontage"]


def test_setup_uses_product_version_symbol() -> None:
    source = (ROOT / "setup.py").read_text(encoding="utf-8")

    assert "from openmontage.product_version import PRODUCT_VERSION" in source
    assert "version=PRODUCT_VERSION" in source


def test_bootstrap_commercial_stage_order_and_schemas() -> None:
    manifest = load_pipeline("bootstrap-commercial")

    assert [stage["name"] for stage in manifest["stages"]] == EXPECTED_COMMERCIAL_STAGES
    assert manifest["required_skills"] == [
        "openmontage-bootstrap-03-usercheck",
        "openmontage-bootstrap-04-produce",
    ]
    for stage in manifest["stages"]:
        for artifact in stage.get("produces", []):
            assert (get_resources().artifact_schemas() / f"{artifact}.schema.json").is_file()


def test_bootstrap_critical_tool_names_remain_available() -> None:
    surface = list_bootstrap_tools()
    registered = {tool.name for tool in asyncio.run(mcp.list_tools())}

    assert REQUIRED_PRODUCE_TOOLS <= set(surface["produce_minimal"])
    assert REQUIRED_PRODUCE_TOOLS <= registered


def test_backlot_http_route_paths_remain_stable() -> None:
    paths = {route.path for route in create_app().routes}

    assert EXPECTED_BACKLOT_ROUTES <= paths


def test_mcp_templates_put_src_on_pythonpath() -> None:
    template_dir = ROOT / "README" / "配置" / "templates"
    paths = sorted(template_dir.glob("*.mcp.json"))
    assert paths, "expected MCP JSON templates"
    for path in paths:
        payload = json.loads(path.read_text(encoding="utf-8"))
        for name, server in payload["mcp"]["servers"].items():
            pythonpath = server["env"]["PYTHONPATH"]
            assert pythonpath.endswith("/src"), f"{name} PYTHONPATH={pythonpath!r}"
            assert "<OPENMONTAGE_REPO_ROOT>" in pythonpath
            assert server["cwd"] == "<OPENMONTAGE_REPO_ROOT>"
            assert server["args"][0] == "-m"
            assert server["args"][1].startswith("openmontage.mcp.")
