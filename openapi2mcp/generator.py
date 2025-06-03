import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from .parser import (HttpMethod, OpenAPIParser, Operation, Parameter,
                     ParameterLocation, Schema)

logger = logging.getLogger(__name__)

# Python keywords that cannot be used as variable names
PYTHON_KEYWORDS = [
    "False", "None", "True", "and", "as", "assert", "async", "await",
    "break", "class", "continue", "def", "del", "elif", "else", "except",
    "finally", "for", "from", "global", "if", "import", "in", "is",
    "lambda", "nonlocal", "not", "or", "pass", "raise", "return", "try",
    "while", "with", "yield"
]

def sanitize_variable_name(name: str) -> str:
    """
    Sanitizes a string to be a valid Python variable name.
    - Replaces invalid characters with underscores.
    - Prepends an underscore if it starts with a digit or is empty.
    - Appends an underscore if it's a Python keyword.
    """
    if not isinstance(name, str):
        name = str(name)

    # Replace invalid characters (anything not a letter, digit, or underscore)
    # Also, ensure it doesn't start with a digit by prepending underscore if so.
    name = re.sub(r'[^0-9a-zA-Z_]', '_', name)

    if not name: # if name became empty after sanitization
        return "_var"

    if name[0].isdigit():
        name = "_" + name

    # Ensure it's not a keyword
    if name in PYTHON_KEYWORDS:
        name += "_"
    return name


