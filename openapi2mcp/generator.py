import re
from typing import List, Optional, Any, Dict, Tuple

# --- Type Conversion Helpers ---
def _oas_type_to_pydantic_type_str(prop_schema: Dict[str, Any]) -> str:
    oas_type = prop_schema.get("type")
    if "$ref" in prop_schema: return prop_schema["$ref"].split("/")[-1]
    if oas_type == "string": return "str"
    if oas_type == "integer": return "int"
    if oas_type == "number": return "float"
    if oas_type == "boolean": return "bool"
    if oas_type == "array":
        items_schema = prop_schema.get("items", {})
        item_type = "Any" if not items_schema else _oas_type_to_pydantic_type_str(items_schema)
        return f"List[{item_type}]"
    if oas_type == "object": return "Dict[str, Any]"
    return "Any"

def oas_schema_to_python_type(schema_obj: Dict[str, Any], schemas_root: Dict[str, Any] = None) -> str:
    if not isinstance(schema_obj, dict): return "Any"
    if "$ref" in schema_obj: return schema_obj["$ref"].split("/")[-1]
    oas_type = schema_obj.get("type")
    if oas_type == "string": return "str"
    if oas_type == "integer": return "int"
    if oas_type == "number": return "float"
    if oas_type == "boolean": return "bool"
    if oas_type == "array":
        items_schema = schema_obj.get("items", {})
        item_type = "Any" if not items_schema else oas_schema_to_python_type(items_schema, schemas_root)
        return f"List[{item_type}]"
    if oas_type == "object": return "Dict[str, Any]"
    return "Any"

def _get_llm_type_string(schema_obj: Dict[str, Any], spec: Dict[str, Any], depth: int = 0) -> str:
    if not isinstance(schema_obj, dict): return "Any"
    schemas_root = spec.get('components', {}).get('schemas', {})
    if "$ref" in schema_obj:
        schema_name = schema_obj["$ref"].split("/")[-1]
        if depth > 1: return schema_name
        actual_schema = schemas_root.get(schema_name, {})
        if not actual_schema or actual_schema.get("type") != "object": return schema_name
        properties = actual_schema.get("properties", {})
        prop_strings = [f"{name}: {_get_llm_type_string(prop_sch, spec, depth + 1)}" for name, prop_sch in properties.items() if not prop_sch.get("readOnly") and not prop_sch.get("writeOnly")]
        return f"{schema_name} {{{', '.join(prop_strings)}}}" if prop_strings else schema_name
    oas_type = schema_obj.get("type")
    if oas_type == "array":
        item_type_str = _get_llm_type_string(schema_obj.get("items", {}), spec, depth)
        return f"List[{item_type_str}]"
    if oas_type in ["string", "integer", "number", "boolean"]:
        return oas_schema_to_python_type(schema_obj, schemas_root)
    if oas_type == "object":
        if depth > 1: return "object"
        properties = schema_obj.get("properties", {})
        prop_strings = [f"{name}: {_get_llm_type_string(prop_sch, spec, depth + 1)}" for name, prop_sch in properties.items() if not prop_sch.get("readOnly") and not prop_sch.get("writeOnly")]
        return f"{{{', '.join(prop_strings)}}}" if prop_strings else "object"
    return "Any"

# --- Name Generation Helpers ---

# A list of Python keywords that cannot be used as identifiers
PYTHON_KEYWORDS = [
    "False", "None", "True", "and", "as", "assert", "async", "await",
    "break", "class", "continue", "def", "del", "elif", "else", "except",
    "finally", "for", "from", "global", "if", "import", "in", "is", "lambda",
    "nonlocal", "not", "or", "pass", "raise", "return", "try", "while",
    "with", "yield"
]

def _sanitize_python_identifier(name: str) -> str:
    if not name.strip(): # Handles empty string or string with only spaces
        return "_generated_name"

    # Replace invalid characters (anything not a letter, digit, or underscore) with a single underscore
    name = re.sub(r'[^0-9a-zA-Z_]', '_', name)

    # Condense multiple consecutive underscores to a single underscore
    name = re.sub(r'_+', '_', name)

    # If the name consists only of underscores (e.g., "---" became "___" then "_")
    # or if it became empty after initial char replacement (e.g. if re.sub resulted in empty)
    if not name.replace("_", ""): # if stripping all '_' leaves an empty string
        return "_generated_name"

    # If the first character is a digit, prepend an underscore
    # This must be done *after* initial sanitization and before keyword check
    if name[0].isdigit():
        name = "_" + name

    # If the sanitized name is a Python keyword, append an underscore
    if name in PYTHON_KEYWORDS:
        name += "_"

    return name

