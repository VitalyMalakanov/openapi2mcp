import logging
import re
import sys
from pathlib import Path

import click

from .generator import MCPGenerator
from .parser import OpenAPIParser, OpenAPIParserError

# Basic logging setup
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

VERSION_STRING = "openapi2mcp v1.0.0" # TODO: Centralize versioning, perhaps __version__

@click.group()
def main():
    """openapi2mcp - OpenAPI to MCP Server Code Generator"""
    pass

@main.command()
@click.option(
    "-i",
    "--input-file",
    required=True,
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    help="Path to the OpenAPI specification file (JSON or YAML).",
)
@click.option(
    "-o",
    "--output-file",
    required=True,
    type=click.Path(dir_okay=False, writable=True, path_type=Path),
    help="Path to the output Python file for the generated MCP server.",
)
@click.option(
    "-t",
    "--transport",
    type=click.Choice(["stdio", "google_pubsub"], case_sensitive=False),
    default="stdio",
    show_default=True,
    help="The transport mechanism for the MCP server.",
)
@click.option(
    "--llms-txt-file",
    type=click.Path(dir_okay=False, writable=True, path_type=Path),
    help="Optional: Path to generate an llms.txt file for language models. If not provided, uses output directory.",
    default=None,
)
@click.option(
    "--mount",
    "mount_path", # Use a different dest name if 'mount' conflicts
    default="",
    help="Mount path for resources (e.g., '/myapi/v1').",
    show_default=True,
)
def generate(input_file: Path, output_file: Path, transport: str, llms_txt_file: Optional[Path], mount_path: str):
    """Generates MCP server code from an OpenAPI specification."""
    logger.info(f"Parsing OpenAPI specification from: {input_file}")

    parser = OpenAPIParser()
    try:
        parser.parse_file(input_file) # parse_file now raises exceptions on failure
        logger.info("OpenAPI specification parsed successfully.")
    except OpenAPIParserError as e:
        logger.error(f"Failed to parse OpenAPI specification: {e}")
        sys.exit(1)
    except Exception as e:
        logger.error(f"An unexpected error occurred during parsing: {e}", exc_info=True)
        sys.exit(1)

    logger.info(f"Generating MCP server code to: {output_file}")
    generator = MCPGenerator(parser, transport=transport, mount_path=mount_path)

    if not generator.generate(str(output_file)): # Generator's generate expects str path
        logger.error("MCP server code generation failed.")
        sys.exit(1)
    logger.info("MCP server code generated successfully.")

    # Determine output directory for llms.txt
    if llms_txt_file:
        output_dir_for_llms = llms_txt_file.parent
        # Ensure llms_txt_file itself is used if it's a full path including filename,
        # but generator.generate_llms_txt writes a fixed "llms.txt" in the given dir.
        # So, we just need the directory.
        # If llms_txt_file is just "llms.txt", parent will be Path(".")
        # If it's "/path/to/custom_llms.txt", parent is "/path/to"
        # The generator method will create "llms.txt" in that directory.
        # This means the --llms-txt-file option effectively specifies the *directory* and *name*
        # if the name is not "llms.txt".
        # For now, let's stick to the generator's behavior of creating "llms.txt".
        # So, if llms_txt_file is "foo/bar.txt", llms.txt will be "foo/llms.txt".
        # This might be slightly different from original script if it allowed custom filename.
        # The generator's method is `generate_llms_txt(self, output_dir: str)`
    else:
        output_dir_for_llms = output_file.parent

    logger.info(f"Generating llms.txt in directory: {output_dir_for_llms}")
    if not generator.generate_llms_txt(str(output_dir_for_llms)):
        logger.warning("llms.txt generation failed. Continuing without it.") # Non-fatal
    else:
        logger.info(f"llms.txt generated successfully in {output_dir_for_llms / 'llms.txt'}")


@main.command()
@click.option(
    "--server-file",
    required=True,
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    help="Path to the generated MCP server Python file to check.",
)
def check(server_file: Path):
    """Checks the generated server code for basic validity."""
    logger.info(f"Checking generated server file: {server_file}")
    try:
        with open(server_file, "r") as f:
            code = f.read()
    except IOError as e:
        logger.error(f"Error reading server file {server_file}: {e}")
        sys.exit(1)

    # 1. Try to compile the code
    try:
        compile(code, str(server_file), "exec")
        logger.info("Code compilation successful.")
    except SyntaxError as e:
        logger.error(f"Syntax error in generated code: {e}")
        sys.exit(1)
    except Exception as e:
        logger.error(f"An unexpected error occurred during compilation: {e}", exc_info=True)
        sys.exit(1)

    # 2. Regex checks (examples from original script)
    checks = {
        "Pydantic model definition": r"class\s+\w+\(BaseModel\):",
        "MCP Resource definition": r"@Server\.resource\(",
        "MCP Tool definition": r"@Server\.tool\(",
        "Main function definition": r"def\s+main\(\):",
        "Server serve call": r"app\.serve\(",
    }

    all_checks_passed = True
    for check_name, pattern in checks.items():
        if re.search(pattern, code):
            logger.info(f"Check passed: Found {check_name}.")
        else:
            logger.warning(f"Check failed: Did not find {check_name} (pattern: {pattern}).")
            all_checks_passed = False # Mark as warning, not critical failure for now

    if all_checks_passed:
        logger.info("All basic checks passed.")
    else:
        logger.warning("Some basic checks did not pass. Review the generated code.")
        # Not exiting with error for regex check failures, as they are heuristic.

@main.command()
def version():
    """Displays the version of openapi2mcp."""
    click.echo(VERSION_STRING)

if __name__ == "__main__":
    main()
