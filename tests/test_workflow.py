import asyncio
import json
from pathlib import Path
import sys

import pytest
from pydantic import ValidationError
from pydantic_ai import ModelRequest, ToolReturnPart, models

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from engine import Report, Source, code_for, run_workflow, validate_evidence
from fixture.harness import FixtureServer

ROOT = Path(__file__).resolve().parents[1]
SCENARIO = json.loads((ROOT / "scenario.json").read_text())


@pytest.mark.parametrize("mode", ["tools", "code"])
def test_agent_executes_mcp_and_returns_grounded_report(mode):
    async def run():
        models.ALLOW_MODEL_REQUESTS = False
        with FixtureServer(mode) as fixture:
            fixture.reject_bad_token()
            report = await run_workflow(SCENARIO, url=fixture.url, token="local-fixture-token", mode=mode, fixture=True)
        assert report.status == "complete"
        assert report.workflow == SCENARIO["title"]
        assert report.metrics == SCENARIO["expected_metrics"]
        expected_ids = {record["id"] for step in SCENARIO["steps"] for record in step["records"]}
        assert {source.id for source in report.sources} == expected_ids
    asyncio.run(run())


def test_rejects_invented_source_and_missing_evidence():
    report = Report(workflow=SCENARIO["title"], status="complete", summary="Example", sources=[Source(id="invented", app="example", title="Not retrieved")])
    with pytest.raises(ValueError, match="not returned"):
        validate_evidence(report, [])


def test_report_requires_source_references_and_missing_work_explanation():
    with pytest.raises(ValidationError):
        Report(workflow="Example", status="complete", summary="No evidence")
    with pytest.raises(ValidationError):
        Report(workflow="Example", status="needs_connection", summary="Missing app")


def test_rejects_crossed_source_id_and_url_from_different_records():
    report = Report(workflow="Example", status="complete", summary="Example", sources=[Source(id="record-a", app="Example", title="A", url="https://example.com/b")])
    messages = [ModelRequest(parts=[ToolReturnPart(tool_name="example__read", content={"records": [{"id": "record-a", "url": "https://example.com/a"}, {"id": "record-b", "url": "https://example.com/b"}]}, tool_call_id="read-1")])]
    with pytest.raises(ValueError, match="together"):
        validate_evidence(report, messages)
    report.sources[0].url = "https://example.com/a"
    validate_evidence(report, messages)


def test_code_uses_alias_namespaces_and_only_declared_actions():
    code = code_for(SCENARIO)
    for step in SCENARIO["steps"]:
        assert f"weavz.{step['alias']}.{step.get('function', step['action'].replace('-', '_'))}(" in code
    assert "await weavz_search(" not in code
