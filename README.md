# openapi2mcp

[Читать на русском](README.ru.md)

A tool to convert OpenAPI 3.x specifications to FastMCP servers.

## Installation

```bash
poetry install
```

## Usage / Commands

`openapi2mcp` provides a command-line interface to generate and manage MCP server code from OpenAPI specifications.

### `generate`

Generates the MCP server Python code from an OpenAPI specification file.

**Syntax:**

```bash
openapi2mcp generate [OPTIONS]
```

**Options:**

*   `-i, --input-file PATH`: Path to the OpenAPI specification file (JSON or YAML). (Required)
*   `-o, --output-file PATH`: Path to the output Python file for the generated MCP server. (Required)
*   `-t, --transport [stdio|google_pubsub]`: The transport mechanism for the MCP server. (Default: `stdio`)
*   `--llms-txt-file PATH`: Optional path to generate an `llms.txt` file, which provides a description of the generated tools and resources for language models. If not specified, `llms.txt` will be created in the same directory as the output server file.
*   `--mount TEXT`: Optional mount path for resources (e.g., `/myapi/v1`). (Default: `""`)

**Example:**

```bash
openapi2mcp generate --input-file examples/example_openapi.yaml --output-file generated_server.py --transport stdio --mount "/api"
```

This command will parse `examples/example_openapi.yaml`, generate an MCP server file named `generated_server.py` using the `stdio` transport, and set the resource mount path to `/api`. It will also generate an `llms.txt` file in the same directory as `generated_server.py`.

### `check`

Checks a generated MCP server Python file for basic code validity, including syntax and presence of key MCP patterns.

**Syntax:**

```bash
openapi2mcp check --server-file PATH
```

**Options:**

*   `--server-file PATH`: Path to the generated MCP server Python file to check. (Required)

**Example:**

```bash
openapi2mcp check --server-file generated_server.py
```

### `version`

Displays the version of the `openapi2mcp` tool.

**Syntax:**

```bash
openapi2mcp version
```

**Example:**

```bash
openapi2mcp version
```

## Examples

See example implementations:
- [HTTP Server](examples/server_http.py)
- [SSE Server](examples/server_sse.py)
- [STDIO Server](examples/server_stdio.py)
- [Sample OpenAPI spec](examples/example_openapi.yaml)

## Project Structure

- `openapi2mcp/parser.py`: OpenAPI specification parser
- `openapi2mcp/generator.py`: FastMCP server code generator
- `openapi2mcp/cli.py`: Command-line interface

## Architecture

The project consists of three main components:

*   `parser.py`: This module is responsible for reading and parsing the OpenAPI 3.x specification file. It validates the structure and extracts relevant information about paths, operations, schemas, and parameters.
*   `generator.py`: This module takes the parsed OpenAPI data and generates the Python code for a FastMCP server. It maps OpenAPI operations to MCP resources and methods, creating the necessary handlers and data structures.
*   `cli.py`: This module provides the command-line interface for the tool, allowing users to invoke the generation process and other utility functions like checking the generated server code or displaying the tool's version.

## Core Principles / How it Works

The general workflow of `openapi2mcp` is as follows:

1.  **OpenAPI Specification Input**: The user provides an OpenAPI 3.x specification file (in JSON or YAML format) that describes their API.
2.  **Parsing**: The `parser.py` module reads this specification and transforms it into an internal representation, making it easier for the generator to understand the API structure.
3.  **Code Generation**: The `generator.py` module processes this internal representation. It iterates through the API paths and operations, generating corresponding FastMCP resources and Python functions. It also handles the conversion of OpenAPI schemas into Pydantic models for request and response validation.
4.  **MCP Server Output**: The result is a Python file containing a fully functional FastMCP server. This server can then be run using a suitable MCP transport (like STDIO or Google Pub/Sub).
5.  **LLMs Description (Optional)**: Alongside the server, an `llms.txt` file can be generated. This file provides a natural language description of the tools (API endpoints) and resources available in the generated server, which can be useful for integration with Large Language Models.

## Customization

The generated MCP server code is standard Python and FastMCP code. This means you can:

*   **Modify the generated code**: Feel free to edit the output Python file to tweak logic, add custom error handling, or integrate additional functionalities not covered by the OpenAPI specification.
*   **Extend functionality**: You can add new MCP resources or methods to the generated server, or import and use other Python libraries within your server code.
*   **Change transport or middleware**: While the transport is selected during generation, you can manually adjust the server setup or add FastMCP middleware as needed.

<!-- Add PyPI version badge here -->
<!-- Add License badge here -->
<!-- Add other relevant badges here (e.g., build status, code coverage) -->

## License

MIT - See [LICENSE](LICENSE)