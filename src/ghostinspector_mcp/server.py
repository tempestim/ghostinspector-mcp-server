"""Ghost Inspector MCP Server."""

import json
import os
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Optional

from mcp.server.mcpserver import MCPServer
from mcp.types import ToolAnnotations

from .client import GhostInspectorClient, GhostInspectorError

# Initialize the MCP server
mcp = MCPServer("ghostinspector")

READ_ONLY = ToolAnnotations(readOnlyHint=True, openWorldHint=True)
# Runs or creates tests: changes state, but never deletes anything.
WRITE = ToolAnnotations(readOnlyHint=False, destructiveHint=False, openWorldHint=True)
CANCEL = ToolAnnotations(readOnlyHint=False, destructiveHint=True, openWorldHint=True)

# Global client instance
_client: Optional[GhostInspectorClient] = None


def get_client() -> GhostInspectorClient:
    """Get or create the Ghost Inspector client."""
    global _client
    if _client is None:
        api_key = os.environ.get("GHOST_INSPECTOR_API_KEY")
        if not api_key:
            raise GhostInspectorError(
                "GHOST_INSPECTOR_API_KEY environment variable is required. "
                "Get your API key from https://app.ghostinspector.com/account"
            )
        _client = GhostInspectorClient(api_key)
    return _client


def format_response(data: Any) -> str:
    """Format response data as JSON string."""
    return json.dumps(data, indent=2, default=str)


# ==================== Organization & Hierarchy Tools ====================


@mcp.tool(annotations=READ_ONLY)
def get_hierarchy() -> str:
    """Get the complete organizational hierarchy of folders, suites, and tests.

    Returns the full tree structure showing:
    - Folders containing their suites
    - Suites with their test counts and module status
    - Unorganized suites (not in any folder)

    This provides a single-call overview of your entire test organization,
    making it easy to understand the structure without multiple API calls.
    """
    client = get_client()
    folders = client.list_folders()
    suites = client.list_suites()

    # Build folder lookup
    folder_map = {
        f.get("_id"): {"_id": f.get("_id"), "name": f.get("name"), "suites": []} for f in folders
    }

    unorganized = []
    for suite in suites:
        folder_id = suite.get("folder")
        suite_info = {
            "_id": suite.get("_id"),
            "name": suite.get("name"),
            "testCount": suite.get("testCount"),
            "passing": suite.get("passing"),
        }
        if folder_id and folder_id in folder_map:
            folder_map[folder_id]["suites"].append(suite_info)
        else:
            unorganized.append(suite_info)

    result = {
        "folders": list(folder_map.values()),
        "unorganized_suites": unorganized,
    }
    return format_response(result)


@mcp.tool(annotations=READ_ONLY)
def list_modules() -> str:
    """List reusable test modules in your Ghost Inspector account.

    Modules are tests with importOnly=true. They are designed to be imported
    into other tests using the 'Import steps from test' step, rather than
    run independently. Common examples include login flows, navigation
    sequences, and setup/teardown procedures.

    Returns modules grouped by their containing suite.
    """
    client = get_client()
    tests = client.list_tests()

    # Filter to only importOnly tests and group by suite
    modules_by_suite: dict[str, list] = {}
    for t in tests:
        if t.get("importOnly") is True:
            suite_name = (
                t.get("suite", {}).get("name") if isinstance(t.get("suite"), dict) else "Unknown"
            )
            if suite_name not in modules_by_suite:
                modules_by_suite[suite_name] = []
            modules_by_suite[suite_name].append(
                {
                    "_id": t.get("_id"),
                    "name": t.get("name"),
                }
            )

    result = [
        {"suite": suite_name, "modules": modules}
        for suite_name, modules in modules_by_suite.items()
    ]
    return format_response(result)


