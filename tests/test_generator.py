import pytest
from openapi2mcp.generator import (
    oas_schema_to_python_type,
    generate_pydantic_models,
    _oas_type_to_pydantic_type_str # For testing this internal helper if needed, though testing public interface is primary
)

# --- Tests for oas_schema_to_python_type (used for function signatures) ---
def test_oas_schema_to_python_type_basic_types():
    assert oas_schema_to_python_type({"type": "string"}) == "str"
    assert oas_schema_to_python_type({"type": "integer"}) == "int"
    assert oas_schema_to_python_type({"type": "number"}) == "float"
    assert oas_schema_to_python_type({"type": "boolean"}) == "bool"
    assert oas_schema_to_python_type({}) == "Any" # Default fallback
    assert oas_schema_to_python_type({"type": "unknown"}) == "Any" # Unknown type

def test_oas_schema_to_python_type_ref():
    assert oas_schema_to_python_type({"$ref": "#/components/schemas/MyModel"}) == "MyModel"

def test_oas_schema_to_python_type_array_of_strings():
    schema = {"type": "array", "items": {"type": "string"}}
    assert oas_schema_to_python_type(schema) == "List[str]"

def test_oas_schema_to_python_type_array_of_ref():
    schema = {"type": "array", "items": {"$ref": "#/components/schemas/MyItem"}}
    assert oas_schema_to_python_type(schema) == "List[MyItem]"

def test_oas_schema_to_python_type_array_of_any():
    schema_no_items = {"type": "array"} # No items defined
    assert oas_schema_to_python_type(schema_no_items) == "List[Any]"
    schema_empty_items = {"type": "array", "items": {}} # Empty items schema
    assert oas_schema_to_python_type(schema_empty_items) == "List[Any]"

def test_oas_schema_to_python_type_object():
    schema = {"type": "object", "properties": {"name": {"type": "string"}}}
    # For function signatures, anonymous objects are typically Dict[str, Any] or Any
    assert oas_schema_to_python_type(schema) == "Dict[str, Any]"
    schema_no_props = {"type": "object"}
    assert oas_schema_to_python_type(schema_no_props) == "Dict[str, Any]"


# --- Tests for _oas_type_to_pydantic_type_str (used for Pydantic model fields) ---
# These might be similar to above, but this helper is specifically for Pydantic field generation
def test_internal_pydantic_type_str_basic():
    assert _oas_type_to_pydantic_type_str({"type": "string"}) == "str"
    assert _oas_type_to_pydantic_type_str({"type": "integer"}) == "int"
    # ... etc. for other basic types

def test_internal_pydantic_type_str_ref():
    assert _oas_type_to_pydantic_type_str({"$ref": "#/components/schemas/MyModel"}) == "MyModel"

def test_internal_pydantic_type_str_array_of_primitive():
    assert _oas_type_to_pydantic_type_str({"type": "array", "items": {"type": "integer"}}) == "List[int]"

def test_internal_pydantic_type_str_array_of_ref():
    assert _oas_type_to_pydantic_type_str({"type": "array", "items": {"$ref": "#/components/schemas/Other"}}) == "List[Other]"


# --- Tests for generate_pydantic_models ---
def test_generate_single_model_no_props():
    schemas = {"TestModel": {"type": "object"}}
    expected_code = (
        "class TestModel(BaseModel):\n"
            "    pass\n" # Model class ends, then \n from joiner if it's the only model
            "\n\n" # Expected: one \n after class, then \n before # Resolve, then \n after model_rebuild
        "# Resolve forward references\n"
        "TestModel.model_rebuild()\n\n"
    )
    # generate_pydantic_models now returns only model code, no imports
    generated_code = generate_pydantic_models(schemas)
    assert generated_code.strip() == expected_code.strip()

def test_generate_single_model_simple_props():
    schemas = {
        "TestModel": {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "age": {"type": "integer"}
            }
        }
    }
    # Expected: fields are optional by default
    expected_code = (
        "class TestModel(BaseModel):\n"
        "    name: str | None = None\n"
        "    age: int | None = None\n"
            "\n\n"
        "# Resolve forward references\n"
        "TestModel.model_rebuild()\n\n"
    )
    generated_code = generate_pydantic_models(schemas)
    assert generated_code.strip() == expected_code.strip()

def test_generate_model_with_required_field():
    schemas = {
        "UserModel": {
            "type": "object",
            "required": ["id"],
            "properties": {
                "id": {"type": "integer"},
                "username": {"type": "string"}
            }
        }
    }
    expected_code = (
        "class UserModel(BaseModel):\n"
        "    id: int\n"
        "    username: str | None = None\n"
            "\n\n"
        "# Resolve forward references\n"
        "UserModel.model_rebuild()\n\n"
    )
    generated_code = generate_pydantic_models(schemas)
    assert generated_code.strip() == expected_code.strip()

def test_generate_model_with_ref_field():
    schemas = {
        "Order": {
            "type": "object",
            "properties": {
                "order_id": {"type": "string"},
                "customer": {"$ref": "#/components/schemas/Customer"}
            }
        },
        # Customer is not defined here, but due to `from __future__ import annotations`
        # and Pydantic's handling of forward refs (especially with model_rebuild),
        # this should generate "customer: Customer | None = None"
    }
    expected_code = (
        "class Order(BaseModel):\n"
        "    order_id: str | None = None\n"
        "    customer: Customer | None = None\n" # Customer is a string type hint
            "\n\n"
        "# Resolve forward references\n"
        "Order.model_rebuild()\n\n"
    )
    generated_code = generate_pydantic_models(schemas)
    assert generated_code.strip() == expected_code.strip()

def test_generate_model_with_list_of_ref():
    schemas = {
        "Playlist": {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "songs": {
                    "type": "array",
                    "items": {"$ref": "#/components/schemas/Song"}
                }
            }
        }
    }
    expected_code = (
        "class Playlist(BaseModel):\n"
        "    name: str | None = None\n"
        "    songs: List[Song] | None = None\n" # Song is a string type hint
            "\n\n"
        "# Resolve forward references\n"
        "Playlist.model_rebuild()\n\n"
    )
    generated_code = generate_pydantic_models(schemas)
    # Note: generate_pydantic_models itself does not add "from typing import List" anymore.
    # This is handled by generate_mcp_server_code.
    # So, the raw output of generate_pydantic_models is tested here.
    assert generated_code.strip() == expected_code.strip()

def test_no_models_generated_if_schemas_empty():
    assert generate_pydantic_models({}) == ""
    assert generate_pydantic_models({"NotAnObject": {"type": "string"}}) == "" # Skips non-object schemas

def test_model_rebuild_calls_generated_correctly():
    schemas = {
        "ModelA": {"type": "object"},
        "ModelB": {"type": "object", "properties": {"prop1": {"type": "integer"}}}
    }
    expected_code = (
        "class ModelA(BaseModel):\n"
        "    pass\n"
        "\n"
        "class ModelB(BaseModel):\n"
        "    prop1: int | None = None\n"
            "\n\n" # Expecting two newlines after the last model property list before # Resolve
        "# Resolve forward references\n"
        "ModelA.model_rebuild()\n"
        "ModelB.model_rebuild()\n\n"
    )
    generated_code = generate_pydantic_models(schemas)
    assert generated_code.strip() == expected_code.strip()