def _to_snake_case(name: str) -> str:
    if not name:
        return ""
    # Replace hyphens and other common separators with underscores
    name = re.sub(r'[-.\s]', '_', name)
    # Insert underscore before_capitals (handles CamelCase and existing_snake_case gracefully)
    name = re.sub(r'(?<=[a-z0-9])([A-Z])', r'_\1', name)
    # Insert underscore before multiple capitals (e.g. HTTPResponse -> HTTP_Response)
    name = re.sub(r'([A-Z]+)([A-Z][a-z])', r'\1_\2', name)
    # Condense multiple underscores
    name = re.sub(r'_+', '_', name)
    # name = name.strip('_') # Removed this line, as it can strip valid leading/trailing underscores.
    return name.lower()

def _generate_function_name(method: str, path: str, operation_id: str | None) -> str:
    if operation_id:
        sanitized_op_id = _sanitize_python_identifier(operation_id)
        return _to_snake_case(sanitized_op_id)

    path_parts = path.strip('/').split('/')

    if not path_parts or path_parts == ['']: # Handle root path or empty path
        name_base = "root" if path == "/" else _sanitize_python_identifier("") # Uses _generated_name for truly empty
    else:
        processed_parts = []
        for part in path_parts:
            if "{" in part and "}" in part: # Path parameter
                param_name = part.strip('{}')
                # Sanitize the parameter name itself before snake_casing
                sanitized_param_name = _sanitize_python_identifier(param_name)
                # Ensure 'by' is not prepended if sanitized_param_name is empty or just an underscore
                if sanitized_param_name and sanitized_param_name != '_generated_name':
                     processed_parts.append(f"by_{_to_snake_case(sanitized_param_name)}")
                else: # fallback if param name was totally invalid
                    processed_parts.append("by_param")
            else: # Normal path segment
                # Sanitize the segment name before snake_casing
                sanitized_segment = _sanitize_python_identifier(part)
                if sanitized_segment and sanitized_segment != '_generated_name':
                    processed_parts.append(_to_snake_case(sanitized_segment))
                # Do not add a part if the segment was totally invalid

        name_base = "_".join(filter(None, processed_parts))
        if not name_base : # If all parts were invalid or empty
            name_base = _sanitize_python_identifier("") # results in _generated_name

    final_name = f"{method.lower()}_{name_base}"
    # Replace any double underscores that might have formed from joining
    final_name = re.sub(r'_+', '_', final_name)
    return final_name

# --- Code Generation Functions ---
def generate_pydantic_models(schemas: Dict[str, Any]) -> str:
    if not schemas: return ""
    model_definitions_str = ""
    model_rebuild_calls = [] # Store names for model_rebuild calls

    for schema_name, schema_details in schemas.items():
        if not isinstance(schema_details, dict) or schema_details.get("type") != "object": continue
        model_code = f"class {schema_name}(BaseModel):\n"
        properties = schema_details.get("properties", {})
        required_fields = schema_details.get("required", [])
        if not properties: model_code += "    pass\n"
        else:
            for prop_name, prop_schema in properties.items():
                base_type_str = _oas_type_to_pydantic_type_str(prop_schema)
                model_code += f"    {prop_name}: {base_type_str}{'' if prop_name in required_fields else ' | None = None'}\n"
        model_code += "\n" # End class block
        model_definitions_str += model_code
        model_rebuild_calls.append(f"{schema_name}.model_rebuild()")

    # Append all model_rebuild calls after all model definitions
    if model_definitions_str: # Only add rebuild calls if there were models
        model_definitions_str += "\n# Resolve forward references\n"
        for call_str in model_rebuild_calls:
            model_definitions_str += call_str + "\n"
        model_definitions_str += "\n"

    return model_definitions_str