@mcp.tool(annotations=READ_ONLY)
def get_module_usage(module_id: str) -> str:
    """Find all tests that import a specific module.

    This helps with impact analysis when modifying a module, showing which
    tests depend on it. Note: This scans all test steps, which may be slow
    for accounts with many tests.

    Args:
        module_id: The ID of the module (test) to find usage for.

    Returns:
        List of tests that import this module, with their suite information.
    """
    client = get_client()

    # First get the module info
    try:
        module = client.get_test(module_id)
        module_name = module.get("name", "Unknown")
    except GhostInspectorError:
        module_name = "Unknown"

    candidates = [t for t in client.list_tests() if t.get("_id") != module_id]

    def imports_module(t: dict) -> Optional[dict]:
        try:
            test_detail = client.get_test(t.get("_id"))
        except GhostInspectorError:
            return None
        for step in test_detail.get("steps", []):
            # Check for importTest command targeting this module
            if step.get("command") == "importTest" and step.get("target") == module_id:
                suite_info = test_detail.get("suite", {})
                return {
                    "_id": t.get("_id"),
                    "name": t.get("name"),
                    "suite_id": suite_info.get("_id") if isinstance(suite_info, dict) else None,
                    "suite_name": suite_info.get("name") if isinstance(suite_info, dict) else None,
                }
        return None

    # Every test's steps must be fetched individually; do it a few at a time.
    with ThreadPoolExecutor(max_workers=8) as pool:
        importing_tests = [r for r in pool.map(imports_module, candidates) if r]

    return format_response(
        {
            "module_id": module_id,
            "module_name": module_name,
            "importing_tests_count": len(importing_tests),
            "importing_tests": importing_tests,
        }
    )


# ==================== Test Tools ====================


@mcp.tool(annotations=READ_ONLY)
def list_tests() -> str:
    """List all tests in your Ghost Inspector account.

    Returns a list of all tests with their IDs, names, status, and module indicator.
    Tests with importOnly=true are reusable modules designed to be imported into other tests.
    """
    client = get_client()
    tests = client.list_tests()
    # Return simplified view
    simplified = [
        {
            "_id": t.get("_id"),
            "name": t.get("name"),
            "suite": t.get("suite", {}).get("name")
            if isinstance(t.get("suite"), dict)
            else t.get("suite"),
            "importOnly": t.get("importOnly", False),
            "passing": t.get("passing"),
            "screenshotComparePassing": t.get("screenshotComparePassing"),
            "dateExecuted": t.get("dateExecuted"),
        }
        for t in tests
    ]
    return format_response(simplified)


@mcp.tool(annotations=READ_ONLY)
def get_test(test_id: str) -> str:
    """Get detailed information about a specific test.

    Args:
        test_id: The ID of the test to retrieve.

    Returns:
        Detailed test information including steps, settings, and last execution status.
    """
    client = get_client()
    test = client.get_test(test_id)
    return format_response(test)


@mcp.tool(annotations=WRITE)
def execute_test(
    test_id: str,
    start_url: Optional[str] = None,
    browser: Optional[str] = None,
    region: Optional[str] = None,
    viewport: Optional[str] = None,
    immediate: bool = False,
) -> str:
    """Execute a Ghost Inspector test.

    Args:
        test_id: The ID of the test to execute.
        start_url: Override the starting URL for the test.
        browser: Browser to use (e.g., 'chrome', 'firefox', 'chrome-*').
        region: Region to run from (e.g., 'us-east-1', 'eu-west-1').
        viewport: Viewport size (e.g., '1280x1024', '800x600').
        immediate: If True, return immediately without waiting for completion.

    Returns:
        Test execution result including pass/fail status and any errors.
    """
    client = get_client()
    result = client.execute_test(
        test_id=test_id,
        start_url=start_url,
        browser=browser,
        region=region,
        viewport=viewport,
        immediate=immediate,
    )
    return format_response(result)


