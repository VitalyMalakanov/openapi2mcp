import re
from typing import List, Optional, Any, Dict, Tuple

# Helper for Pydantic model field type strings
def _oas_type_to_pydantic_type_str(prop_schema: Dict[str, Any]) -> str:
    oas_type = prop_schema.get("type")
    if "$ref" in prop_schema:
        return prop_schema["$ref"].split("/")[-1]
    elif oas_type == "string": return "str"
    elif oas_type == "integer": return "int"
    elif oas_type == "number": return "float"
    elif oas_type == "boolean": return "bool"
    elif oas_type == "array":
        items_schema = prop_schema.get("items", {})
        item_type = "Any" if not items_schema else _oas_type_to_pydantic_type_str(items_schema)
        return f"List[{item_type}]"
    elif oas_type == "object": return "Dict[str, Any]"
    return "Any"

# Helper for function parameter/return type annotations
def oas_schema_to_python_type(schema_obj: Dict[str, Any], schemas_root: Dict[str, Any] = None) -> str:
    if not isinstance(schema_obj, dict): return "Any"
    if "$ref" in schema_obj:
        return schema_obj["$ref"].split("/")[-1]
    oas_type = schema_obj.get("type")
    if oas_type == "string": return "str"
    elif oas_type == "integer": return "int"
    elif oas_type == "number": return "float"
    elif oas_type == "boolean": return "bool"
    elif oas_type == "array":
        items_schema = schema_obj.get("items", {})
        item_type = "Any" if not items_schema else oas_schema_to_python_type(items_schema, schemas_root)
        return f"List[{item_type}]"
    elif oas_type == "object": return "Dict[str, Any]"
    return "Any"

def generate_pydantic_models(schemas: Dict[str, Any]) -> str:
    if not schemas: return ""
    model_definitions = []
    pydantic_specific_imports = {"from pydantic import BaseModel"}
    typing_imports_for_pydantic = set()

    for schema_name, schema_details in schemas.items():
        if not isinstance(schema_details, dict) or schema_details.get("type") != "object": continue
        model_code = f"class {schema_name}(BaseModel):\n"
        properties = schema_details.get("properties", {})
        required_fields = schema_details.get("required", [])
        if not properties: model_code += "    pass\n"
        else:
            for prop_name, prop_schema in properties.items():
                base_type_str = _oas_type_to_pydantic_type_str(prop_schema)
                if "List" in base_type_str: typing_imports_for_pydantic.add("List")
                if "Any" in base_type_str: typing_imports_for_pydantic.add("Any")
                model_code += f"    {prop_name}: {base_type_str}"
                if prop_name not in required_fields: model_code += " | None = None"
                model_code += "\n"
        model_code += "\n"
        model_definitions.append(model_code)

    final_import_lines = list(pydantic_specific_imports)
    if typing_imports_for_pydantic:
        # Ensure 'Optional' is not added here if only using `| None`
        typing_to_import = sorted([t for t in list(typing_imports_for_pydantic) if t != "Optional"])
        if typing_to_import:
             final_import_lines.append(f"from typing import {', '.join(typing_to_import)}")

    import_block = "\n".join(final_import_lines) + "\n\n" if final_import_lines else ""
    return import_block + "".join(model_definitions)

def _sanitize_python_identifier(name: str) -> str:
    name = re.sub(r'[^0-9a-zA-Z_]', '_', name)
    name = re.sub(r'^[^a-zA-Z_]+', '', name)
    if not name: return "_generated_name"
    if name[0].isdigit(): name = "_" + name
    return name

def _to_snake_case(name: str) -> str:
    s1 = re.sub('(.)([A-Z][a-z]+)', r'\1_\2', name)
    return re.sub('([a-z0-9])([A-Z])', r'\1_\2', s1).lower()

def _generate_function_name(method: str, path: str, operation_id: str | None) -> str:
    if operation_id:
        return _to_snake_case(_sanitize_python_identifier(operation_id))
    path_parts = path.strip('/').split('/')
    processed_parts = []
    for part in path_parts:
        if "{" in part and "}" in part:
            param_name = _sanitize_python_identifier(part.strip('{}'))
            processed_parts.append(f"by_{_to_snake_case(param_name)}")
        else:
            processed_parts.append(_to_snake_case(_sanitize_python_identifier(part)))
    name_base = "_".join(filter(None, processed_parts))
    return f"{method.lower()}_{name_base}"

