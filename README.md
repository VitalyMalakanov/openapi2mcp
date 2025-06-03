# openapi2mcp

A tool to convert OpenAPI 3.x specifications to FastMCP servers.

## Installation

```bash
poetry install
```

## Usage

```bash
openapi2mcp --input openapi.yaml --output server.py
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