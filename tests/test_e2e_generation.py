import subprocess
import sys
import tempfile
from pathlib import Path
import shutil
import pytest

# Determine project root to construct paths to example files
PROJECT_ROOT = Path(__file__).parent.parent
EXAMPLES_DIR = PROJECT_ROOT / "examples"
EXAMPLE_OPENAPI_YAML = EXAMPLES_DIR / "example_openapi.yaml"
SPEC_WITH_TOOLS_YAML = PROJECT_ROOT / "tests" / "fixtures" / "spec_with_tools.yaml"

# This is the one with /pets, /pets/{petId}, POST, PUT, DELETE etc.

# Ensure the example spec file exists
@pytest.fixture(scope="module", autouse=True)
def check_example_spec_exists():
    if not EXAMPLE_OPENAPI_YAML.exists():
        pytest.fail(f"Example OpenAPI spec not found: {EXAMPLE_OPENAPI_YAML}")
    if not SPEC_WITH_TOOLS_YAML.exists():
        pytest.fail(f"Spec with tools not found: {SPEC_WITH_TOOLS_YAML}")

def test_generated_server_passes_fastmcp_check():
    """
    Tests that the generated server code from a known good OpenAPI spec
    passes the `fastmcp --check` validation.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        temp_output_file = Path(tmpdir) / "generated_server.py"

        cmd_generate = [
            sys.executable, "-m", "openapi2mcp.cli", "generate",
            "-i", str(EXAMPLE_OPENAPI_YAML),
            "-o", str(temp_output_file),
            "--transport", "stdio" # Transport choice shouldn't affect --check validity
        ]

        # Generate the server file
        result_generate = subprocess.run(cmd_generate, capture_output=True, text=True, check=False) # check=False to inspect output

        assert result_generate.returncode == 0, \
            f"openapi2mcp generate failed with exit code {result_generate.returncode}.\n" \
            f"Stderr: {result_generate.stderr}\nStdout: {result_generate.stdout}"

        assert temp_output_file.exists(), \
            f"Generated server file was not created: {temp_output_file}"

        # Basic Python syntax check
        cmd_compile_check = [sys.executable, "-m", "py_compile", str(temp_output_file)]

        result_compile_check = subprocess.run(cmd_compile_check, capture_output=True, text=True, check=False)

        assert result_compile_check.returncode == 0, \
            f"Python syntax check failed for {temp_output_file}.\n" \
            f"Stderr: {result_compile_check.stderr}\nStdout: {result_compile_check.stdout}"

        # fastmcp --check functionality is not available as initially assumed.
        # The tool does not have a simple check/lint command.
        # Python syntax check (py_compile) is performed above.

def test_generated_server_with_http_transport_passes_fastmcp_check():
    """
    Tests specifically with HTTP transport as it involves more complex setup (uvicorn).
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        temp_output_file = Path(tmpdir) / "generated_server_http.py"

        cmd_generate = [
            sys.executable, "-m", "openapi2mcp.cli", "generate",
            "-i", str(EXAMPLE_OPENAPI_YAML),
            "-o", str(temp_output_file),
            "--transport", "http"
        ]

        result_generate = subprocess.run(cmd_generate, capture_output=True, text=True, check=False)

        assert result_generate.returncode == 0, \
            f"openapi2mcp generate (http) failed with exit code {result_generate.returncode}.\n" \
            f"Stderr: {result_generate.stderr}\nStdout: {result_generate.stdout}"

        assert temp_output_file.exists(), \
            f"Generated server file (http) was not created: {temp_output_file}"

        # Basic Python syntax check
        cmd_compile_check = [sys.executable, "-m", "py_compile", str(temp_output_file)]
        result_compile_check = subprocess.run(cmd_compile_check, capture_output=True, text=True, check=False)

        assert result_compile_check.returncode == 0, \
            f"Python syntax check failed for {temp_output_file} (http).\n" \
            f"Stderr: {result_compile_check.stderr}\nStdout: {result_compile_check.stdout}"

        # fastmcp --check functionality is not available as initially assumed.
        # The tool does not have a simple check/lint command.
        # Python syntax check (py_compile) is performed above.

# It might also be useful to have a test for llms.txt generation,
# but the primary goal here is server code validity.
def test_llms_txt_generation(check_example_spec_exists):
    """
    Tests the generation of llms.txt files, both with a custom name
    and with the default naming convention.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        # Test with custom llms.txt file name using spec_with_tools.yaml
        temp_server_file_custom = Path(tmpdir) / "server_custom_llms.py"
        temp_llms_txt_file_custom = Path(tmpdir) / "llms_custom_tools.txt"

        cmd_generate_custom = [
            sys.executable, "-m", "openapi2mcp.cli", "generate",
            "-i", str(SPEC_WITH_TOOLS_YAML),  # Use the new spec
            "-o", str(temp_server_file_custom),
            "--llms-txt-file", str(temp_llms_txt_file_custom)
        ]
        result_generate_custom = subprocess.run(cmd_generate_custom, capture_output=True, text=True, check=False)

        assert result_generate_custom.returncode == 0, \
            f"openapi2mcp generate for custom llms.txt (with tools spec) failed with exit code {result_generate_custom.returncode}.\n" \
            f"Stderr: {result_generate_custom.stderr}\nStdout: {result_generate_custom.stdout}"

        assert temp_llms_txt_file_custom.exists(), \
            f"llms.txt file with custom name was not created when using spec with tools: {temp_llms_txt_file_custom}"

        content_custom = temp_llms_txt_file_custom.read_text()
        assert content_custom.strip() != "", \
            f"llms.txt file with custom name is empty when using spec with tools: {temp_llms_txt_file_custom}"
        assert "create_item" in content_custom, \
            f"Expected 'create_item' not found in custom llms.txt: {temp_llms_txt_file_custom}\nContent:\n{content_custom}"
        assert "update_item" in content_custom, \
            f"Expected 'update_item' not found in custom llms.txt: {temp_llms_txt_file_custom}\nContent:\n{content_custom}"

        # Test with default llms.txt file name using spec_with_tools.yaml
        temp_server_file_default = Path(tmpdir) / "server_default_llms.py"
        expected_default_llms_txt_path = Path(str(temp_server_file_default) + ".llms.txt")

        cmd_generate_default = [
            sys.executable, "-m", "openapi2mcp.cli", "generate",
            "-i", str(SPEC_WITH_TOOLS_YAML),  # Use the new spec
            "-o", str(temp_server_file_default)  # No --llms-txt-file option
        ]
        result_generate_default = subprocess.run(cmd_generate_default, capture_output=True, text=True, check=False)

        assert result_generate_default.returncode == 0, \
            f"openapi2mcp generate for default llms.txt (with tools spec) failed with exit code {result_generate_default.returncode}.\n" \
            f"Stderr: {result_generate_default.stderr}\nStdout: {result_generate_default.stdout}"

        assert expected_default_llms_txt_path.exists(), \
            f"Default llms.txt file was not created at expected path when using spec with tools: {expected_default_llms_txt_path}"

        content_default = expected_default_llms_txt_path.read_text()
        assert content_default.strip() != "", \
            f"Default llms.txt file is empty when using spec with tools: {expected_default_llms_txt_path}"
        assert "create_item" in content_default, \
            f"Expected 'create_item' not found in default llms.txt: {expected_default_llms_txt_path}\nContent:\n{content_default}"
        assert "update_item" in content_default, \
            f"Expected 'update_item' not found in default llms.txt: {expected_default_llms_txt_path}\nContent:\n{content_default}"
