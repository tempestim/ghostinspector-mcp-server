"""Ghost Inspector API client."""

from typing import Any, Optional

import httpx
from mcp.server.mcpserver.exceptions import ToolError

# Executing a test or suite without immediate=True waits for it to finish, which
# can take many minutes; everything else should be quick.
DEFAULT_TIMEOUT = 60.0
EXECUTE_TIMEOUT = 900.0


class GhostInspectorError(ToolError):
    """An anticipated failure whose message is shown to the model."""


def _execute_timeout(immediate: bool) -> float:
    """Only executions that wait for the run to finish need the long timeout."""
    return DEFAULT_TIMEOUT if immediate else EXECUTE_TIMEOUT


class GhostInspectorClient:
    """Client for interacting with the Ghost Inspector API."""

    BASE_URL = "https://api.ghostinspector.com/v1"

    def __init__(self, api_key: str):
        """Initialize the client with an API key."""
        self.api_key = api_key
        self._client = httpx.Client(timeout=DEFAULT_TIMEOUT)

    def _request(
        self,
        method: str,
        endpoint: str,
        params: Optional[dict] = None,
        json_data: Optional[dict] = None,
        timeout: float = DEFAULT_TIMEOUT,
    ) -> Any:
        """Make a request to the Ghost Inspector API."""
        url = f"{self.BASE_URL}/{endpoint}"
        params = params or {}
        params["apiKey"] = self.api_key

        try:
            response = self._client.request(
                method=method,
                url=url,
                params=params,
                json=json_data,
                timeout=timeout,
            )
        except httpx.TimeoutException as e:
            message = f"Ghost Inspector did not respond within {timeout:.0f}s."
            if timeout == EXECUTE_TIMEOUT:
                message += " For long runs, execute with immediate=True and poll the result."
            raise GhostInspectorError(message) from e
        except httpx.HTTPError as e:
            raise GhostInspectorError(f"Could not reach Ghost Inspector: {e!r}") from e

        status = f" ({response.status_code})" if response.status_code >= 400 else ""
        try:
            result = response.json()
        except ValueError:
            # e.g. an HTML error page from a proxy; never treat it as a successful result
            body = (response.text or response.reason_phrase).strip()[:500]
            raise GhostInspectorError(
                f"Ghost Inspector returned an unexpected non-JSON response"
                f" ({response.status_code}): {body}"
            ) from None
        if not isinstance(result, dict):
            raise GhostInspectorError(
                f"Ghost Inspector returned an unexpected response{status}: {str(result)[:500]}"
            )

        if response.status_code >= 400 or result.get("code") == "ERROR":
            message = result.get("message") or response.text or response.reason_phrase
            raise GhostInspectorError(f"Ghost Inspector API error{status}: {message}")

        return result.get("data", result)

    # ==================== Tests ====================

    def list_tests(self) -> list[dict]:
        """List all tests in the account."""
        return self._request("GET", "tests")

    def get_test(self, test_id: str) -> dict:
        """Get a single test by ID."""
        return self._request("GET", f"tests/{test_id}")

    def execute_test(
        self,
        test_id: str,
        start_url: Optional[str] = None,
        browser: Optional[str] = None,
        region: Optional[str] = None,
        viewport: Optional[str] = None,
        immediate: bool = False,
        variables: Optional[dict] = None,
    ) -> dict:
        """Execute a test and return the result."""
        params = {}
        if start_url:
            params["startUrl"] = start_url
        if browser:
            params["browser"] = browser
        if region:
            params["region"] = region
        if viewport:
            params["viewport"] = viewport
        if immediate:
            params["immediate"] = "true"
        if variables:
            for key, value in variables.items():
                params[key] = value

        return self._request(
            "POST",
            f"tests/{test_id}/execute",
            params=params,
            timeout=_execute_timeout(immediate),
        )

    def list_test_results(self, test_id: str, count: int = 10, offset: int = 0) -> list[dict]:
        """List results for a specific test."""
        return self._request(
            "GET",
            f"tests/{test_id}/results",
            params={"count": count, "offset": offset},
        )

    def get_test_result(self, result_id: str) -> dict:
        """Get a specific test result."""
        return self._request("GET", f"results/{result_id}")

    def cancel_test_result(self, result_id: str) -> dict:
        """Cancel a running test result."""
        return self._request("POST", f"results/{result_id}/cancel")

    def duplicate_test(self, test_id: str) -> dict:
        """Duplicate an existing test."""
        return self._request("POST", f"tests/{test_id}/duplicate")

    def execute_on_demand_test(
        self,
        org_id: str,
        test_definition: dict,
        start_url: Optional[str] = None,
        browser: Optional[str] = None,
        region: Optional[str] = None,
        viewport: Optional[str] = None,
        immediate: bool = False,
    ) -> dict:
        """Execute an on-demand test from a JSON definition.

        The test is executed but not permanently saved to the account.
        """
        params = {"organizationId": org_id}
        if start_url:
            params["startUrl"] = start_url
        if browser:
            params["browser"] = browser
        if region:
            params["region"] = region
        if viewport:
            params["viewport"] = viewport
        if immediate:
            params["immediate"] = "true"

        return self._request(
            "POST",
            "tests/on-demand/execute",
            params=params,
            json_data=test_definition,
            timeout=_execute_timeout(immediate),
        )

    # ==================== Suites ====================

    def list_suites(self) -> list[dict]:
        """List all suites in the account."""
        return self._request("GET", "suites")

    def get_suite(self, suite_id: str) -> dict:
        """Get a single suite by ID."""
        return self._request("GET", f"suites/{suite_id}")

    def execute_suite(
        self,
        suite_id: str,
        start_url: Optional[str] = None,
        browser: Optional[str] = None,
        region: Optional[str] = None,
        viewport: Optional[str] = None,
        immediate: bool = False,
        variables: Optional[dict] = None,
    ) -> list[dict]:
        """Execute all tests in a suite and return the results."""
        params = {}
        if start_url:
            params["startUrl"] = start_url
        if browser:
            params["browser"] = browser
        if region:
            params["region"] = region
        if viewport:
            params["viewport"] = viewport
        if immediate:
            params["immediate"] = "true"
        if variables:
            for key, value in variables.items():
                params[key] = value

        return self._request(
            "POST",
            f"suites/{suite_id}/execute",
            params=params,
            timeout=_execute_timeout(immediate),
        )

    def list_suite_tests(self, suite_id: str) -> list[dict]:
        """List all tests in a suite."""
        return self._request("GET", f"suites/{suite_id}/tests")

    def list_suite_results(self, suite_id: str, count: int = 10, offset: int = 0) -> list[dict]:
        """List results for a specific suite."""
        return self._request(
            "GET",
            f"suites/{suite_id}/results",
            params={"count": count, "offset": offset},
        )

    def get_suite_result(self, result_id: str) -> dict:
        """Get a specific suite result."""
        return self._request("GET", f"suite-results/{result_id}")

    def cancel_suite_result(self, result_id: str) -> dict:
        """Cancel a running suite result."""
        return self._request("POST", f"suite-results/{result_id}/cancel")

    def list_suite_result_tests(self, result_id: str) -> list[dict]:
        """List test results within a suite result."""
        return self._request("GET", f"suite-results/{result_id}/results")

    def import_test(self, suite_id: str, test_definition: dict) -> dict:
        """Import a test into a suite from a JSON definition.

        The test is permanently saved to the specified suite.
        """
        return self._request(
            "POST", f"suites/{suite_id}/import-test/json", json_data=test_definition
        )

    # ==================== Folders ====================

    def list_folders(self) -> list[dict]:
        """List all folders in the account."""
        return self._request("GET", "folders")

    def get_folder(self, folder_id: str) -> dict:
        """Get a single folder by ID."""
        return self._request("GET", f"folders/{folder_id}")

    def list_folder_suites(self, folder_id: str) -> list[dict]:
        """List all suites in a folder."""
        return self._request("GET", f"folders/{folder_id}/suites")

    # ==================== Organizations ====================

    def get_running(self, org_id: str) -> list[dict]:
        """Get currently running tests for an organization."""
        return self._request("GET", f"organizations/{org_id}/running")

    def close(self):
        """Close the HTTP client."""
        self._client.close()
