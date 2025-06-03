import yaml
from pathlib import Path

class OpenAPIParserError(ValueError):
    """Custom error for OpenAPI parsing issues."""
    pass

def load_openapi_spec(filepath: str) -> dict:
    """
    Loads an OpenAPI 3.x specification from a YAML or JSON file.

    Args:
        filepath: Path to the OpenAPI specification file.

    Returns:
        A dictionary representing the OpenAPI specification.

    Raises:
        OpenAPIParserError: If the file is not valid OpenAPI 3.x or cannot be parsed.
        FileNotFoundError: If the filepath does not exist.
    """
    p = Path(filepath)
    if not p.is_file(): # Check if it's a file and exists
        raise FileNotFoundError(f"File not found or is not a file: {filepath}")

    try:
        with open(p, 'r', encoding='utf-8') as f:
            spec = yaml.safe_load(f)
    except yaml.YAMLError as e:
        raise OpenAPIParserError(f"Error parsing YAML/JSON file: {e}")
    except Exception as e:
        raise OpenAPIParserError(f"An unexpected error occurred while reading the file: {e}")


    if not isinstance(spec, dict):
        raise OpenAPIParserError("Invalid OpenAPI spec: The document root is not a dictionary.")

    openapi_version = spec.get("openapi")
    if not openapi_version or not str(openapi_version).startswith("3."):
        raise OpenAPIParserError(
            f"Invalid OpenAPI version: '{openapi_version}'. Only OpenAPI 3.x is supported."
        )

    if "info" not in spec:
        raise OpenAPIParserError("Invalid OpenAPI spec: Missing 'info' section.")
    if not isinstance(spec["info"], dict):
        raise OpenAPIParserError("Invalid OpenAPI spec: 'info' section must be a dictionary.")
    if "title" not in spec["info"] or "version" not in spec["info"]:
        raise OpenAPIParserError("Invalid OpenAPI spec: 'info' section must contain 'title' and 'version'.")


    if "paths" not in spec:
        raise OpenAPIParserError("Invalid OpenAPI spec: Missing 'paths' section.")
    if not isinstance(spec["paths"], dict):
        raise OpenAPIParserError("Invalid OpenAPI spec: 'paths' section must be a dictionary.")

    # 'components' and 'components.schemas' are optional, so we don't strictly check them here.
    # They will be checked when accessed.

    return spec