def generate_mcp_resources(spec: Dict[str, Any]) -> Tuple[List[str], str]:
    resource_names = []
    resource_definitions = []
    schemas_root = spec.get('components', {}).get('schemas', {})

    for path_str, path_item in spec.get('paths', {}).items():
        if 'get' in path_item:
            operation_spec = path_item['get']
            func_name = _generate_function_name('get', path_str, operation_spec.get('operationId'))
            resource_names.append(func_name)
            arg_strings = []
            for param in operation_spec.get('parameters', []):
                param_name = _to_snake_case(_sanitize_python_identifier(param['name']))
                annotation = oas_schema_to_python_type(param.get('schema', {}), schemas_root)
                type_hint = f"{annotation} | None = None" if not param.get('required', False) else annotation
                arg_strings.append(f"{param_name}: {type_hint}")

            return_annotation_str = "Any"
            for code, resp_spec in operation_spec.get('responses', {}).items():
                if code in ['200', '201'] and 'application/json' in resp_spec.get('content', {}):
                    return_annotation_str = oas_schema_to_python_type(
                        resp_spec['content']['application/json'].get('schema', {}), schemas_root)
                    break
            summary = operation_spec.get('summary', 'Generated MCP resource.')
            desc = operation_spec.get('description', '')
            docstring = f"{summary}\n\n{desc}".strip().replace('\"\"\"', '\\"\\"\\"').replace('\n', '\n        ')
            resource_code = (
                f"@app.resource\n"
                f"def {func_name}({', '.join(arg_strings)}) -> {return_annotation_str}:\n"
                f"    \"\"\"{docstring}\n    \"\"\"\n"
                f"    pass  # TODO: Implement actual logic\n"
            )
            resource_definitions.append(resource_code)
    return resource_names, "\n\n".join(resource_definitions)

def generate_mcp_tools(spec: Dict[str, Any]) -> Tuple[List[str], str]:
    tool_names = []
    tool_definitions = []
    schemas_root = spec.get('components', {}).get('schemas', {})
    component_schema_names = list(schemas_root.keys())

    for path_str, path_item in spec.get('paths', {}).items():
        for method_name in ['post', 'put', 'delete']:
            if method_name in path_item:
                operation_spec = path_item[method_name]
                func_name = _generate_function_name(method_name, path_str, operation_spec.get('operationId'))
                tool_names.append(func_name)
                arg_strings = ["ctx: mcp.Context"]
                for param in operation_spec.get('parameters', []):
                    param_name_sanitized = _to_snake_case(_sanitize_python_identifier(param['name']))
                    annotation = oas_schema_to_python_type(param.get('schema', {}), schemas_root)
                    type_hint = f"{annotation} | None = None" if not param.get('required', False) else annotation
                    arg_strings.append(f"{param_name_sanitized}: {type_hint}")

                if 'requestBody' in operation_spec:
                    request_body_spec = operation_spec['requestBody']
                    content_spec = request_body_spec.get('content', {}).get('application/json', {})
                    schema_spec = content_spec.get('schema', {})
                    if schema_spec:
                        body_param_type = oas_schema_to_python_type(schema_spec, schemas_root)
                        body_param_name = "payload"
                        if "$ref" in schema_spec:
                            ref_name = schema_spec["$ref"].split("/")[-1]
                            if ref_name in component_schema_names: body_param_name = _to_snake_case(ref_name)
                        elif body_param_type in component_schema_names: body_param_name = _to_snake_case(body_param_type)
                        is_body_required = request_body_spec.get('required', True)
                        arg_strings.append(f"{body_param_name}: {body_param_type}{'' if is_body_required else ' | None = None'}")

                return_annotation_str = "Dict[str, Any]"
                responses = operation_spec.get('responses', {})
                if '204' in responses: return_annotation_str = "None"
                else:
                    for code in ['200', '201', '202']:
                        if code in responses and 'application/json' in responses[code].get('content', {}):
                            resp_schema = responses[code]['content']['application/json'].get('schema')
                            if resp_schema: return_annotation_str = oas_schema_to_python_type(resp_schema, schemas_root); break
                summary = operation_spec.get('summary', f'Generated MCP tool for {method_name.upper()} {path_str}')
                desc = operation_spec.get('description', '')
                docstring = f"{summary}\n\n{desc}".strip().replace('\"\"\"', '\\"\\"\\"').replace('\n', '\n        ')
                tool_code = (
                    f"@app.tool\n"
                    f"def {func_name}({', '.join(arg_strings)}) -> {return_annotation_str}:\n"
                    f"    \"\"\"{docstring}\n    \"\"\"\n"
                    f"    pass  # TODO: Implement actual logic. Consider using ctx.sample() for LLM interaction.\n"
                )
                tool_definitions.append(tool_code)
    return tool_names, "\n\n".join(tool_definitions)