class MCPGenerator:
    def __init__(self, parser: OpenAPIParser, transport: str = "stdio", mount_path: str = ""):
        self.parser = parser
        self.transport = transport
        self.mount_path = mount_path.strip("/") # Ensure no leading/trailing slashes for mount_path
        self._model_name_map: Dict[str, str] = {} # Maps original schema name to Pydantic model name
        self._generated_model_names: Set[str] = set() # Tracks names of models already generated

    def generate(self, output_file: str) -> bool:
        """Orchestrates the code generation and writing to file."""
        logger.info(f"Starting MCP server code generation for transport: {self.transport}")
        try:
            # Pre-populate model name map to handle dependencies correctly
            self._prepare_model_name_map()

            code = self._generate_code()
            output_path = Path(output_file)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            with open(output_path, "w") as f:
                f.write(code)
            logger.info(f"MCP server code successfully generated at {output_path}")
            return True
        except Exception as e:
            logger.error(f"Error generating MCP server code: {e}", exc_info=True)
            return False

    def _prepare_model_name_map(self):
        """First pass: collect all schema names and map them to valid Pydantic class names."""
        for schema_name in self.parser.schemas.keys():
            pydantic_model_name = self._sanitize_pydantic_model_name(schema_name)
            self._model_name_map[schema_name] = pydantic_model_name


    def _sanitize_pydantic_model_name(self, name: str) -> str:
        """ Sanitizes a schema name to be a valid Pydantic model class name.
            Ensures it starts with uppercase and is a valid Python identifier.
        """
        # Parser's sanitize_name makes it a valid identifier.
        # Here, ensure it's suitable for a class name (e.g., CamelCase).
        name = self.parser._sanitize_name(name) # Use parser's base sanitization
        if not name: return "_Model" # Should not happen if parser's sanitize_name is robust

        # Ensure CamelCase/PascalCase - simple version: capitalize first letter
        # More complex logic could split by underscores and capitalize parts.
        if '_' in name: # e.g. my_schema -> MySchema
            name = "".join(part.capitalize() or '_' for part in name.split('_'))

        if not name[0].isupper():
             name = name[0].upper() + name[1:]

        if name in PYTHON_KEYWORDS: # Should be caught by parser's sanitize, but double check
            name += "Model" # Append "Model" to avoid keyword clash, e.g. "List" -> "ListModel"
        return name


    def _generate_code(self) -> str:
        """Calls the other _generate_* internal methods to build the full code string."""
        imports = self._generate_imports()
        models = self._generate_models() # This needs self._model_name_map to be populated
        app_init = self._generate_app_init()
        resources = self._generate_resources()
        tools = self._generate_tools()
        main_block = self._generate_main()

        return f"{imports}\n\n{models}\n\n{app_init}\n\n{resources}\n\n{tools}\n\n{main_block}\n"

    def _generate_imports(self) -> str:
        """Generates necessary import statements."""
        uses_datetime = False
        uses_date = False
        # Pydantic V2 doesn't need List, Optional, Any, Dict from typing for simple cases
        # but good to have them for more complex scenarios or if user adds custom types.

        type_strings_to_check = []
        for schema in self.parser.schemas.values():
            type_strings_to_check.append(schema.type)
            for prop_def in schema.properties.values():
                type_strings_to_check.append(prop_def['type'] if isinstance(prop_def, dict) else str(prop_def))

        for op in self.parser.operations:
            for param in op.parameters:
                type_strings_to_check.append(param.type)
            if op.request_body_schema:
                type_strings_to_check.append(op.request_body_schema.type)
            if op.response_schema:
                type_strings_to_check.append(op.response_schema.type)

        for type_str in type_strings_to_check:
            s_type_str = str(type_str) # Ensure it's a string
            if "datetime" in s_type_str: uses_datetime = True
            if "date" in s_type_str and "datetime" not in s_type_str: uses_date = True # Avoid date if datetime is already true for 'date-time'

        import_statements = [
            "import logging",
            "from typing import List, Optional, Any, Dict, Union", # Keep for robustness
            "from pydantic import BaseModel, Field",
            "from mcp import AbstractResource, AbstractTool, BlockingStdioTransport, Server, Message, Context"
        ]
        if uses_datetime:
            import_statements.append("from datetime import datetime")
        if uses_date:
            import_statements.append("from datetime import date")

        if self.transport == "google_pubsub":
            import_statements.append("from mcp.transport.gcp_pubsub import GooglePubSubTransport")

        import_statements.sort()
        return "\n".join(import_statements) + "\n\nlogger = logging.getLogger(__name__)"


    def _map_openapi_type_to_pydantic(self, openapi_type_info: Union[str, Dict[str, Any]], is_optional: bool = False) -> str:
        """Maps OpenAPI type (and format) to Pydantic field types."""
        final_type_str = "Any" # Default

        if isinstance(openapi_type_info, str): # Already a string, likely a schema name or basic python type
            type_str = openapi_type_info

            list_match = re.match(r"List\[(.+)\]", type_str)
            dict_match = re.match(r"Dict\[str, (.+)\]", type_str) # Assuming Dict[str, Type]

            if list_match:
                inner_type = list_match.group(1)
                mapped_inner_type = self._map_openapi_type_to_pydantic(inner_type)
                final_type_str = f"List[{mapped_inner_type}]"
            elif dict_match:
                value_type = dict_match.group(1)
                mapped_value_type = self._map_openapi_type_to_pydantic(value_type)
                final_type_str = f"Dict[str, {mapped_value_type}]"
            elif type_str in self._model_name_map: # It's a reference to another schema
                final_type_str = self._model_name_map[type_str]
            elif type_str in ["str", "int", "float", "bool", "datetime", "date", "bytes", "Any"]:
                final_type_str = type_str
            else: # Unrecognized string, could be a schema name not found in map (should not happen if _prepare_model_name_map ran)
                  # Or an inline enum/literal type if parser supports that.
                  # Fallback: sanitize and use as is, or default to Any.
                  # For now, assume it's a model name that should have been mapped.
                  # If it's from schema.type directly for a non-object schema, it might be like "string".
                logger.warning(f"Unmapped type string '{type_str}' encountered. Defaulting to Any or using sanitized name.")
                # Try to map basic OpenAPI types if they appear here directly
                if type_str == "string": final_type_str = "str"
                elif type_str == "integer": final_type_str = "int"
                elif type_str == "number": final_type_str = "float"
                elif type_str == "boolean": final_type_str = "bool"
                else: final_type_str = self._sanitize_pydantic_model_name(type_str) # Assume it's a schema name

        elif isinstance(openapi_type_info, dict): # Property definition from parser
            oas_type = openapi_type_info.get("type")

            if openapi_type_info.get("is_ref"): # Property referencing another schema
                ref_name = oas_type # Parser puts sanitized schema name into 'type' for refs
                final_type_str = self._model_name_map.get(ref_name, self._sanitize_pydantic_model_name(ref_name))
            elif oas_type == "string": final_type_str = "str" # format handled by parser into specific types like date/datetime if applicable
            elif oas_type == "integer": final_type_str = "int"
            elif oas_type == "number": final_type_str = "float"
            elif oas_type == "boolean": final_type_str = "bool"
            elif oas_type == "array":
                items_def = openapi_type_info.get("items", {"type": "Any"}) # Default for items
                item_type_str = self._map_openapi_type_to_pydantic(items_def) # Recursive call
                final_type_str = f"List[{item_type_str}]"
            elif oas_type == "object":
                # Inline object definition. Could be Dict[str, Any] or a nested anonymous model.
                # For simplicity, map to Dict[str, Any] or use additionalProperties if defined.
                if "additionalProperties" in openapi_type_info:
                    ap_def = openapi_type_info["additionalProperties"]
                    if isinstance(ap_def, dict): # Schema for additionalProperties
                        ap_type = self._map_openapi_type_to_pydantic(ap_def)
                        final_type_str = f"Dict[str, {ap_type}]"
                    elif isinstance(ap_def, bool) and ap_def: # additionalProperties: true
                        final_type_str = "Dict[str, Any]"
                    else: # additionalProperties: false or not a schema
                        final_type_str = "Dict[str, Any]" # Or raise error/handle specific model
                elif openapi_type_info.get("is_inline_complex"): # Hint from _get_python_type
                    # This means it's an object with properties but not a named schema.
                    # Ideally, the generator would create an inline Pydantic model for this.
                    # For now, we'll use Dict[str, Any] as a placeholder.
                    # A more advanced generator might create a nested class here.
                    logger.warning(f"Inline complex object found, mapping to Dict[str, Any]. Consider defining as a separate schema.")
                    final_type_str = "Dict[str, Any]"
                else:
                    final_type_str = "Dict[str, Any]"
            # If oas_type is None but there's a ref, it should be handled by 'is_ref' logic.
            # If oas_type is a schema name itself (e.g. from param.type = "MySchemaName")
            elif oas_type in self._model_name_map:
                 final_type_str = self._model_name_map[oas_type]


        if is_optional and not final_type_str.startswith("Optional[") and not final_type_str.startswith("Union["):
            final_type_str = f"Optional[{final_type_str}]"

        return final_type_str


    def _generate_models(self) -> str:
        """Generates Pydantic model definitions from OpenAPI schemas."""
        model_strs = []
        # self._model_name_map should be populated by _prepare_model_name_map

        for schema_name, schema_obj in self.parser.schemas.items():
            # Only generate for schemas that are meant to be objects with properties
            # The parser sets schema.type to the schema name if it's an object type.
            # Or if it's a complex type that should become a Pydantic model.
            # Simple types or aliases (e.g. UserId = str) won't be BaseModel.
            # Check if schema.type is the same as the intended model name, or if it has properties.
            is_object_schema = schema_obj.type == schema_name or schema_obj.properties

            if is_object_schema and schema_name not in self._generated_model_names:
                 model_str = self._generate_model(schema_obj)
                 if model_str:
                    model_strs.append(model_str)
                    self._generated_model_names.add(schema_name) # Mark as generated

        return "\n\n".join(model_strs)

    def _generate_model(self, schema: Schema) -> str:
        """Generates a single Pydantic model class string."""
        class_name = self._model_name_map.get(schema.name)
        if not class_name:
            logger.error(f"Could not find mapped Pydantic name for schema: {schema.name}. Skipping model generation.")
            return ""

        fields = []
        for prop_name, prop_def_raw in schema.properties.items():
            field_name = sanitize_variable_name(prop_name)
            is_required = prop_name in schema.required_properties

            # prop_def_raw can be a string (type name) or dict (full schema for property)
            pydantic_type = self._map_openapi_type_to_pydantic(prop_def_raw, is_optional=not is_required)

            field_args = []
            if not is_required:
                # Pydantic V2 handles Optional[...] automatically with `= None`
                # So, `pydantic_type` will already be Optional[ActualType] via `is_optional` flag.
                field_args.append("default=None")
            else:
                # For required fields, if you want to use Field() e.g. for description
                field_args.append("default=...") # Ellipsis for required fields in Pydantic Field

            description = None
            if isinstance(prop_def_raw, dict):
                description = prop_def_raw.get("description")

            if description:
                escaped_description = description.replace('"', '\\"')
                field_args.append(f'description="{escaped_description}"')

            # Add alias if original prop_name is different from field_name (e.g. due to sanitization for keywords)
            # For now, this is not strictly implemented, assuming field_name is used directly.
            # if field_name != prop_name:
            #    field_args.append(f'alias="{prop_name}"')


            if field_args: # Using Field(...)
                 # If default=None, pydantic_type should be Optional[X]
                 # If default=..., pydantic_type should be X (not Optional)
                 # _map_openapi_type_to_pydantic handles making it Optional if not is_required
                 actual_type_for_annotation = pydantic_type
                 if not is_required and not actual_type_for_annotation.startswith("Optional["):
                     actual_type_for_annotation = f"Optional[{actual_type_for_annotation}]"
                 elif is_required and actual_type_for_annotation.startswith("Optional["): # Strip Optional if required
                     match = re.match(r"Optional\[(.+)\]", actual_type_for_annotation)
                     if match: actual_type_for_annotation = match.group(1)


                 fields.append(f"    {field_name}: {actual_type_for_annotation} = Field({', '.join(field_args)})")
            else: # Simple annotation: name: type
                 fields.append(f"    {field_name}: {pydantic_type}")


        if not fields : # Pydantic model needs at least 'pass'
             fields.append("    pass  # No properties defined for this model.")

        model_docstring_content = schema.description or f"Pydantic model for {schema.name}"
        model_docstring = f'    """\n    {model_docstring_content}\n    """'

        model_def = f"class {class_name}(BaseModel):\n"
        if model_docstring: model_def += f"{model_docstring}\n"
        model_def += "\n".join(fields)

        return model_def

    def _generate_app_init(self) -> str:
        return "app = Server()"

    def _generate_resources(self) -> str:
        resource_strs = [self._generate_resource(op) for op in self.parser.operations if op.method == HttpMethod.GET]
        return "\n\n".join(filter(None, resource_strs))

    def _generate_resource(self, operation: Operation) -> str:
        class_name_base = self.parser._sanitize_name(operation.operation_id) # Use parser's sanitize
        class_name = (class_name_base[0].upper() + class_name_base[1:] if class_name_base else "") + "Resource"
        if not class_name or not class_name[0].isupper(): class_name = "_" + class_name

        response_model_name = "None"
        if operation.response_schema:
            # Use the mapped Pydantic model name
            # The type might be like "List[MyModel]"
            response_model_name = self._map_openapi_type_to_pydantic(operation.response_schema.type)


        resource_path = f"{self.mount_path}/{operation.operation_id}" if self.mount_path else operation.operation_id
        class_docstring = f'    """Resource for: {operation.summary or operation.operation_id}"""'

        param_extraction_lines = []
        param_usage_comments = []
        for param in operation.parameters:
            var_name = sanitize_variable_name(param.name)
            param_type_hint = self._map_openapi_type_to_pydantic(param.type, is_optional=not param.required)

            # In MCP, query params for resources are in ctx.payload
            if param.required:
                param_extraction_lines.append(f"        {var_name}: {param_type_hint} = ctx.payload['{param.name}']")
            else:
                param_extraction_lines.append(f"        {var_name}: {param_type_hint} = ctx.payload.get('{param.name}')")
            param_usage_comments.append(var_name)


        param_extraction_str = "\n".join(param_extraction_lines) or "        # No parameters to extract directly from payload for this resource."
        param_usage_str = ", ".join(param_usage_comments)

        return f"""
@Server.resource(path="{resource_path}")
class {class_name}(AbstractResource[{response_model_name}]):
{class_docstring}
    async def query(self, ctx: Context, **kwargs) -> {response_model_name}: # Added Context type hint
        logger.info(f"Executing resource: {class_name} with query params: {{ctx.payload}}")
{param_extraction_str}

        # --- Begin User-Implemented Logic ---
        # Use extracted parameters ({param_usage_str}) to fetch/compute result.
        raise NotImplementedError("Resource logic not implemented by the user.")
        # Example: return {response_model_name}(...)
        # --- End User-Implemented Logic ---
"""

    def _generate_tools(self) -> str:
        tool_strs = [self._generate_tool(op) for op in self.parser.operations if op.method != HttpMethod.GET]
        return "\n\n".join(filter(None, tool_strs))

    def _generate_tool(self, operation: Operation) -> str:
        class_name_base = self.parser._sanitize_name(operation.operation_id)
        class_name = (class_name_base[0].upper() + class_name_base[1:] if class_name_base else "") + "Tool"
        if not class_name or not class_name[0].isupper(): class_name = "_" + class_name

        request_model_name = "BaseModel" # Default for tools without a specific request body
        if operation.request_body_schema:
            # Map to the Pydantic model name
            request_model_name = self._map_openapi_type_to_pydantic(operation.request_body_schema.type)
        elif operation.parameters: # No explicit request body, but parameters exist
            # If parameters are only path, still use BaseModel for arg type.
            # If query/header params, user might need to create a model or access via ctx.
            # For now, if no body, arg is BaseModel. User can inspect ctx.
            pass


        response_model_name = "None"
        if operation.response_schema:
            response_model_name = self._map_openapi_type_to_pydantic(operation.response_schema.type)

        tool_name_mcp = operation.operation_id
        class_docstring = f'    """Tool for: {operation.summary or operation.operation_id} (Method: {operation.method.value.upper()}, Path: {operation.path})"""'

        # Guidance for parameters (path, query, header)
        param_guidance_lines = ["# This tool might use the following parameters not part of the direct input model:"]
        has_other_params = False
        for p in operation.parameters:
            # Request body schema (if any) is handled by `arg: {request_model_name}`
            # Path, query, header params might need to be handled from ctx or kwargs
            if p.location != ParameterLocation.PATH: # Path params are part of URL construction
                 p_type_hint = self._map_openapi_type_to_pydantic(p.type, is_optional=not p.required)
                 line = f"#   - {p.name} ({p.location.value}, type: {p_type_hint})"
                 if not p.required: line += " (optional)"
                 param_guidance_lines.append(line)
                 has_other_params = True

        param_guidance = "\n        ".join(param_guidance_lines) if has_other_params else "# All parameters are expected to be in the input model or path."

        # Construct placeholder URL for HTTP call guidance
        url_path_template = operation.path
        path_param_vars = []
        for p_op_param in operation.parameters:
            if p_op_param.location == ParameterLocation.PATH:
                sanitized_param_name = sanitize_variable_name(p_op_param.name)
                url_path_template = url_path_template.replace(f"{{{p_op_param.name}}}", f"{{{sanitized_param_name}}}")
                # Assume path params might come from input model `arg` if not a dedicated request body
                path_param_vars.append(f'{sanitized_param_name}=arg.{sanitized_param_name} if hasattr(arg, "{sanitized_param_name}") else "TODO_path_param_{sanitized_param_name}"')


        url_fstring_prefix = "f" if "{ rumoured_dead_name_for_a_variable_that_should_not_exist }" in url_path_template else "" # Hack to force f-string if needed by var names
        if any(p.location == ParameterLocation.PATH for p in operation.parameters): url_fstring_prefix = "f"


        # Tool execute method body
        execute_body = f"""
        logger.info(f"Executing tool: {class_name} with input: {{arg}}")
        {param_guidance}

        # Example: Accessing path parameters if they were part of `arg`
        # {(', '.join(path_param_vars))} # This line is illustrative

        # --- Begin User-Implemented Logic ---
        # Replace with actual service call. Example for an HTTP endpoint:
        # import httpx
        # async with httpx.AsyncClient() as client:
        #     response = await client.{operation.method.value.lower()}(
        #         url={url_fstring_prefix}"http://your-api-base{url_path_template}",
        #         json=arg.model_dump(exclude_none=True) if isinstance(arg, BaseModel) and arg != BaseModel() else None,
        #         # params={{key: val for key, val in arg.model_dump().items() if key not in path_params and val is not None}} # if query params are in arg
        #     )
        #     response.raise_for_status()
        #     if "{response_model_name}" != "None":
        #         return {response_model_name}(**response.json())
        #     return None
        raise NotImplementedError("Tool logic not implemented by the user.")
        # --- End User-Implemented Logic ---
"""
        return f"""
@Server.tool(name="{tool_name_mcp}")
class {class_name}(AbstractTool[{request_model_name}, {response_model_name}]):
{class_docstring}
    async def execute(self, arg: {request_model_name}, ctx: Context) -> {response_model_name}: # Added Context
{execute_body}
"""

    def _generate_function_params(self, operation: Operation, include_ctx: bool = False) -> str:
        # This method seems less used now as Resources/Tools have fixed signatures.
        # It could be useful for docstrings or internal helper functions if needed.
        # For now, let's ensure it aligns with how model types are resolved.
        params_list = []
        if include_ctx: params_list.append("ctx: Context")

        for param in operation.parameters:
            param_name = sanitize_variable_name(param.name)
            param_type = self._map_openapi_type_to_pydantic(param.type, is_optional=not param.required)
            if param.required:
                params_list.append(f"{param_name}: {param_type}")
            else:
                # _map_openapi_type_to_pydantic already made it Optional[T]
                params_list.append(f"{param_name}: {param_type} = None")

        if operation.request_body_schema:
            body_model_name = self._map_openapi_type_to_pydantic(operation.request_body_schema.type)
            # Sanitize name for payload parameter
            payload_param_name = sanitize_variable_name(operation.request_body_schema.name + "_payload")
            params_list.append(f"{payload_param_name}: {body_model_name}")

        return ", ".join(params_list)


    def _generate_main(self) -> str:
        transport_details = {
            "stdio": "transport = BlockingStdioTransport()",
            "google_pubsub": """
    project_id = "YOUR_GCP_PROJECT_ID"  # Replace
    mcp_subscription_id = "YOUR_MCP_PUBSUB_SUBSCRIPTION"  # Replace
    agent_topic_id = "YOUR_AGENT_PUBSUB_TOPIC"  # Replace
    transport = GooglePubSubTransport(
        project_id=project_id,
        mcp_subscription_id=mcp_subscription_id,
        agent_topic_id=agent_topic_id,
    )"""
        }
        transport_config = transport_details.get(self.transport, "transport = BlockingStdioTransport() # Default or unrecognized transport")
        if self.transport not in transport_details:
            logger.warning(f"Unsupported transport '{self.transport}'. Defaulting to Stdio.")

        return f"""
def main():
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    logger.info("Starting MCP server...")

{transport_config}

    # Assuming 'app' is the Server instance, defined globally after imports.
    # Resources and Tools are registered to 'app' using decorators.
    app.serve(transport=transport)

if __name__ == "__main__":
    main()
"""

    def generate_llms_txt(self, output_dir_str: str) -> bool:
        logger.info("Generating llms.txt content...")
        # Ensure model name map is fresh if called standalone
        if not self._model_name_map: self._prepare_model_name_map()

        content_lines = [
            "This document describes the tools and resources available through an MCP server, generated from an OpenAPI specification.",
            "---"
        ]

        # Resources
        content_lines.append("Available Resources (for querying data, typically via GET):")
        resource_ops = [op for op in self.parser.operations if op.method == HttpMethod.GET]
        if not resource_ops:
            content_lines.append("  No resources (GET operations) defined.")
        else:
            for op in resource_ops:
                res_path = f"{self.mount_path}/{op.operation_id}" if self.mount_path else op.operation_id
                content_lines.append(f"\nResource Path (for GET requests): {res_path}")
                if op.summary: content_lines.append(f"  Summary: {op.summary}")

                response_type_str = "None"
                if op.response_schema: response_type_str = self._map_openapi_type_to_pydantic(op.response_schema.type)
                content_lines.append(f"  Returns: {response_type_str}")

                if op.parameters:
                    content_lines.append("  Query Parameters (passed in request payload):")
                    for param in op.parameters: # Assuming all params for GET resource are query params
                        if param.location == ParameterLocation.QUERY: # Only list query for resource payload
                            p_type = self._map_openapi_type_to_pydantic(param.type, is_optional=not param.required)
                            req_opt = "required" if param.required else "optional"
                            desc = f" - {param.description}" if param.description else ""
                            content_lines.append(f"    - {param.name} (type: {p_type}, {req_opt}){desc}")
                else: content_lines.append("  No specific query parameters.")

        content_lines.append("\n---\n")

        # Tools
        content_lines.append("Available Tools (for actions/commands):")
        tool_ops = [op for op in self.parser.operations if op.method != HttpMethod.GET]
        if not tool_ops:
            content_lines.append("  No tools (non-GET operations) defined.")
        else:
            for op in tool_ops:
                tool_name_mcp = op.operation_id
                content_lines.append(f"\nTool Name: {tool_name_mcp}")
                content_lines.append(f"  Action: Corresponds to OpenAPI operation {op.method.value.upper()} {op.path}")
                if op.summary: content_lines.append(f"  Summary: {op.summary}")

                input_model_str = "None"
                if op.request_body_schema:
                    input_model_str = self._map_openapi_type_to_pydantic(op.request_body_schema.type)
                content_lines.append(f"  Input Model (for tool argument `arg`): {input_model_str}")

                # Add info about other parameters (path, query, header) if any
                other_params = [p for p in op.parameters if p.location != ParameterLocation.BODY] # Body handled by input model
                if other_params:
                    content_lines.append("  Additional Parameters (contextual, e.g. for URL path or query if not in input model):")
                    for param in other_params:
                        p_type = self._map_openapi_type_to_pydantic(param.type, is_optional=not param.required)
                        req_opt = "required" if param.required else "optional"
                        desc = f" - {param.description}" if param.description else ""
                        content_lines.append(f"    - {param.name} ({param.location.value}, type: {p_type}, {req_opt}){desc}")

                response_type_str = "None"
                if op.response_schema: response_type_str = self._map_openapi_type_to_pydantic(op.response_schema.type)
                content_lines.append(f"  Returns: {response_type_str}")

        content_lines.append("\n---\nNote: Model names refer to Pydantic models in the generated server code.")

        try:
            output_dir = Path(output_dir_str)
            output_dir.mkdir(parents=True, exist_ok=True)
            llms_txt_path = output_dir / "llms.txt"
            with open(llms_txt_path, "w") as f:
                f.write("\n".join(content_lines))
            logger.info(f"llms.txt successfully generated at {llms_txt_path}")
            return True
        except Exception as e:
            logger.error(f"Error generating llms.txt: {e}", exc_info=True)
            return False
