import click
from pathlib import Path # Added for llms.txt path manipulation
from .parser import load_openapi_spec, OpenAPIParserError
from .generator import generate_mcp_server_code, generate_llms_txt # Updated import

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
@click.option(
    "--llms-txt-file",
    type=click.Path(dir_okay=False, writable=True, allow_dash=False),
    default=None,
    help="Path to save the LLM tools description file (llms.txt). Defaults to [OUTPUT_FILE].llms.txt.",
)
def generate(input_file: str, output_file: str, transport: str, llms_txt_file: str | None):
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

        server_code, tool_names_for_llms = generate_mcp_server_code(spec, mcp_app_details, transport)

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
                f.write(server_code)
            click.echo(click.style(f"MCP server code successfully generated to {output_file}", fg="green"))
        except IOError as e:
            click.echo(click.style(f"Error writing to output file {output_file}: {e}", fg="red"), err=True)
            # Potentially exit or don't proceed to llms.txt if server writing failed
            return # Exit if server file writing fails

        # Determine path for llms.txt and generate it
        llms_output_path = llms_txt_file
        if not llms_output_path:
            if output_file == "-": # Check if output_file itself is stdout, though type=Path might prevent this.
                                   # click.Path(allow_dash=True) would be needed for stdout for output_file.
                                   # Current type for output_file does not allow dash.
                click.echo(click.style("Skipping llms.txt generation when main output is stdout (not currently supported for main output).", fg="yellow"))
                llms_output_path = None
            else:
                # Ensure output_file is not a directory, which click.Path(dir_okay=False) should handle.
                p = Path(output_file)
                llms_output_path = str(p.parent / (p.name + ".llms.txt"))

        if llms_output_path:
            if tool_names_for_llms:
                llms_content = generate_llms_txt(spec, tool_names_for_llms)
                try:
                    with open(llms_output_path, 'w', encoding='utf-8') as f:
                        f.write(llms_content)
                    click.echo(click.style(f"LLM tools description saved to {llms_output_path}", fg="green"))
                except IOError as e:
                    click.echo(click.style(f"Error writing LLM tools description to {llms_output_path}: {e}", fg="red"), err=True)
            else:
                click.echo(click.style(f"No tools found to generate {llms_output_path}", fg="yellow"))

    except FileNotFoundError as e:
        click.echo(click.style(f"Error: {e}", fg="red"), err=True)
    except OpenAPIParserError as e:
        click.echo(click.style(f"Error parsing OpenAPI spec: {e}", fg="red"), err=True)
    except Exception as e:
        click.echo(click.style(f"An unexpected error occurred: {e}", fg="red"), err=True)

if __name__ == '__main__':
    main()
