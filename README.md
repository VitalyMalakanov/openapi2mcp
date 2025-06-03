# openapi2mcp

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

## License

MIT - See [LICENSE](LICENSE)