def generate_mcp_resources(spec: Dict[str, Any]) -> Tuple[List[str], List[Tuple[str, str]], str]:
    resource_names, static_resource_tuples, resource_definitions_list = [], [], []
    schemas_root = spec.get('components', {}).get('schemas', {})
    for path_str, path_item in spec.get('paths', {}).items():
        if 'get' in path_item:
            op_spec = path_item['get']
            func_name = _generate_function_name('get', path_str, op_spec.get('operationId'))
            resource_names.append(func_name)
            arg_strings = []
            for param in op_spec.get('parameters', []):
                param_oas_name = param['name']
                # Path and query parameters are snake_cased after sanitization
                param_py_name = _to_snake_case(_sanitize_python_identifier(param_oas_name))
                annotation = oas_schema_to_python_type(param.get('schema', {}), schemas_root)
                type_hint = f"{annotation} | None = None" if not param.get('required', False) else annotation
                arg_strings.append(f"{param_py_name}: {type_hint}")
            ret_ann = next((oas_schema_to_python_type(r['content']['application/json'].get('schema',{}),schemas_root) for c,r in op_spec.get('responses',{}).items() if c in ['200','201'] and 'application/json' in r.get('content',{})), "Any")
            doc = f"{op_spec.get('summary','')}\n\n{op_spec.get('description','')}".strip().replace('\"\"\"','\\"\\"\\"').replace('\n','\n        ')
            func_def_str = f"def {func_name}({', '.join(arg_strings)}) -> {ret_ann}:\n    \"\"\"{doc}\n    \"\"\"\n    pass # TODO: Implement actual logic\n"
            if "{" in path_str and "}" in path_str: # Templated path
                path_for_decorator = path_str.lstrip('/')
                resource_definitions_list.append(f"@app.resource(\"{path_for_decorator}\")\n{func_def_str}")
            else: # Static path
                static_resource_tuples.append((func_name, path_str))
                resource_definitions_list.append(func_def_str)
    return resource_names, static_resource_tuples, "\n\n".join(resource_definitions_list)

def generate_mcp_tools(spec: Dict[str, Any]) -> Tuple[List[str], str]:
    tool_names, tool_definitions = [], []
    schemas_root = spec.get('components',{}).get('schemas',{})
    comp_schema_names = list(schemas_root.keys())
    for path_str, path_item in spec.get('paths',{}).items():
        for method in ['post','put','delete']:
            if method in path_item:
                op_spec = path_item[method]
                func_name = _generate_function_name(method, path_str, op_spec.get('operationId'))
                tool_names.append(func_name)
                args = ["ctx: fmcp.Context"]
                param_args = []
                for p in op_spec.get('parameters',[]):
                    # All parameter names (path, query, etc.) are snake_cased after sanitization for consistency
                    param_name = _to_snake_case(_sanitize_python_identifier(p['name']))
                    param_args.append(f"{param_name}: {oas_schema_to_python_type(p.get('schema',{}),schemas_root)}{'' if p.get('required',False) else ' | None = None'}")
                args.extend(param_args)
                if 'requestBody' in op_spec:
                    rb_spec,sch_spec = op_spec['requestBody'],op_spec['requestBody'].get('content',{}).get('application/json',{}).get('schema',{})
                    if sch_spec:
                        body_type = oas_schema_to_python_type(sch_spec,schemas_root)
                        body_name = "payload"
                        if "$ref" in sch_spec and sch_spec["$ref"].split("/")[-1] in comp_schema_names: body_name = _to_snake_case(sch_spec["$ref"].split("/")[-1])
                        elif body_type in comp_schema_names: body_name = _to_snake_case(body_type)
                        args.append(f"{body_name}: {body_type}{'' if rb_spec.get('required',True) else ' | None = None'}")
                ret_ann = "None" if '204' in op_spec.get('responses',{}) else next((oas_schema_to_python_type(r['content']['application/json'].get('schema',{}),schemas_root) for c,r in op_spec.get('responses',{}).items() if c in ['200','201','202'] and 'application/json' in r.get('content',{})), "Dict[str,Any]")
                doc = f"{op_spec.get('summary',f'Tool for {method.upper()} {path_str}')}\n\n{op_spec.get('description','')}".strip().replace('\"\"\"','\\"\\"\\"').replace('\n','\n        ')
                tool_definitions.append(f"@app.tool\ndef {func_name}({', '.join(args)}) -> {ret_ann}:\n    \"\"\"{doc}\n    \"\"\"\n    pass # TODO: Implement actual logic\n")
    return tool_names, "\n\n".join(tool_definitions)

