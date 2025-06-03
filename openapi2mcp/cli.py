import click
from .parser import load_openapi_spec, OpenAPIParserError
from .generator import generate_mcp_server_code # Updated import

@click.group()
def main():
    """
    OpenAPI to FastMCP server converter.
    """
    pass

@main.command()
@click.option(
    "-i",
    "--input-file",
    required=True,
    type=click.Path(exists=True, dir_okay=False, readable=True),
    help="Path to the input OpenAPI 3.x specification file (YAML or JSON).",
)
@click.option(
    "-o",
    "--output-file",
    required=True,
    type=click.Path(dir_okay=False, writable=True),
    help="Path to save the generated FastMCP server Python file.",
)
@click.option(
    "--transport",
    type=click.Choice(['stdio', 'sse', 'http'], case_sensitive=False),
    default='stdio',
    show_default=True,
    help="The transport protocol to run the generated MCP server with.",
)
def generate(input_file: str, output_file: str, transport: str):
    """
    Generates a FastMCP server from an OpenAPI specification.
    """
    click.echo(f"Input OpenAPI file: {input_file}")
    click.echo(f"Output MCP server file: {output_file}")

    try:
        spec = load_openapi_spec(input_file)
        click.echo(click.style("OpenAPI specification loaded successfully.", fg="green"))

        api_title = spec.get('info', {}).get('title', 'GeneratedAPI')
        api_version = spec.get('info', {}).get('version', '0.1.0')
        mcp_app_details = {"name": api_title, "version": api_version}

        click.echo(f"API Title: {api_title}, Version: {api_version}, Selected transport: {transport}")

        generated_code = generate_mcp_server_code(spec, mcp_app_details, transport)

        # Remove or comment out old Pydantic models echo
        # schemas = spec.get('components', {}).get('schemas', {})
        # if schemas:
        #     click.echo(click.style("\nGenerating Pydantic models...", fg="blue"))
        #     models_code = generate_pydantic_models(schemas) # This function is still used by generate_mcp_server_code
        #     click.echo(models_code)
        # else:
        #     click.echo(click.style("\nNo component schemas found to generate Pydantic models.", fg="yellow"))

        try:
            with open(output_file, 'w', encoding='utf-8') as f:
                f.write(generated_code)
            click.echo(click.style(f"MCP server code successfully generated to {output_file}", fg="green"))
        except IOError as e:
            click.echo(click.style(f"Error writing to output file {output_file}: {e}", fg="red"), err=True)

    except FileNotFoundError as e:
        click.echo(click.style(f"Error: {e}", fg="red"), err=True)
    except OpenAPIParserError as e:
        click.echo(click.style(f"Error parsing OpenAPI spec: {e}", fg="red"), err=True)
    except Exception as e:
        click.echo(click.style(f"An unexpected error occurred: {e}", fg="red"), err=True)

if __name__ == '__main__':
    main()
