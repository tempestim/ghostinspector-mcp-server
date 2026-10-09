"""Tests for the Ghost Inspector MCP server against a mocked API."""

import asyncio
import json

import httpx
import pytest
import respx

from ghostinspector_mcp import server
from ghostinspector_mcp.client import (
    DEFAULT_TIMEOUT,
    EXECUTE_TIMEOUT,
    GhostInspectorClient,
    GhostInspectorError,
)

API = GhostInspectorClient.BASE_URL


@pytest.fixture(autouse=True)
def client(monkeypatch):
    c = GhostInspectorClient("key123")
    monkeypatch.setattr(server, "_client", c)
    return c


def ok(data):
    return {"code": "SUCCESS", "data": data}


@respx.mock
def test_requests_send_api_key_and_unwrap_data():
    route = respx.get(f"{API}/tests").respond(
        json=ok([{"_id": "t1", "name": "Login", "suite": {"name": "Smoke"}, "importOnly": True}])
    )
    out = json.loads(server.list_tests())
    assert route.calls.last.request.url.params["apiKey"] == "key123"
    assert out[0]["suite"] == "Smoke"
    assert out[0]["importOnly"] is True


@respx.mock
def test_api_error_code_raises_tool_error_with_message():
    respx.get(f"{API}/tests/bad").respond(json={"code": "ERROR", "message": "Test not found"})
    with pytest.raises(GhostInspectorError, match="Test not found"):
        server.get_test("bad")


@respx.mock
def test_http_error_status_raises_tool_error():
    respx.get(f"{API}/suites/x").respond(401, json={"code": "ERROR", "message": "Bad key"})
    with pytest.raises(GhostInspectorError, match=r"\(401\): Bad key"):
        server.get_suite("x")


@respx.mock
def test_execute_uses_long_timeout():
    route = respx.post(f"{API}/tests/t1/execute").respond(json=ok({"passing": True}))
    server.execute_test("t1", browser="firefox")
    request = route.calls.last.request
    assert request.url.params["browser"] == "firefox"
    assert request.extensions["timeout"]["read"] == EXECUTE_TIMEOUT


@respx.mock
def test_timeout_suggests_immediate():
    respx.post(f"{API}/suites/s1/execute").mock(side_effect=httpx.ReadTimeout("slow"))
    with pytest.raises(GhostInspectorError, match="immediate=True"):
        server.execute_suite("s1")


def test_invalid_steps_json_is_a_tool_error():
    with pytest.raises(GhostInspectorError, match="Invalid steps JSON"):
        server.import_test("s1", "New", "https://example.com", "not json")


@respx.mock
def test_get_module_usage_finds_importing_tests():
    respx.get(f"{API}/tests/mod").respond(json=ok({"_id": "mod", "name": "Login module"}))
    respx.get(f"{API}/tests").respond(
        json=ok([{"_id": "mod"}, {"_id": "a", "name": "Checkout"}, {"_id": "b", "name": "Search"}])
    )
    respx.get(f"{API}/tests/a").respond(
        json=ok(
            {
                "steps": [{"command": "importTest", "target": "mod"}],
                "suite": {"_id": "s1", "name": "Smoke"},
            }
        )
    )
    respx.get(f"{API}/tests/b").respond(json=ok({"steps": [{"command": "click"}]}))

    out = json.loads(server.get_module_usage("mod"))

    assert out["module_name"] == "Login module"
    assert out["importing_tests"] == [
        {"_id": "a", "name": "Checkout", "suite_id": "s1", "suite_name": "Smoke"}
    ]


def test_tools_are_annotated():
    tools = {t.name: t.annotations for t in asyncio.run(server.mcp.list_tools())}
    assert len(tools) == 24
    assert tools["list_tests"].read_only_hint is True
    assert tools["execute_test"].read_only_hint is False
    assert tools["execute_test"].destructive_hint is False
    assert tools["cancel_suite_result"].destructive_hint is True


@respx.mock
def test_immediate_execute_uses_default_timeout():
    route = respx.post(f"{API}/suites/s1/execute").respond(json=ok([]))
    server.execute_suite("s1", immediate=True)
    assert route.calls.last.request.extensions["timeout"]["read"] == DEFAULT_TIMEOUT


@respx.mock
def test_timeout_on_quick_call_does_not_suggest_immediate():
    respx.get(f"{API}/tests/t1").mock(side_effect=httpx.ReadTimeout("slow"))
    with pytest.raises(GhostInspectorError) as exc:
        server.get_test("t1")
    assert "immediate" not in str(exc.value)


@respx.mock
def test_non_json_success_response_is_an_error():
    respx.get(f"{API}/folders").respond(200, text="<html>Bad gateway</html>")
    with pytest.raises(GhostInspectorError, match=r"non-JSON response \(200\): <html>Bad gateway"):
        server.list_folders()
