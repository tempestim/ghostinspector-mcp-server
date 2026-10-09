# Ghost Inspector MCP Server

An MCP (Model Context Protocol) server for interacting with [Ghost Inspector](https://ghostinspector.com/), an automated browser testing platform.

## Features

This MCP server provides tools to:

- **Hierarchy & Modules**: View complete folder/suite structure, list reusable modules, and analyze module usage
- **Tests**: List, view, execute, create, duplicate, and manage test results
- **Suites**: List, view, execute suites, import tests, and manage suite results
- **Folders**: Browse folder structure and list suites within folders
- **Organizations**: Monitor currently running tests

## Installation

### Using pip

```bash
pip install -e /path/to/ghostinspector-mcp-server
```

### Using uv (recommended)

```bash
uv pip install -e /path/to/ghostinspector-mcp-server
```

## Configuration

### API Key

Set your Ghost Inspector API key as an environment variable:

```bash
export GHOST_INSPECTOR_API_KEY=your_api_key_here
```

You can find your API key at: https://app.ghostinspector.com/account

### Claude Code Configuration

```bash
claude mcp add ghostinspector --scope user \
  -e GHOST_INSPECTOR_API_KEY=your_api_key_here \
  -- uv run --directory /path/to/ghostinspector-mcp-server ghostinspector-mcp
```

Or add it to an MCP config file (e.g. Claude Desktop's `claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "ghostinspector": {
      "command": "ghostinspector-mcp",
      "env": {
        "GHOST_INSPECTOR_API_KEY": "your_api_key_here"
      }
    }
  }
}
```

Or, without installing it first, via uv:

```json
{
  "mcpServers": {
    "ghostinspector": {
      "command": "uv",
      "args": ["run", "--directory", "/path/to/ghostinspector-mcp-server", "ghostinspector-mcp"],
      "env": {
        "GHOST_INSPECTOR_API_KEY": "your_api_key_here"
      }
    }
  }
}
```

## Available Tools

### Hierarchy & Module Tools

| Tool | Description |
|------|-------------|
| `get_hierarchy` | Get complete folder/suite structure in a single call |
| `list_modules` | List all reusable modules (tests with `importOnly=true`) |
| `get_module_usage` | Find all tests that import a specific module |

### Test Tools

| Tool | Description |
|------|-------------|
| `list_tests` | List all tests in your account (includes `importOnly` flag) |
| `get_test` | Get detailed information about a specific test |
| `execute_test` | Execute a test with optional parameters (browser, region, viewport, start URL) |
| `duplicate_test` | Create a copy of an existing test |
| `execute_on_demand_test` | Run a test from JSON definition without saving it permanently |
| `list_test_results` | List execution history for a test |
| `get_test_result` | Get detailed result information |
| `cancel_test_result` | Cancel a running test |

### Suite Tools

| Tool | Description |
|------|-------------|
| `list_suites` | List all test suites (includes resolved folder names) |
| `get_suite` | Get suite details |
| `execute_suite` | Execute all tests in a suite |
| `import_test` | Create a new test in a suite from JSON definition |
| `list_suite_tests` | List tests within a suite (includes `importOnly` flag) |
| `list_suite_results` | List execution history for a suite |
| `get_suite_result` | Get detailed suite result |
| `list_suite_result_tests` | List individual test results from a suite run |
| `cancel_suite_result` | Cancel a running suite |

### Folder Tools

| Tool | Description |
|------|-------------|
| `list_folders` | List all folders |
| `get_folder` | Get folder details |
| `list_folder_suites` | List suites in a folder |

### Organization Tools

| Tool | Description |
|------|-------------|
| `get_running_tests` | Get currently running tests for an organization |

Tools are annotated as read-only, write (execute/create), or destructive (cancel) so clients can decide which need confirmation.

Executing a test or suite without `immediate` waits for it to finish (up to 15 minutes). For long suites, pass `immediate=True` and check the result with `get_suite_result`.

## Usage Examples

Once configured, you can use natural language to interact with Ghost Inspector:

- "List all my Ghost Inspector tests"
- "Run the test with ID abc123"
- "Show me the results for suite xyz789"
- "What tests are currently running?"
- "Execute the login test suite on Firefox"
- "Create a test that clicks the login button and verifies the dashboard loads"
- "Show me the folder and suite hierarchy"
- "List all reusable modules"
- "What tests use the login module?"

## Understanding Modules

Ghost Inspector supports **reusable test modules** - tests that are designed to be imported into other tests rather than run independently. Common examples include login flows, navigation sequences, and setup/teardown procedures.

### Identifying Modules

Tests marked with `importOnly=true` are modules. They:
- Won't execute when running a suite (they're skipped)
- Are meant to be imported into other tests using the "Import steps from test" step
- Allow you to maintain common flows in one place

### Module Tools

| Tool | Use Case |
|------|----------|
| `list_modules` | See all reusable modules grouped by suite |
| `get_module_usage` | Impact analysis before modifying a module |
| `list_tests` / `list_suite_tests` | Check `importOnly` flag to identify modules |

## Creating Tests

You can create tests programmatically using either `import_test` (saves permanently) or `execute_on_demand_test` (runs without saving).

### Test Step Format

Steps are defined as a JSON array. Each step has:
- `command`: The action to perform
- `target`: CSS selector or element identifier
- `value`: (optional) Value for the action

### Available Commands

| Command | Description | Example |
|---------|-------------|---------|
| `click` | Click an element | `{"command": "click", "target": ".submit-btn"}` |
| `type` | Type text into an input | `{"command": "type", "target": "#email", "value": "test@example.com"}` |
| `open` | Navigate to a URL | `{"command": "open", "target": "https://example.com/page"}` |
| `assertTextPresent` | Verify text exists | `{"command": "assertTextPresent", "target": "body", "value": "Welcome"}` |
| `assertElementPresent` | Verify element exists | `{"command": "assertElementPresent", "target": ".success-message"}` |
| `assertElementVisible` | Verify element is visible | `{"command": "assertElementVisible", "target": "#modal"}` |
| `extract` | Extract text to a variable | `{"command": "extract", "target": ".user-id", "value": "userId"}` |
| `eval` | Execute JavaScript | `{"command": "eval", "value": "document.title"}` |
| `pause` | Wait for milliseconds | `{"command": "pause", "value": "2000"}` |
| `screenshot` | Take a screenshot | `{"command": "screenshot"}` |
| `mouseOver` | Hover over element | `{"command": "mouseOver", "target": ".dropdown"}` |
| `keypress` | Press keyboard key | `{"command": "keypress", "target": "#input", "value": "Enter"}` |

### Example: Create a Login Test

```
Create a test in suite abc123 called "Login Test" that:
1. Goes to https://example.com/login
2. Types "user@example.com" into #email
3. Types "password123" into #password
4. Clicks the .login-button
5. Verifies "Dashboard" appears on the page
```

## Development

### Setup

```bash
# Clone the repository
cd ghostinspector-mcp-server

# Install dependencies
uv venv && uv pip install -e ".[dev]"
```

### Running Tests

```bash
pytest
```

### Code Formatting

```bash
ruff format src tests
ruff check src tests
```

## License

MIT