@mcp.tool(annotations=READ_ONLY)
def list_test_results(test_id: str, count: int = 10, offset: int = 0) -> str:
    """List execution results for a specific test.

    Args:
        test_id: The ID of the test.
        count: Number of results to return (default: 10).
        offset: Offset for pagination (default: 0).

    Returns:
        List of test execution results with pass/fail status and timestamps.
    """
    client = get_client()
    results = client.list_test_results(test_id, count=count, offset=offset)
    # Return simplified view
    simplified = [
        {
            "_id": r.get("_id"),
            "name": r.get("name"),
            "passing": r.get("passing"),
            "screenshotComparePassing": r.get("screenshotComparePassing"),
            "dateExecuted": r.get("dateExecuted"),
            "executionTime": r.get("executionTime"),
            "browser": r.get("browser"),
        }
        for r in results
    ]
    return format_response(simplified)


@mcp.tool(annotations=READ_ONLY)
def get_test_result(result_id: str) -> str:
    """Get detailed information about a specific test result.

    Args:
        result_id: The ID of the test result.

    Returns:
        Detailed result including steps executed, screenshots, and any errors.
    """
    client = get_client()
    result = client.get_test_result(result_id)
    return format_response(result)


@mcp.tool(annotations=CANCEL)
def cancel_test_result(result_id: str) -> str:
    """Cancel a running test execution.

    Args:
        result_id: The ID of the running test result to cancel.

    Returns:
        Confirmation of cancellation.
    """
    client = get_client()
    result = client.cancel_test_result(result_id)
    return format_response(result)


@mcp.tool(annotations=WRITE)
def duplicate_test(test_id: str) -> str:
    """Duplicate an existing test to create a copy.

    Args:
        test_id: The ID of the test to duplicate.

    Returns:
        The newly created test object with its new ID.
    """
    client = get_client()
    result = client.duplicate_test(test_id)
    return format_response(result)


@mcp.tool(annotations=WRITE)
def execute_on_demand_test(
    org_id: str,
    name: str,
    start_url: str,
    steps: str,
    browser: Optional[str] = None,
    region: Optional[str] = None,
    viewport: Optional[str] = None,
    immediate: bool = False,
) -> str:
    """Execute a test from a JSON definition without saving it permanently.

    This allows running ad-hoc tests defined in code without creating persistent tests.

    Args:
        org_id: Your Ghost Inspector organization ID.
        name: Name for the test.
        start_url: The URL where the test should start.
        steps: JSON array of test steps. Each step should have 'command' and 'target'.
               Example: '[{"command": "click", "target": ".button"}, {"command": "assertTextPresent", "target": "body", "value": "Success"}]'
               Available commands: click, type, open, assertTextPresent, assertElementPresent,
               assertElementVisible, extract, eval, mouseOver, keypress, pause, screenshot, etc.
        browser: Browser to use (e.g., 'chrome', 'firefox').
        region: Region to run from (e.g., 'us-east-1', 'eu-west-1').
        viewport: Viewport size (e.g., '1280x1024').
        immediate: If True, return immediately without waiting for completion.

    Returns:
        Test execution result.
    """
    client = get_client()
    # Parse the steps JSON
    try:
        steps_list = json.loads(steps)
    except json.JSONDecodeError as e:
        raise GhostInspectorError(f"Invalid steps JSON: {e}") from e

    test_definition = {
        "name": name,
        "startUrl": start_url,
        "steps": steps_list,
    }

    result = client.execute_on_demand_test(
        org_id=org_id,
        test_definition=test_definition,
        browser=browser,
        region=region,
        viewport=viewport,
        immediate=immediate,
    )
    return format_response(result)


# ==================== Suite Tools ====================


@mcp.tool(annotations=READ_ONLY)
def list_suites() -> str:
    """List all test suites in your Ghost Inspector account.

    Returns a list of all suites with their IDs, names, folder information,
    and test counts. Includes resolved folder names for easy identification.
    """
    client = get_client()
    suites = client.list_suites()
    folders = client.list_folders()

    # Build folder name lookup
    folder_names = {f.get("_id"): f.get("name") for f in folders}

    # Return simplified view with resolved folder names
    simplified = [
        {
            "_id": s.get("_id"),
            "name": s.get("name"),
            "folder_id": s.get("folder"),
            "folder_name": folder_names.get(s.get("folder")),
            "testCount": s.get("testCount"),
            "passing": s.get("passing"),
            "dateExecuted": s.get("dateExecuted"),
        }
        for s in suites
    ]
    return format_response(simplified)