def generate_llms_txt(spec: Dict[str, Any], tool_names: List[str]) -> str:
    llms_parts = []
    schemas_root = spec.get('components',{}).get('schemas',{})
    for path_str, path_item in spec.get('paths',{}).items():
        for method in ['post','put','delete']:
            if method in path_item:
                op_spec = path_item[method]
                func_name = _generate_function_name(method, path_str, op_spec.get('operationId'))
                if func_name in tool_names:
                    desc_parts = [f"## {func_name}", op_spec.get('summary',op_spec.get('description','No description')) or "No summary.", "Параметры:"]
                    has_params = False
                    for p in op_spec.get('parameters',[]):
                        param_name_for_llms = _sanitize_python_identifier(p['name']) if p.get('in') == 'path' else _to_snake_case(p['name'])
                        desc_parts.append(f"- {param_name_for_llms}: {_get_llm_type_string(p.get('schema',{}),spec)}{'' if p.get('required',False) else ' (опционально)'}"); has_params=True
                    if 'requestBody' in op_spec:
                        rb_spec,sch = op_spec['requestBody'],op_spec['requestBody'].get('content',{}).get('application/json',{}).get('schema',{})
                        if sch:
                            body_name = "payload"; ref_name = sch["$ref"].split("/")[-1] if "$ref" in sch else None
                            if ref_name and ref_name in schemas_root: body_name = _to_snake_case(ref_name)
                            desc_parts.append(f"- {body_name}: {_get_llm_type_string(sch,spec)}{'' if rb_spec.get('required',True) else ' (опционально)'}"); has_params=True
                    if not has_params: desc_parts.append("- Нет параметров")
                    llms_parts.append("\n".join(desc_parts))
    return "\n\n\n".join(llms_parts)

def generate_mcp_server_code(spec: Dict[str, Any], mcp_app_details: Dict[str, str], transport: str) -> Tuple[str, List[str]]:
    future_imp = "from __future__ import annotations\n\n"
    std_imports_list = [
        "import sys",
        "import fastmcp as fmcp",
        "from pydantic import BaseModel",
        "from typing import List, Optional, Any, Dict",
    ]
    std_imports_block = "\n".join(std_imports_list) + "\n\n"

    models_code_str = generate_pydantic_models(spec.get('components',{}).get('schemas',{}))
    all_resource_names, static_resource_tuples, resources_code_definitions = generate_mcp_resources(spec)
    tool_names, tools_code_str = generate_mcp_tools(spec)

    app_init_code = f"app = fmcp.FastMCP(\n"
    app_init_code += f"    name=\"{mcp_app_details.get('name','GeneratedAPI')}\",\n"
    app_init_code += f"    version=\"{mcp_app_details.get('version','0.1.0')}\",\n"
    app_init_code += f"    llm_tools=[]\n)\n"

    reg_code = "\n\n# Register static resources explicitly\n"
    if static_resource_tuples:
        for name, path in static_resource_tuples:
            reg_code += f"if '{name}' in locals():\n    app.add_resource({name}, path_override=\"{path}\")\n"
    else:
        reg_code += "# No static resources to register explicitly\n"

    main_exec_block = {"stdio": '\nif __name__ == "__main__":\n    app.run_stdio()\n',
                       "sse": '\nif __name__ == "__main__":\n    app.run_sse()\n',
                       "http": '\nif __name__ == "__main__":\n    try:\n        import uvicorn\n    except ImportError:\n        print(\'Error: "uvicorn" is not installed. Please install it to use the http transport (e.g., pip install uvicorn)\')\n        sys.exit(1)\n    uvicorn.run(app.http_app, host="0.0.0.0", port=8000)\n'
                      }.get(transport, "")

    code_str = future_imp + std_imports_block
    if models_code_str.strip(): code_str += models_code_str
    code_str += app_init_code # app_init_code ends with \n so models_code_str should ensure it ends with \n\n if not empty

    if resources_code_definitions.strip(): code_str += "\n\n" + resources_code_definitions
    if tools_code_str.strip(): code_str += "\n\n" + tools_code_str
    if static_resource_tuples : code_str += reg_code # Add registration code only if there are static resources

    if main_exec_block.strip(): code_str += main_exec_block
    else: code_str += "\n"

    return code_str, tool_names
