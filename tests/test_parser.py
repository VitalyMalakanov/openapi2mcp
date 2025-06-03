import pytest
import yaml # For yaml.YAMLError if OpenAPIParserError wraps it directly
from pathlib import Path
from openapi2mcp.parser import load_openapi_spec, OpenAPIParserError

# Define fixture path relative to the test file
FIXTURE_DIR = Path(__file__).parent / "fixtures"

def test_load_valid_spec(tmp_path):
    # Create a valid spec file in tmp_path for isolation, or use fixture file
    # Using the fixture file directly for this test:
    valid_spec_path = FIXTURE_DIR / "valid_spec.yaml"
    spec = load_openapi_spec(str(valid_spec_path))
    assert isinstance(spec, dict)
    assert "info" in spec
    assert "paths" in spec
    assert "components" in spec
    assert spec["openapi"] == "3.0.1" # As per the file

def test_load_nonexistent_file():
    with pytest.raises(FileNotFoundError):
        load_openapi_spec("nonexistent_file.yaml")

def test_load_invalid_yaml_syntax():
    invalid_yaml_path = FIXTURE_DIR / "invalid_yaml.yaml"
    # OpenAPIParserError should wrap yaml.YAMLError or be raised for parsing issues
    with pytest.raises(OpenAPIParserError) as e_info:
        load_openapi_spec(str(invalid_yaml_path))
    # Optionally, check if the error message contains specifics about YAML parsing
    assert "Error parsing YAML/JSON file" in str(e_info.value)


def test_load_missing_openapi_version(tmp_path):
    content = """
info:
  title: Missing OpenAPI Version
  version: 1.0.0
paths: {}
"""
    p = tmp_path / "missing_openapi.yaml"
    p.write_text(content)
    with pytest.raises(OpenAPIParserError, match="Invalid OpenAPI version: 'None'"):
        load_openapi_spec(str(p))

def test_load_unsupported_openapi_version(tmp_path):
    content = """
openapi: 2.0.0
info:
  title: Unsupported Version
  version: 1.0.0
paths: {}
"""
    p = tmp_path / "unsupported_openapi.yaml"
    p.write_text(content)
    with pytest.raises(OpenAPIParserError, match="Only OpenAPI 3.x is supported"):
        load_openapi_spec(str(p))

def test_load_missing_info_section(tmp_path):
    content = """
openapi: 3.0.0
# info section is missing
paths: {}
"""
    p = tmp_path / "missing_info.yaml"
    p.write_text(content)
    with pytest.raises(OpenAPIParserError, match="Missing 'info' section"):
        load_openapi_spec(str(p))

def test_load_missing_info_title(tmp_path):
    content = """
openapi: 3.0.0
info:
  version: 1.0.0 # title is missing
paths: {}
"""
    p = tmp_path / "missing_info_title.yaml"
    p.write_text(content)
    with pytest.raises(OpenAPIParserError, match="'info' section must contain 'title' and 'version'"):
        load_openapi_spec(str(p))

def test_load_missing_info_version(tmp_path):
    content = """
openapi: 3.0.0
info:
  title: Test API # version is missing
paths: {}
"""
    p = tmp_path / "missing_info_version.yaml"
    p.write_text(content)
    with pytest.raises(OpenAPIParserError, match="'info' section must contain 'title' and 'version'"):
        load_openapi_spec(str(p))

def test_load_missing_paths_section(tmp_path):
    content = """
openapi: 3.0.0
info:
  title: Missing Paths
  version: 1.0.0
# paths section is missing
"""
    p = tmp_path / "missing_paths.yaml"
    p.write_text(content)
    with pytest.raises(OpenAPIParserError, match="Missing 'paths' section"):
        load_openapi_spec(str(p))

def test_load_spec_not_a_dictionary(tmp_path):
    content = "[]" # YAML representing a list, not a dictionary
    p = tmp_path / "list_not_dict.yaml"
    p.write_text(content)
    with pytest.raises(OpenAPIParserError, match="The document root is not a dictionary"):
        load_openapi_spec(str(p))

def test_info_not_a_dictionary(tmp_path):
    content = """
openapi: 3.0.0
info: "This should be a dictionary"
paths: {}
"""
    p = tmp_path / "info_not_dict.yaml"
    p.write_text(content)
    with pytest.raises(OpenAPIParserError, match="'info' section must be a dictionary"):
        load_openapi_spec(str(p))

def test_paths_not_a_dictionary(tmp_path):
    content = """
openapi: 3.0.0
info:
  title: Test
  version: 1.0
paths: "This should be a dictionary"
"""
    p = tmp_path / "paths_not_dict.yaml"
    p.write_text(content)
    with pytest.raises(OpenAPIParserError, match="'paths' section must be a dictionary"):
        load_openapi_spec(str(p))
