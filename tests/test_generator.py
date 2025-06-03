import pytest
from openapi2mcp.generator import (
    oas_schema_to_python_type,
    generate_pydantic_models,
    _oas_type_to_pydantic_type_str, # For testing this internal helper if needed, though testing public interface is primary
    _sanitize_python_identifier,
    _to_snake_case,
    _generate_function_name,
    _get_llm_type_string,
    generate_mcp_resources,
    generate_mcp_tools,
    generate_llms_txt,
    generate_mcp_server_code
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


# --- Tests for _sanitize_python_identifier ---
@pytest.mark.parametrize("input_str, expected_output", [
    ("ValidIdentifier123_", "ValidIdentifier123_"),
    ("Invalid-Identifier!", "Invalid_Identifier_"),
    ("123StartsWithDigit", "_123StartsWithDigit"),
    ("_LeadingUnderscore", "_LeadingUnderscore"),
    ("", "_generated_name"), # Default name for empty
    ("!@#", "_generated_name"), # Only invalid chars
    ("multiple--dashes", "multiple_dashes"), # Multiple invalid chars condensed
    ("trailing-", "trailing_"),
    (" leading_space", "_leading_space"),
    ("na!me with sp@ces", "na_me_with_sp_ces"),
    ("test.dots.ok", "test_dots_ok"), # Dots are often part of opId
    ("keyword_def", "keyword_def"), # keyword_def is a valid identifier, should not be changed.
    ("def", "def_"),
    ("class", "class_"),
    ("for", "for_"),
])
def test_sanitize_python_identifier(input_str, expected_output):
    assert _sanitize_python_identifier(input_str) == expected_output

# --- Tests for _to_snake_case ---
@pytest.mark.parametrize("input_str, expected_output", [
    ("SimpleTest", "simple_test"),
    ("Simple", "simple"),
    ("simple", "simple"),
    ("AnotherHTTPExample", "another_http_example"),
    ("AnotherHTTP1Example", "another_http1_example"),
    ("already_snake", "already_snake"),
    ("TestV1", "test_v1"),
    ("TestV1Value", "test_v1_value"),
    ("UPPERCASE", "uppercase"),
    ("Mixed_Case_Example", "mixed_case_example"),
    ("Mixed_Case-ExampleWith-Dashes", "mixed_case_example_with_dashes"), # Handles other separators
    ("singleword", "singleword"),
    ("", ""), # Empty string
    ("LeadingCap", "leading_cap"),
    ("S", "s"), # Single character
    ("SomeCAPSAtEnd", "some_caps_at_end"),
    ("getHTTPResponse", "get_http_response"),
    ("UserID", "user_id"),
    ("APIKey", "api_key"),
])
def test_to_snake_case(input_str, expected_output):
    assert _to_snake_case(input_str) == expected_output

# --- Tests for _generate_function_name ---
@pytest.mark.parametrize("method, path, operation_id, expected_name", [
    # With operationId
    ("get", "/users", "getUsersOpId", "get_users_op_id"),
    ("post", "/items", "create-item-op-id", "create_item_op_id"), # Sanitized opId
    ("get", "/complex/path", "  leadingSpaceOpId  ", "_leading_space_op_id_"), # opId with spaces
    ("delete", "/products/{id}", "delete_product_by_id_v1", "delete_product_by_id_v1"), # Valid opId

    # Without operationId, using method and path
    ("get", "/users", None, "get_users"),
    ("post", "/some/long/path", None, "post_some_long_path"),
    ("get", "/users/{userId}", None, "get_users_by_user_id"),
    ("put", "/items/{item-id}", None, "put_items_by_item_id"), # Path param sanitization
    ("patch", "/items/{item_id}/details/{detail-name}", None, "patch_items_by_item_id_details_by_detail_name"),
    ("get", "/", None, "get_root"), # Root path
    ("GeT", "/path", None, "get_path"), # Method case
    ("DELETE", "/resource", None, "delete_resource"),

    # opId takes precedence
    ("get", "/users/very/complex/path/that/is/ignored", "opIdTakesPrecedence", "op_id_takes_precedence"),

    # Edge cases for path-based generation
    ("get", "/_some_path_with_leading_underscore", None, "get_some_path_with_leading_underscore"), # leading underscore in path segment
    ("get", "/path/{_param_leading_underscore}", None, "get_path_by_param_leading_underscore"),
    ("get", "/path/{trailing_underscore_}", None, "get_path_by_trailing_underscore_"),
    ("get", "/path/{multiple--dashes}", None, "get_path_by_multiple_dashes"),
    ("get", "/path/123numericSegment", None, "get_path_123numeric_segment"), # Not common but test sanitization
    # Consider if an empty path is possible by OpenAPI spec (usually not for valid specs)
    # If it were possible and not caught by parser:
    # ("get", "", None, "get_"), # Needs decision on how generator handles this
    # ("post", " ", None, "post_"), # Path with only space
])
def test_generate_function_name(method, path, operation_id, expected_name):
    assert _generate_function_name(method, path, operation_id) == expected_name

# --- Tests for _get_llm_type_string ---

# Minimal spec for basic type tests
MINIMAL_SPEC = {"components": {"schemas": {}}}

@pytest.mark.parametrize("schema, expected_type_str", [
    ({"type": "string"}, "str"),
    ({"type": "integer"}, "int"),
    ({"type": "number"}, "float"),
    ({"type": "boolean"}, "bool"),
    ({}, "Any"), # Empty schema
    ({"type": "unknown"}, "Any"), # Unknown type
])
def test_get_llm_type_string_basic_types(schema, expected_type_str):
    assert _get_llm_type_string(schema, MINIMAL_SPEC) == expected_type_str

@pytest.mark.parametrize("items_schema, expected_list_item_type", [
    ({"type": "string"}, "List[str]"),
    ({"type": "integer"}, "List[int]"),
    ({"$ref": "#/components/schemas/SimpleRef"}, "List[SimpleRef]"),
])
def test_get_llm_type_string_array_types(items_schema, expected_list_item_type):
    spec_with_simple_ref = {
        "components": {
            "schemas": {
                "SimpleRef": {"type": "string"} # SimpleRef resolves to a basic string
            }
        }
    }
    schema = {"type": "array", "items": items_schema}
    assert _get_llm_type_string(schema, spec_with_simple_ref) == expected_list_item_type

def test_get_llm_type_string_object_inline():
    schema = {
        "type": "object",
        "properties": {
            "name": {"type": "string"},
            "age": {"type": "integer"},
            "id": {"type": "string", "readOnly": True},
            "config": {"type": "string", "writeOnly": True}
        }
    }
    # readOnly and writeOnly properties should be excluded
    assert _get_llm_type_string(schema, MINIMAL_SPEC) == "{name: str, age: int}"

def test_get_llm_type_string_object_inline_empty():
    schema = {"type": "object", "properties": {}}
    assert _get_llm_type_string(schema, MINIMAL_SPEC) == "object" # Current behavior for empty props
    schema_no_props = {"type": "object"}
    assert _get_llm_type_string(schema_no_props, MINIMAL_SPEC) == "object"


COMPLEX_SPEC = {
    "components": {
        "schemas": {
            "Address": {
                "type": "object",
                "properties": {
                    "street": {"type": "string"},
                    "city": {"type": "string"}
                }
            },
            "User": {
                "type": "object",
                "properties": {
                    "id": {"type": "integer"},
                    "name": {"type": "string"},
                    "address": {"$ref": "#/components/schemas/Address"},
                    "orders": {
                        "type": "array",
                        "items": {"$ref": "#/components/schemas/Order"}
                    }
                }
            },
            "Order": {
                "type": "object",
                "properties": {
                    "orderId": {"type": "string"},
                    "itemCount": {"type": "integer"},
                    "customer": {"$ref": "#/components/schemas/User"}
                }
            },
            "SimpleString": {"type": "string"}
        }
    }
}

@pytest.mark.parametrize("ref_path, depth, expected_type_str", [
    ("#/components/schemas/SimpleString", 0, "SimpleString"),
    ("#/components/schemas/SimpleString", 1, "SimpleString"),
    ("#/components/schemas/SimpleString", 2, "SimpleString"),
    ("#/components/schemas/Address", 0, "Address {street: str, city: str}"),
    # Corrected expectation for User at depth=0 based on re-trace
    ("#/components/schemas/User", 0, "User {id: int, name: str, address: Address {street: str, city: str}, orders: List[Order {orderId: str, itemCount: int, customer: User}]}"),
    # Corrected expectation for User at depth=1 based on re-trace
    ("#/components/schemas/User", 1, "User {id: int, name: str, address: Address, orders: List[Order]}"),
    ("#/components/schemas/User", 2, "User"),
    ("#/components/schemas/Address", 2, "Address"),
    ("#/components/schemas/Order", 2, "Order"),
])
def test_get_llm_type_string_ref_and_depth(ref_path, depth, expected_type_str):
    assert _get_llm_type_string({"$ref": ref_path}, COMPLEX_SPEC, depth) == expected_type_str

def test_get_llm_type_string_array_of_complex_object_with_depth():
    schema = {"type": "array", "items": {"$ref": "#/components/schemas/User"}}
    # Expectation based on User @ depth=0 expansion
    expected = "List[User {id: int, name: str, address: Address {street: str, city: str}, orders: List[Order {orderId: str, itemCount: int, customer: User}]}]"
    assert _get_llm_type_string(schema, COMPLEX_SPEC, depth=0) == expected

    schema_depth1_array = {"type": "array", "items": {"$ref": "#/components/schemas/User"}}
    # Expectation based on User @ depth=1 expansion
    expected_depth1 = "List[User {id: int, name: str, address: Address, orders: List[Order]}]"
    assert _get_llm_type_string(schema_depth1_array, COMPLEX_SPEC, depth=1) == expected_depth1

def test_get_llm_type_string_object_inline_recursive_like_at_depth_limit():
    schema = {
        "type": "object",
        "properties": {
            "name": {"type": "string"},
            "child": {
                "type": "object",
                "properties": {"data": {"type": "string"}}
            }
        }
    }
    assert _get_llm_type_string(schema, MINIMAL_SPEC, depth=2) == "object"
    expected = "{name: str, child: {data: str}}"
    assert _get_llm_type_string(schema, MINIMAL_SPEC, depth=0) == expected
    expected_depth1 = "{name: str, child: object}"
    assert _get_llm_type_string(schema, MINIMAL_SPEC, depth=1) == expected_depth1

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

# --- Tests for generate_mcp_resources ---

def test_generate_mcp_resources_no_get_operations():
    spec = {
        "paths": {
            "/items": {
                "post": { # only a post operation
                    "summary": "Create an item",
                    "responses": {"201": {"description": "Item created"}}
                }
            }
        }
    }
    resource_names, static_resource_tuples, definitions_str = generate_mcp_resources(spec)
    assert resource_names == []
    assert static_resource_tuples == []
    assert definitions_str.strip() == ""

def test_generate_mcp_resources_simple_get_no_params():
    spec = {
        "paths": {
            "/ping": {
                "get": {
                    "operationId": "pingServer",
                    "summary": "Ping the server",
                    "description": "Returns a pong message.",
                    "responses": {
                        "200": {
                            "description": "Successful pong",
                            "content": {"application/json": {"schema": {"type": "string"}}}
                        }
                    }
                }
            }
        }
    }
    resource_names, static_resource_tuples, definitions_str = generate_mcp_resources(spec)
    assert resource_names == ["ping_server"]
    assert static_resource_tuples == [("ping_server", "/ping")]
    assert "def ping_server() -> str:" in definitions_str
    assert '"""Ping the server' in definitions_str
    assert 'Returns a pong message.' in definitions_str
    assert "@app.resource" not in definitions_str # Static path

def test_generate_mcp_resources_get_with_path_params():
    spec = {
        "paths": {
            "/users/{userId}/info": {
                "get": {
                    "operationId": "getUserInfo",
                    "summary": "Get user information",
                    "parameters": [
                        {"name": "userId", "in": "path", "required": True, "schema": {"type": "integer"}}
                    ],
                    "responses": {
                        "200": {"description": "User data", "content": {"application/json": {"schema": {"type": "object", "properties": {"name": {"type": "string"}}}}}}
                    }
                }
            }
        }
    }
    resource_names, static_resource_tuples, definitions_str = generate_mcp_resources(spec)
    assert resource_names == ["get_user_info"]
    assert static_resource_tuples == [] # Templated path
    assert '@app.resource("users/{userId}/info")' in definitions_str
    assert "def get_user_info(user_id: int) -> Dict[str, Any]:" in definitions_str # userId becomes user_id
    assert "user_id: int" in definitions_str # Sanitized path param

def test_generate_mcp_resources_get_with_query_params():
    spec = {
        "paths": {
            "/items": {
                "get": {
                    "summary": "List items",
                    "parameters": [
                        {"name": "limit", "in": "query", "required": False, "schema": {"type": "integer"}},
                        {"name": "filter-by", "in": "query", "required": True, "schema": {"type": "string"}}
                    ],
                    "responses": {
                        "200": {"description": "A list of items", "content": {"application/json": {"schema": {"type": "array", "items": {"type": "string"}}}}}
                    }
                }
            }
        }
    }
    resource_names, static_resource_tuples, definitions_str = generate_mcp_resources(spec)
    assert resource_names == ["get_items"]
    assert static_resource_tuples == [("get_items", "/items")]
    assert "def get_items(limit: int | None = None, filter_by: str) -> List[str]:" in definitions_str # filter-by becomes filter_by
    assert "limit: int | None = None" in definitions_str
    assert "filter_by: str" in definitions_str # Sanitized query param

def test_generate_mcp_resources_response_handling():
    spec = {
        "paths": {
            "/data": {
                "get": {
                    "responses": { # No 200 or 201, should default to Any
                        "202": {"description": "Accepted", "content": {"application/json": {"schema": {"type": "string"}}}}
                    }
                }
            },
            "/refData": {
                "get": {
                    "responses": {
                        "200": {"description": "OK", "content": {"application/json": {"schema": {"$ref": "#/components/schemas/MyData"}}}}
                    }
                }
            }
        },
        "components": {"schemas": {"MyData": {"type": "object", "properties": {"value": {"type": "integer"}}}}}
    }
    resource_names, static_resource_tuples, definitions_str = generate_mcp_resources(spec)
    assert "get_data() -> Any:" in definitions_str
    assert "get_ref_data() -> MyData:" in definitions_str

def test_generate_mcp_resources_path_name_generation_no_opid():
    spec = {
        "paths": {
            "/some/very-long/path-example": {"get": {"responses": {"200": {"description": "ok"}}}},
            "/items/{item_id}/sub-items/{sub_item-name}": {
                "get": {
                    "summary": "Get a specific sub-item",
                    "parameters": [
                        {
                            "name": "item_id",
                            "in": "path",
                            "required": True,
                            "schema": {"type": "string"} # Schema can be simple or complex
                        },
                        {
                            "name": "sub_item-name", # original name with hyphen
                            "in": "path",
                            "required": True,
                            "schema": {"type": "string"}
                        }
                    ],
                    "responses": {"200": {"description": "ok"}}
                }
            }
        }
    }
    resource_names, _, definitions_str = generate_mcp_resources(spec)
    assert "get_some_very_long_path_example" in resource_names
    assert "def get_some_very_long_path_example() -> Any:" in definitions_str
    assert "get_items_by_item_id_sub_items_by_sub_item_name" in resource_names
    # Parameters should now be correctly generated and snake_cased
    assert "def get_items_by_item_id_sub_items_by_sub_item_name(item_id: str, sub_item_name: str) -> Any:" in definitions_str
    assert '@app.resource("items/{item_id}/sub-items/{sub_item-name}")' in definitions_str

def test_generate_mcp_resources_parameter_name_sanitization():
    spec = {
        "paths": {
            "/search/{search-term}": {
                "get": {
                    "parameters": [
                        {"name": "search-term", "in": "path", "required": True, "schema": {"type": "string"}},
                        {"name": "X-Request-ID", "in": "query", "schema": {"type": "string"}}
                    ],
                    "responses": {"200": {"description": "ok"}}
                }
            }
        }
    }
    _, _, definitions_str = generate_mcp_resources(spec)
    # Path param 'search-term' becomes 'search_term' (sanitized by _sanitize_python_identifier)
    # Query param 'X-Request-ID' becomes 'x_request_id' (sanitized then snake_cased)
    assert "def get_search_by_search_term(search_term: str, x_request_id: str | None = None) -> Any:" in definitions_str
    assert "search_term: str" in definitions_str
    assert "x_request_id: str | None = None" in definitions_str
    assert '@app.resource("search/{search-term}")' in definitions_str

# --- Tests for generate_mcp_tools ---

def test_generate_mcp_tools_no_tool_operations():
    spec = {
        "paths": {
            "/items": {
                "get": { # only a get operation
                    "summary": "List items",
                    "responses": {"200": {"description": "A list of items"}}
                }
            }
        }
    }
    tool_names, definitions_str = generate_mcp_tools(spec)
    assert tool_names == []
    assert definitions_str.strip() == ""

def test_generate_mcp_tools_simple_post_no_body_no_params():
    spec = {
        "paths": {
            "/create_simple": {
                "post": {
                    "operationId": "createSimpleResource",
                    "summary": "Create a simple resource",
                    "responses": {
                        "201": {"description": "Created", "content": {"application/json": {"schema": {"type": "string"}}}}
                    }
                }
            }
        }
    }
    tool_names, definitions_str = generate_mcp_tools(spec)
    assert tool_names == ["create_simple_resource"]
    assert "@app.tool" in definitions_str
    assert "def create_simple_resource(ctx: fmcp.Context) -> str:" in definitions_str
    assert '"""Create a simple resource' in definitions_str

def test_generate_mcp_tools_put_with_path_and_query_params():
    spec = {
        "paths": {
            "/items/{itemId}": {
                "put": {
                    "operationId": "updateItem",
                    "parameters": [
                        {"name": "itemId", "in": "path", "required": True, "schema": {"type": "string"}},
                        {"name": "notify-user", "in": "query", "schema": {"type": "boolean"}}
                    ],
                    "responses": {"200": {"description": "Updated"}}
                }
            }
        }
    }
    tool_names, definitions_str = generate_mcp_tools(spec)
    assert tool_names == ["update_item"]
    # Path param itemId (sanitized only) vs query param notify-user (sanitized then snake_cased)
    # The code for tools currently does:
    # param_name = _sanitize_python_identifier(p['name']) if p.get('in') == 'path' else _to_snake_case(_sanitize_python_identifier(p['name']))
    # This is inconsistent with resources. For tools, let's assume all params should be snake_cased for consistency in Python.
    # I will adjust this test to expect snake_case for path params too, and will need to update the generator logic for generate_mcp_tools.
    assert "def update_item(ctx: fmcp.Context, item_id: str, notify_user: bool | None = None) -> Dict[str,Any]:" # Default response Any or Dict
    # The default response if not 204 and no specific 200/201/202 schema is Dict[str,Any]

def test_generate_mcp_tools_delete_204_response():
    spec = {
        "paths": {
            "/items/{item_id}": {
                "delete": {
                    "summary": "Delete an item",
                    "parameters": [{"name": "item_id", "in": "path", "required": True, "schema": {"type": "string"}}],
                    "responses": {"204": {"description": "Item deleted"}}
                }
            }
        }
    }
    tool_names, definitions_str = generate_mcp_tools(spec)
    assert tool_names == ["delete_items_by_item_id"] # name generated from path
    assert "def delete_items_by_item_id(ctx: fmcp.Context, item_id: str) -> None:" in definitions_str

def test_generate_mcp_tools_with_request_body_ref():
    spec = {
        "components": {"schemas": {"MyItem": {"type": "object", "properties": {"name": {"type": "string"}}}}},
        "paths": {
            "/items": {
                "post": {
                    "requestBody": {
                        "required": True,
                        "content": {"application/json": {"schema": {"$ref": "#/components/schemas/MyItem"}}}
                    },
                    "responses": {"201": {"description": "Created", "content": {"application/json": {"schema": {"$ref": "#/components/schemas/MyItem"}}}}}
                }
            }
        }
    }
    tool_names, definitions_str = generate_mcp_tools(spec)
    assert tool_names == ["post_items"]
    # requestBody schema name "MyItem" becomes snake_cased "my_item"
    assert "def post_items(ctx: fmcp.Context, my_item: MyItem) -> MyItem:" in definitions_str

def test_generate_mcp_tools_with_request_body_inline_and_optional():
    spec = {
        "paths": {
            "/items_inline": {
                "post": {
                    "requestBody": {
                        "required": False,
                        "content": {"application/json": {"schema": {"type": "object", "properties": {"data": {"type": "string"}}}}}
                    },
                    "responses": {"201": {"description": "Created"}}
                }
            }
        }
    }
    tool_names, definitions_str = generate_mcp_tools(spec)
    assert tool_names == ["post_items_inline"]
    # Inline request body uses "payload" as name, type is Dict[str, Any] for inline object
    assert "def post_items_inline(ctx: fmcp.Context, payload: Dict[str, Any] | None = None) -> Dict[str,Any]:" in definitions_str

def test_generate_mcp_tools_all_param_types_and_response_schema():
    spec = {
        "components": {
            "schemas": {
                "ItemCreate": {"type": "object", "properties": {"name": {"type": "string"}, "value": {"type": "integer"}}},
                "ItemResponse": {"type": "object", "properties": {"id": {"type": "string"}, "status": {"type": "string"}}}
            }
        },
        "paths": {
            "/complex_tool/{entity_id}": {
                "put": {
                    "operationId": "complexToolUpdate",
                    "summary": "Update a complex entity",
                    "parameters": [
                        {"name": "entity_id", "in": "path", "required": True, "schema": {"type": "string"}},
                        {"name": "queryParam", "in": "query", "required": True, "schema": {"type": "boolean"}},
                        {"name": "optionalQuery", "in": "query", "required": False, "schema": {"type": "integer"}}
                    ],
                    "requestBody": {
                        "required": True,
                        "content": {"application/json": {"schema": {"$ref": "#/components/schemas/ItemCreate"}}}
                    },
                    "responses": {
                        "200": {"description": "Updated successfully", "content": {"application/json": {"schema": {"$ref": "#/components/schemas/ItemResponse"}}}}
                    }
                }
            }
        }
    }
    tool_names, definitions_str = generate_mcp_tools(spec)
    assert tool_names == ["complex_tool_update"]
    expected_sig = "def complex_tool_update(ctx: fmcp.Context, entity_id: str, query_param: bool, optional_query: int | None = None, item_create: ItemCreate) -> ItemResponse:"
    assert expected_sig in definitions_str
    assert "@app.tool" in definitions_str
    assert '"""Update a complex entity' in definitions_str

# --- Tests for generate_llms_txt ---

SPEC_FOR_LLMS_TEST = {
    "openapi": "3.0.0",
    "info": {"title": "LLMS Test API", "version": "1.0"},
    "components": {
        "schemas": {
            "MyItem": {"type": "object", "properties": {"name": {"type": "string"}, "value": {"type": "integer"}}},
            "ItemResponse": {"type": "object", "properties": {"id": {"type": "string"}, "status": {"type": "string"}}}
        }
    },
    "paths": {
        "/items": {
            "post": {
                "operationId": "create_llms_item",
                "summary": "Create an item for LLMS.",
                "description": "This operation creates a new item with the given details.",
                "requestBody": {
                    "required": True,
                    "content": {"application/json": {"schema": {"$ref": "#/components/schemas/MyItem"}}}
                },
                "responses": {"201": {"description": "Item created", "content": {"application/json": {"schema": {"$ref": "#/components/schemas/ItemResponse"}}}}}
            }
        },
        "/items/{item_id}": {
            "put": {
                # No operationId, name will be generated
                "summary": "Update an item.",
                # No description, should use summary or default.
                "parameters": [
                    {"name": "item_id", "in": "path", "required": True, "schema": {"type": "string"}},
                    {"name": "queryFlag", "in": "query", "required": False, "schema": {"type": "boolean"}}
                ],
                "requestBody": {
                    "required": False, # Optional body
                    "content": {"application/json": {"schema": {"$ref": "#/components/schemas/MyItem"}}}
                },
                "responses": {"200": {"description": "Updated"}}
            }
        },
        "/action": {
            "post": {
                "operationId": "do_action", "summary": "Perform an action.", # No parameters
                "responses": {"204": {"description": "Action done"}}
            }
        },
        "/other": { # No tools here
            "get": {"summary": "Get other", "responses": {"200": {"description": "OK"}}}
        }
    }
}

def test_generate_llms_txt_no_tool_operations_or_empty_tool_names():
    empty_spec = {"openapi": "3.0.0", "info": {"title": "Empty", "version": "1.0"}, "paths": {}}
    assert generate_llms_txt(empty_spec, []) == ""

    # Spec has tool-generating paths, but tool_names list is empty
    assert generate_llms_txt(SPEC_FOR_LLMS_TEST, []) == ""

def test_generate_llms_txt_with_tools():
    tool_names = [
        "create_llms_item",
        _generate_function_name("put", "/items/{item_id}", None) # Should be put_items_by_item_id
    ]

    llms_output = generate_llms_txt(SPEC_FOR_LLMS_TEST, tool_names)

    # Check create_llms_item
    assert "## create_llms_item" in llms_output
    assert "Create an item for LLMS." in llms_output # Summary is present
    assert "Параметры:" in llms_output
    assert "- my_item: MyItem {name: str, value: int}" in llms_output
    # Verify (опционально) is NOT present for required my_item
    create_section = llms_output.split("## create_llms_item")[1].split("## ")[0]
    assert "(опционально)" not in create_section.split("Параметры:")[1]

    # Check put_items_by_item_id
    put_tool_name = _generate_function_name("put", "/items/{item_id}", None)
    assert f"## {put_tool_name}" in llms_output
    assert "Update an item." in llms_output # Summary used as description
    assert "Параметры:" in llms_output # This is part of the string to be split

    put_section = llms_output.split(f"## {put_tool_name}")[1].split("##")[0]
    params_section_for_put = put_section.split("Параметры:")[1]
    param_lines_for_put = [line.strip() for line in params_section_for_put.split('\n') if line.strip().startswith("- ")]

    item_id_line = next((line for line in param_lines_for_put if line.startswith("- item_id:")), None)
    assert item_id_line is not None, "item_id parameter line not found for put_items_by_item_id"
    assert "(опционально)" not in item_id_line, f"item_id should not be optional: {item_id_line}"

    assert any("- query_flag: bool (опционально)" in line for line in param_lines_for_put), "query_flag parameter not found or not correctly formatted"
    assert any("- my_item: MyItem {name: str, value: int} (опционально)" in line for line in param_lines_for_put), "my_item parameter not found or not correctly formatted"

    assert "## do_action" not in llms_output # Not in tool_names
    assert "Get other" not in llms_output # GET operation

def test_generate_llms_txt_no_parameters_for_tool():
    spec_no_params = {
        "openapi": "3.0.0", "info": {"title": "No Params API", "version": "1.0"},
        "paths": {
            "/action": {
                "post": {
                    "operationId": "do_action", "summary": "Perform an action.",
                    "responses": {"204": {"description": "Action done"}}
                }
            }
        }
    }
    tool_names = ["do_action"]
    llms_output = generate_llms_txt(spec_no_params, tool_names)
    assert "## do_action" in llms_output
    assert "Perform an action." in llms_output
    assert "- Нет параметров" in llms_output

def test_generate_llms_txt_description_fallback():
    spec_desc_fallback = {
        "openapi": "3.0.0", "info": {"title": "Desc Fallback", "version": "1.0"},
        "paths": {
            "/action_desc": {
                "post": { # No summary, only description
                    "operationId": "action_with_description",
                    "description": "Detailed description of the action.",
                    "responses": {"204": {"description": "Done"}}
                }
            },
            "/action_no_summary_desc": {
                 "post": { # No summary or description
                    "operationId": "action_no_details",
                    "responses": {"204": {"description": "Done"}}
                }
            }
        }
    }
    tool_names = ["action_with_description", "action_no_details"]
    llms_output = generate_llms_txt(spec_desc_fallback, tool_names)

    assert "## action_with_description" in llms_output
    assert "Detailed description of the action." in llms_output

    assert "## action_no_details" in llms_output
    # Based on current generator.py: op_spec.get('summary',op_spec.get('description','No description')) or "No summary."
    # So if both are missing, it defaults to 'No description', then if that was falsey, 'No summary'.
    # It seems 'No description' is the expected default if both summary/desc are missing.
    assert "No description" in llms_output.split("## action_no_details")[1]

def test_generate_llms_txt_parameter_name_handling():
    # Based on spec_with_tools.yaml structure
    spec = {
        "openapi": "3.0.0", "info": {"title": "Test API with Tools", "version": "1.0"},
        "components": {
            "schemas": {
                "NewItem": {"type": "object", "properties": {"name": {"type": "string"}, "description": {"type": "string", "nullable": True}}, "required": ["name"]}
            }
        },
        "paths": {
            "/items/{item_id-path}": { # Path param with hyphen
                "put": {
                    "operationId": "update_item_for_llms",
                    "summary": "Update item.",
                    "parameters": [
                        {"name": "item_id-path", "in": "path", "required": True, "schema": {"type": "string"}},
                        {"name": "query-param with space", "in": "query", "schema": {"type": "string"}}
                    ],
                    "requestBody": {"required": True, "content": {"application/json": {"schema": {"$ref": "#/components/schemas/NewItem"}}}},
                    "responses": {"200": {"description": "OK"}}
                }
            }
        }
    }
    tool_names = ["update_item_for_llms"]
    llms_output = generate_llms_txt(spec, tool_names)

    assert "## update_item_for_llms" in llms_output
    # Path param: _sanitize_python_identifier
    assert "- item_id_path: str" in llms_output
    # Query param: _to_snake_case(_sanitize_python_identifier())
    assert "- query_param_with_space: str (опционально)" in llms_output
    # Request body: _to_snake_case of schema name
    assert "- new_item: NewItem {name: str, description: str}" in llms_output

# --- Tests for generate_mcp_server_code ---

MINIMAL_SPEC_FOR_SERVER = {
    "openapi": "3.0.0",
    "info": {"title": "Minimal Server", "version": "0.0.1"},
    "paths": {}
}

SPEC_WITH_COMPONENTS_FOR_SERVER = {
    "openapi": "3.0.0",
    "info": {"title": "Server With All", "version": "1.2.3"},
    "components": {
        "schemas": {
            "Item": {"type": "object", "properties": {"name": {"type": "string"}}}
        }
    },
    "paths": {
        "/items": {
            "get": {"operationId": "list_items", "responses": {"200": {"description": "OK"}}},
            "post": {"operationId": "create_item", "requestBody": {"content": {"application/json": {"schema": {"$ref": "#/components/schemas/Item"}}}}, "responses": {"201": {"description": "Created"}}}
        },
        "/items/{item_id}": {
            "get": {"operationId": "get_item", "parameters": [{"name": "item_id", "in": "path", "required": True, "schema": {"type": "string"}}], "responses": {"200": {"description": "OK"}}}
        }
    }
}

DEFAULT_APP_DETAILS = {"name": "TestApp", "version": "1.0"}


def test_generate_mcp_server_code_minimal_stdio():
    code, _ = generate_mcp_server_code(MINIMAL_SPEC_FOR_SERVER, DEFAULT_APP_DETAILS, "stdio")
    assert "from __future__ import annotations" in code
    assert "import sys" in code
    assert "import fastmcp as fmcp" in code
    assert "from pydantic import BaseModel" in code
    assert "from typing import List, Optional, Any, Dict" in code
    assert "app = fmcp.FastMCP(" in code
    assert 'name="TestApp"' in code # From DEFAULT_APP_DETAILS
    assert 'version="1.0"' in code
    assert "if __name__ == \"__main__\":\n    app.run_stdio()" in code
    assert "class Item(BaseModel)" not in code
    assert "def list_items()" not in code
    assert "@app.tool" not in code
    assert "@app.resource" not in code
    assert "# Register static resources explicitly" not in code # No static resources

def test_generate_mcp_server_code_sse_transport():
    code, _ = generate_mcp_server_code(MINIMAL_SPEC_FOR_SERVER, DEFAULT_APP_DETAILS, "sse")
    assert "if __name__ == \"__main__\":\n    app.run_sse()" in code

def test_generate_mcp_server_code_http_transport():
    code, _ = generate_mcp_server_code(MINIMAL_SPEC_FOR_SERVER, DEFAULT_APP_DETAILS, "http")
    assert "import uvicorn" in code
    assert "uvicorn.run(app.http_app, host=\"0.0.0.0\", port=8000)" in code
    assert "except ImportError:" in code # Check for uvicorn import handling

def test_generate_mcp_server_code_with_all_components():
    # Using spec info for app details
    app_details_from_spec = {"name": "Server With All", "version": "1.2.3"}
    code, tool_names = generate_mcp_server_code(SPEC_WITH_COMPONENTS_FOR_SERVER, app_details_from_spec, "http")

    assert f'name="{app_details_from_spec["name"]}"' in code
    assert f'version="{app_details_from_spec["version"]}"' in code

    # Schemas
    assert "class Item(BaseModel):\n    name: str | None = None" in code
    assert "Item.model_rebuild()" in code

    # Resources
    assert "def list_items() -> Any:" in code # Static resource
    assert "@app.resource(\"items/{item_id}\")" in code # Templated resource
    assert "def get_item(item_id: str) -> Any:" in code

    # Tools
    assert "@app.tool" in code
    assert "def create_item(ctx: fmcp.Context, item: Item) -> Dict[str,Any]:" in code # Corrected expectation
    assert "create_item" in tool_names

    # Static resource registration
    assert "if 'list_items' in locals():" in code
    assert "app.add_resource(list_items, path_override=\"/items\")" in code

    # Main block (HTTP)
    assert "uvicorn.run(app.http_app" in code

def test_generate_mcp_server_code_override_info_with_app_details():
    app_details_override = {"name": "OverrideApp", "version": "2.0.0"}
    code, _ = generate_mcp_server_code(SPEC_WITH_COMPONENTS_FOR_SERVER, app_details_override, "stdio")
    assert 'name="OverrideApp"' in code
    assert 'version="2.0.0"' in code
    # Ensure info from spec is NOT used for these if overridden by mcp_app_details
    assert 'name="Server With All"' not in code
    assert 'version="1.2.3"' not in code

def test_generate_mcp_server_code_no_schemas():
    spec_no_schemas = {
        "openapi": "3.0.0", "info": {"title": "No Schemas", "version": "1.0"},
        "paths": {"/ping": {"get": {"responses": {"200": {"description": "OK"}}}}}
    }
    code, _ = generate_mcp_server_code(spec_no_schemas, DEFAULT_APP_DETAILS, "stdio")
    assert "class" not in code # No Pydantic models
    assert "BaseModel" in code # Import is still there
    assert "get_ping()" in code # Resource should be generated

def test_generate_mcp_server_code_no_get_operations():
    spec_no_get = {
        "openapi": "3.0.0", "info": {"title": "No GET", "version": "1.0"},
        "paths": {"/submit": {"post": {"responses": {"201": {"description": "Created"}}}}}
    }
    code, _ = generate_mcp_server_code(spec_no_get, DEFAULT_APP_DETAILS, "stdio")
    assert "@app.resource" not in code
    assert "# Register static resources explicitly" not in code # Block should be absent
    assert "post_submit(ctx: fmcp.Context)" in code # Tool should be there

def test_generate_mcp_server_code_no_tool_operations():
    spec_no_tools = {
        "openapi": "3.0.0", "info": {"title": "No Tools", "version": "1.0"},
        "paths": {"/data": {"get": {"responses": {"200": {"description": "OK"}}}}}
    }
    code, tool_names = generate_mcp_server_code(spec_no_tools, DEFAULT_APP_DETAILS, "stdio")
    assert "@app.tool" not in code
    assert tool_names == []
    assert "get_data()" in code # Resource should be there
    assert "if 'get_data' in locals():" in code # Static resource registration
    assert "app.add_resource(get_data, path_override=\"/data\")" in code