# Updated generate_mcp_server_code signature and logic
def generate_mcp_server_code(spec: Dict[str, Any], mcp_app_details: Dict[str, str], transport: str) -> str:
    future_imports = "from __future__ import annotations\n\n"
    standard_imports_list = [
        "import fastmcp as mcp",
        "from pydantic import BaseModel",
        "from typing import List, Optional, Any, Dict", # Maintained comprehensive list for server scope
    ]
    standard_imports_block = "\n".join(standard_imports_list) + "\n\n"

    pydantic_models_code = generate_pydantic_models(spec.get('components', {}).get('schemas', {}))
    resource_names, resources_code = generate_mcp_resources(spec)
    tool_names, tools_code = generate_mcp_tools(spec)

    llm_tools_list_str = f"[{', '.join(tool_names)}]" if tool_names else "[]"
    # Ensure function names in llm_tools_list_str are actual identifiers, not strings
    # This was correct in the previous step, assuming tool_names contains valid function identifiers

    app_init_code = f"""app = mcp.Mcp(
    name="{mcp_app_details.get("name", "GeneratedAPI")}",
    version="{mcp_app_details.get("version", "0.1.0")}",
    llm_tools={llm_tools_list_str}
)
"""
    registration_code = "\n\n# Register resources\n"
    if resource_names:
        for name in resource_names:
            registration_code += f"if '{name}' in locals():\n"
            registration_code += f"    app.add_resource({name})\n"
    else:
        registration_code += "# No resources to register\n"

    # Main execution block based on transport
    main_execution_block = ""
    if transport == 'stdio':
        main_execution_block = """
if __name__ == "__main__":
    app.run_stdio()
"""
    elif transport == 'sse':
        main_execution_block = """
if __name__ == "__main__":
    # fastmcp v2.2.0+ should have app.run_sse()
    app.run_sse()
"""
    elif transport == 'http':
        # The import uvicorn and exit(1) should be within the if __name__ == "__main__" block
        # to avoid issues if the generated file is imported as a module.
        main_execution_block = """
if __name__ == "__main__":
    try:
        import uvicorn
    except ImportError:
        print("Error: 'uvicorn' is not installed. Please install it to use the http transport (e.g., pip install uvicorn)")
        import sys # Import sys to use sys.exit()
        sys.exit(1) # Use sys.exit() for cleaner exit
    # fastmcp v2.2.0+ should have app.as_asgi()
    uvicorn.run(app.as_asgi(), host="0.0.0.0", port=8000)
"""

    # Assemble the final code
    final_code_parts = [
        future_imports,
        standard_imports_block,
    ]
    if pydantic_models_code:
        final_code_parts.append(pydantic_models_code)
        if not pydantic_models_code.endswith("\n\n"):
            final_code_parts.append("\n")

    final_code_parts.append(app_init_code)
    if resources_code:
        final_code_parts.append("\n\n" + resources_code)
    if tools_code:
        final_code_parts.append("\n\n" + tools_code)

    final_code_parts.append(registration_code)
    final_code_parts.append(main_execution_block) # Add the main execution block

    return "".join(final_code_parts)
