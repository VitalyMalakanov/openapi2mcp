"""
EN: This module provides the command-line interface (CLI) for openapi2mcp.
It uses Click to define commands for generating MCP server code from OpenAPI
specifications, checking the generated code, and displaying the tool's version.

RU: Этот модуль предоставляет интерфейс командной строки (CLI) для openapi2mcp.
Он использует Click для определения команд для генерации кода MCP-сервера
из спецификаций OpenAPI, проверки сгенерированного кода и отображения версии инструмента.
"""
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

VERSION_STRING = "openapi2mcp v1.0.0" # TODO: Centralize versioning, perhaps __version__. RU: TODO: Централизовать управление версиями, возможно, через __version__.

@click.group()
def main():
    """
    openapi2mcp - OpenAPI to MCP Server Code Generator

    Инструмент для генерации кода MCP-сервера из спецификаций OpenAPI.
    """
    pass

@main.command()
@click.option(
    "-i",
    "--input-file",
    required=True,
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    help="EN: Path to the OpenAPI specification file (JSON or YAML). RU: Путь к файлу спецификации OpenAPI (JSON или YAML).",
)
@click.option(
    "-o",
    "--output-file",
    required=True,
    type=click.Path(dir_okay=False, writable=True, path_type=Path),
    help="EN: Path to the output Python file for the generated MCP server. RU: Путь к выходному Python-файлу для сгенерированного MCP-сервера.",
)
@click.option(
    "-t",
    "--transport",
    type=click.Choice(["stdio", "google_pubsub"], case_sensitive=False),
    default="stdio",
    show_default=True,
    help="EN: The transport mechanism for the MCP server. RU: Транспортный механизм для MCP-сервера.",
)
@click.option(
    "--llms-txt-file",
    type=click.Path(dir_okay=False, writable=True, path_type=Path),
    help="EN: Optional: Path to generate an llms.txt file for language models. If not provided, uses output directory. RU: Необязательно: Путь для генерации файла llms.txt для языковых моделей. Если не указан, используется выходной каталог.",
    default=None,
)
@click.option(
    "--mount",
    "mount_path", # Use a different dest name if 'mount' conflicts
    default="",
    help="EN: Mount path for resources (e.g., '/myapi/v1'). RU: Путь монтирования для ресурсов (например, '/myapi/v1').",
    show_default=True,
)
def generate(input_file: Path, output_file: Path, transport: str, llms_txt_file: Optional[Path], mount_path: str):
    """
    Generates MCP server code from an OpenAPI specification.

    Генерирует код MCP-сервера из спецификации OpenAPI.
    """
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

    # EN: Determine output directory for llms.txt.
    # RU: Определяем выходной каталог для llms.txt.
    if llms_txt_file:
        # EN: If --llms-txt-file is provided, use its parent directory.
        # EN: The generator.generate_llms_txt method creates a file named "llms.txt" in the specified directory.
        # RU: Если указан --llms-txt-file, используем его родительский каталог.
        # RU: Метод generator.generate_llms_txt создает файл с именем "llms.txt" в указанном каталоге.
        output_dir_for_llms = llms_txt_file.parent
        # Example: --llms-txt-file /path/to/custom_name.txt -> output_dir_for_llms is /path/to/
        # llms.txt will be generated as /path/to/llms.txt
        # If --llms-txt-file is just "my_llms.txt" -> output_dir_for_llms is Path(".") (current directory)
        # llms.txt will be generated as ./llms.txt
    else:
        # EN: If --llms-txt-file is not provided, use the parent directory of the output_file.
        # RU: Если --llms-txt-file не указан, используем родительский каталог output_file.
        output_dir_for_llms = output_file.parent

    logger.info(f"Generating llms.txt in directory: {output_dir_for_llms}")
    if not generator.generate_llms_txt(str(output_dir_for_llms)): # generate_llms_txt expects a directory path
        logger.warning("llms.txt generation failed. Continuing without it.") # Non-fatal
    else:
        # EN: The actual path of the generated llms.txt will be output_dir_for_llms / "llms.txt"
        # RU: Фактический путь к сгенерированному llms.txt будет output_dir_for_llms / "llms.txt"
        logger.info(f"llms.txt generated successfully in {output_dir_for_llms / 'llms.txt'}")


@main.command()
@click.option(
    "--server-file",
    required=True,
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    help="EN: Path to the generated MCP server Python file to check. RU: Путь к сгенерированному Python-файлу MCP-сервера для проверки.",
)
def check(server_file: Path):
    """
    Checks the generated server code for basic validity.
    This includes Python syntax checks and heuristic regex checks for MCP patterns.

    Проверяет сгенерированный код сервера на базовую корректность.
    Включает проверку синтаксиса Python и эвристические проверки с помощью регулярных выражений на наличие шаблонов MCP.
    """
    logger.info(f"Checking generated server file: {server_file}")
    try:
        with open(server_file, "r") as f:
            code = f.read()
    except IOError as e:
        logger.error(f"Error reading server file {server_file}: {e}")
        sys.exit(1)

    # EN: 1. Try to compile the code to check for basic Python syntax errors.
    # RU: 1. Пытаемся скомпилировать код для проверки на базовые синтаксические ошибки Python.
    try:
        compile(code, str(server_file), "exec")
        logger.info("Code compilation successful.")
    except SyntaxError as e:
        logger.error(f"Syntax error in generated code: {e}")
        sys.exit(1)
    except Exception as e:
        logger.error(f"An unexpected error occurred during compilation: {e}", exc_info=True)
        sys.exit(1)

    # EN: 2. Perform heuristic regex checks for common MCP patterns.
    # EN: These are not foolproof but can catch common generation issues.
    # RU: 2. Выполняем эвристические проверки с помощью регулярных выражений на наличие общих шаблонов MCP.
    # RU: Они не являются абсолютно надежными, но могут выявить распространенные проблемы генерации.
    checks = {
        "Pydantic model definition": r"class\s+\w+\(BaseModel\):",
        "MCP Resource definition": r"@Server\.resource\(",
        "MCP Tool definition": r"@Server\.tool\(",
        "Main function definition": r"def\s+main\(\):", # Assuming a main function is generated for running the server
        "Server serve call": r"app\.serve\(", # Or similar, depending on the MCP framework used by the generator
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
        # EN: Not exiting with error for regex check failures, as they are heuristic and might produce false positives/negatives.
        # RU: Не выходим с ошибкой при сбоях проверок регулярными выражениями, так как они эвристические и могут давать ложные срабатывания.

@main.command()
def version():
    """
    Displays the version of openapi2mcp.

    Отображает версию openapi2mcp.
    """
    click.echo(VERSION_STRING)

if __name__ == "__main__":
    main()