@mcp.tool(annotations=READ_ONLY)
def get_suite(suite_id: str) -> str:
    """Get detailed information about a specific suite.

    Args:
        suite_id: The ID of the suite to retrieve.

    Returns:
        Detailed suite information including settings and last execution status.
    """
    client = get_client()
    suite = client.get_suite(suite_id)
    return format_response(suite)


@mcp.tool(annotations=WRITE)
def execute_suite(
    suite_id: str,
    start_url: Optional[str] = None,
    browser: Optional[str] = None,
    region: Optional[str] = None,
    viewport: Optional[str] = None,
    immediate: bool = False,
) -> str:
    """Execute all tests in a Ghost Inspector suite.

    Args:
        suite_id: The ID of the suite to execute.
        start_url: Override the starting URL for all tests.
        browser: Browser to use (e.g., 'chrome', 'firefox').
        region: Region to run from (e.g., 'us-east-1', 'eu-west-1').
        viewport: Viewport size (e.g., '1280x1024', '800x600').
        immediate: If True, return immediately without waiting for completion.

    Returns:
        Suite execution results including individual test results.
    """
    client = get_client()
    results = client.execute_suite(
        suite_id=suite_id,
        start_url=start_url,
        browser=browser,
        region=region,
        viewport=viewport,
        immediate=immediate,
    )
    return format_response(results)


@mcp.tool(annotations=READ_ONLY)
def list_suite_tests(suite_id: str) -> str:
    """List all tests in a specific suite.

    Args:
        suite_id: The ID of the suite.

    Returns:
        List of tests in the suite with their IDs, names, and module indicator.
        Tests with importOnly=true are reusable modules.
    """
    client = get_client()
    tests = client.list_suite_tests(suite_id)
    # Return simplified view
    simplified = [
        {
            "_id": t.get("_id"),
            "name": t.get("name"),
            "importOnly": t.get("importOnly", False),
            "passing": t.get("passing"),
            "screenshotComparePassing": t.get("screenshotComparePassing"),
            "dateExecuted": t.get("dateExecuted"),
        }
        for t in tests
    ]
    return format_response(simplified)


@mcp.tool(annotations=READ_ONLY)
def list_suite_results(suite_id: str, count: int = 10, offset: int = 0) -> str:
    """List execution results for a specific suite.

    Args:
        suite_id: The ID of the suite.
        count: Number of results to return (default: 10).
        offset: Offset for pagination (default: 0).

    Returns:
        List of suite execution results with pass/fail status.
    """
    client = get_client()
    results = client.list_suite_results(suite_id, count=count, offset=offset)
    # Return simplified view
    simplified = [
        {
            "_id": r.get("_id"),
            "name": r.get("name"),
            "passing": r.get("passing"),
            "countPassing": r.get("countPassing"),
            "countFailing": r.get("countFailing"),
            "dateExecuted": r.get("dateExecuted"),
            "executionTime": r.get("executionTime"),
        }
        for r in results
    ]
    return format_response(simplified)


@mcp.tool(annotations=READ_ONLY)
def get_suite_result(result_id: str) -> str:
    """Get detailed information about a specific suite result.

    Args:
        result_id: The ID of the suite result.

    Returns:
        Detailed suite result including individual test results.
    """
    client = get_client()
    result = client.get_suite_result(result_id)
    return format_response(result)


