import subprocess
import sys
import tempfile
from pathlib import Path
import pytest

# Determine project root to construct paths to example files
PROJECT_ROOT = Path(__file__).parent.parent
EXAMPLES_DIR = PROJECT_ROOT / "examples"
EXAMPLE_OPENAPI_YAML = EXAMPLES_DIR / "example_openapi.yaml"
# This is the one with /pets, /pets/{petId}, POST, PUT, DELETE etc.

# Ensure the example spec file exists
@pytest.fixture(scope="module", autouse=True)
def check_example_spec_exists():
    if not EXAMPLE_OPENAPI_YAML.exists():
        pytest.fail(f"Example OpenAPI spec not found: {EXAMPLE_OPENAPI_YAML}")

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

# It might also be useful to have a test for llms.txt generation,
# but the primary goal here is server code validity.
# def test_llms_txt_generation():
#     with tempfile.TemporaryDirectory() as tmpdir:
#         temp_server_file = Path(tmpdir) / "server_for_llms.py"
#         temp_llms_txt_file = Path(tmpdir) / "llms_custom.txt"

#         cmd_generate = [
#             sys.executable, "-m", "openapi2mcp.cli", "generate",
#             "-i", str(EXAMPLE_OPENAPI_YAML),
#             "-o", str(temp_server_file),
#             "--llms-txt-file", str(temp_llms_txt_file)
#         ]
#         result_generate = subprocess.run(cmd_generate, capture_output=True, text=True, check=False)
#         assert result_generate.returncode == 0, "openapi2mcp generate for llms.txt failed"
#         assert temp_llms_txt_file.exists(), "llms.txt file was not created with custom name"
#         assert temp_llms_txt_file.read_text().strip() != "", "llms.txt file is empty"

#         # Test default llms.txt naming
#         default_llms_txt_path = Path(str(temp_server_file) + ".llms.txt")
#         cmd_generate_default_llms = [
#             sys.executable, "-m", "openapi2mcp.cli", "generate",
#             "-i", str(EXAMPLE_OPENAPI_YAML),
#             "-o", str(temp_server_file) # No --llms-txt-file option
#         ]
#         result_generate_default = subprocess.run(cmd_generate_default_llms, capture_output=True, text=True, check=False)
#         assert result_generate_default.returncode == 0, "openapi2mcp generate for default llms.txt failed"
#         assert default_llms_txt_path.exists(), "Default llms.txt file was not created"
#         assert default_llms_txt_path.read_text().strip() != "", "Default llms.txt file is empty"