@mcp.tool(annotations=READ_ONLY)
def list_suite_result_tests(result_id: str) -> str:
    """List all test results within a suite execution.

    Args:
        result_id: The ID of the suite result.

    Returns:
        List of individual test results from the suite execution.
    """
    client = get_client()
    results = client.list_suite_result_tests(result_id)
    # Return simplified view
    simplified = [
        {
            "_id": r.get("_id"),
            "name": r.get("name"),
            "passing": r.get("passing"),
            "screenshotComparePassing": r.get("screenshotComparePassing"),
            "executionTime": r.get("executionTime"),
            "browser": r.get("browser"),
        }
        for r in results
    ]
    return format_response(simplified)


@mcp.tool(annotations=CANCEL)
def cancel_suite_result(result_id: str) -> str:
    """Cancel a running suite execution.

    Args:
        result_id: The ID of the running suite result to cancel.

    Returns:
        Confirmation of cancellation.
    """
    client = get_client()
    result = client.cancel_suite_result(result_id)
    return format_response(result)


@mcp.tool(annotations=WRITE)
def import_test(
    suite_id: str,
    name: str,
    start_url: str,
    steps: str,
) -> str:
    """Import a test into a suite, permanently saving it.

    This creates a new test in the specified suite from a JSON definition.

    Args:
        suite_id: The ID of the suite to import the test into.
        name: Name for the test.
        start_url: The URL where the test should start.
        steps: JSON array of test steps. Each step should have 'command' and 'target'.
               Example: '[{"command": "click", "target": ".button"}, {"command": "type", "target": "#email", "value": "test@example.com"}]'
               Available commands: click, type, open, assertTextPresent, assertElementPresent,
               assertElementVisible, assertElementNotPresent, extract, extractEval, eval,
               mouseOver, dragAndDrop, keypress, pause, screenshot, refresh, exit.

    Returns:
        The newly created test object with its ID.
    """
    client = get_client()
    # Parse the steps JSON
    try:
        steps_list = json.loads(steps)
    except json.JSONDecodeError as e:
        raise GhostInspectorError(f"Invalid steps JSON: {e}") from e

    test_definition = {
        "name": name,
        "startUrl": start_url,
        "steps": steps_list,
    }

    result = client.import_test(suite_id=suite_id, test_definition=test_definition)
    return format_response(result)


# ==================== Folder Tools ====================


@mcp.tool(annotations=READ_ONLY)
def list_folders() -> str:
    """List all folders in your Ghost Inspector account.

    Returns a list of all folders with their IDs and names.
    """
    client = get_client()
    folders = client.list_folders()
    # Return simplified view
    simplified = [
        {
            "_id": f.get("_id"),
            "name": f.get("name"),
        }
        for f in folders
    ]
    return format_response(simplified)


@mcp.tool(annotations=READ_ONLY)
def get_folder(folder_id: str) -> str:
    """Get detailed information about a specific folder.

    Args:
        folder_id: The ID of the folder to retrieve.

    Returns:
        Detailed folder information.
    """
    client = get_client()
    folder = client.get_folder(folder_id)
    return format_response(folder)


@mcp.tool(annotations=READ_ONLY)
def list_folder_suites(folder_id: str) -> str:
    """List all suites in a specific folder.

    Args:
        folder_id: The ID of the folder.

    Returns:
        List of suites in the folder with their IDs and names.
    """
    client = get_client()
    suites = client.list_folder_suites(folder_id)
    # Return simplified view
    simplified = [
        {
            "_id": s.get("_id"),
            "name": s.get("name"),
            "testCount": s.get("testCount"),
            "passing": s.get("passing"),
        }
        for s in suites
    ]
    return format_response(simplified)


# ==================== Organization Tools ====================


@mcp.tool(annotations=READ_ONLY)
def get_running_tests(org_id: str) -> str:
    """Get currently running tests for an organization.

    Args:
        org_id: The organization ID.

    Returns:
        List of currently executing test results.
    """
    client = get_client()
    running = client.get_running(org_id)
    return format_response(running)


def main():
    """Run the MCP server."""
    mcp.run()


if __name__ == "__main__":
    main()
