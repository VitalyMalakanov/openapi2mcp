import json
import logging
import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Union

logger = logging.getLogger(__name__)


class OpenAPIParserError(Exception):
    """Custom exception for OpenAPI parsing errors."""

    pass


class HttpMethod(Enum):
    GET = "get"
    POST = "post"
    PUT = "put"
    DELETE = "delete"
    PATCH = "patch"
    OPTIONS = "options"
    HEAD = "head"


class ParameterLocation(Enum):
    PATH = "path"
    QUERY = "query"
    HEADER = "header"
    COOKIE = "cookie"


@dataclass
class Parameter:
    name: str
    location: ParameterLocation
    type: str
    required: bool
    description: Optional[str] = None


@dataclass
class Schema:
    name: str
    type: str
    properties: Dict[str, Any] = field(default_factory=dict)
    required_properties: List[str] = field(default_factory=list)
    description: Optional[str] = None
    raw_schema: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Operation:
    operation_id: str
    method: HttpMethod
    path: str
    summary: Optional[str] = None
    description: Optional[str] = None
    parameters: List[Parameter] = field(default_factory=list)
    request_body_schema: Optional[Schema] = None
    response_schema: Optional[Schema] = None
    tags: List[str] = field(default_factory=list)


class OpenAPIParser:
    def __init__(self):
        self.schemas: Dict[str, Schema] = {}
        self.operations: List[Operation] = []
        self._visited_refs: Set[str] = set()

    def parse_file(self, filepath: Path) -> None:
        """Parses an OpenAPI specification file (JSON or YAML)."""
        try:
            with open(filepath, "r") as f:
                if filepath.suffix in (".yaml", ".yml"):
                    import yaml

                    spec = yaml.safe_load(f)
                elif filepath.suffix == ".json":
                    spec = json.load(f)
                else:
                    raise OpenAPIParserError(
                        f"Unsupported file format: {filepath.suffix}. Please use JSON or YAML."
                    )
            self._parse_spec(spec)
        except FileNotFoundError:
            raise OpenAPIParserError(f"File not found: {filepath}")
        except Exception as e:
            raise OpenAPIParserError(f"Error parsing OpenAPI file {filepath}: {e}")

    def _parse_spec(self, spec: Dict[str, Any]) -> None:
        """Parses the OpenAPI specification content."""
        if "components" in spec and "schemas" in spec["components"]:
            for schema_name, schema_def in spec["components"]["schemas"].items():
                self._parse_schema(schema_name, schema_def, spec)

        if "paths" in spec:
            for path, path_item in spec["paths"].items():
                self._parse_path(path, path_item, spec)

    def _resolve_ref(self, ref: str, spec: Dict[str, Any]) -> Dict[str, Any]:
        """Resolves a JSON reference string."""
        if not ref.startswith("#/"):
            raise OpenAPIParserError(f"Unsupported reference format: {ref}")

        if ref in self._visited_refs:
            # Attempt to return already parsed schema if available to avoid infinite recursion on circular refs
            # This might need more sophisticated handling for complex circular dependencies
            schema_name = self._extract_schema_name(ref)
            if schema_name and schema_name in self.schemas:
                 # Return a minimal representation or a marker that this is a circular ref
                return {"type": "object", "x-circular-ref": schema_name}
            # Fallback or raise error if not handled well
            # For now, we'll proceed, but this is a point of potential infinite recursion
            # logger.warning(f"Re-visiting ref: {ref}. Potential circular dependency.")
            pass # Allow re-visiting for now, simple cycle breaking above.

        self._visited_refs.add(ref)

        parts = ref[2:].split("/")
        current = spec
        for part in parts:
            if isinstance(current, dict) and part in current:
                current = current[part]
            elif isinstance(current, list) and part.isdigit() and int(part) < len(current):
                current = current[int(part)]
            else:
                # If we encounter an unresolvable part of the ref AFTER already processing it,
                # it might indicate a deeper issue or a truly missing part.
                # However, if it's just a part of a circular ref that's not fully defined yet,
                # this could be problematic.
                # For now, let's assume it's resolvable or handled by initial schema parsing.
                # logger.warning(f"Could not resolve part '{part}' in reference '{ref}'")
                # To prevent crashing on partially defined circular refs, return a generic dict.
                # This part might need refinement based on how circular refs are structured.
                # return {"type": "object", "description": f"Unresolved reference part: {part} in {ref}"}
                raise OpenAPIParserError(f"Could not resolve reference: {ref}")


        if "$ref" in current: # Handle nested refs
            nested_ref_val = current["$ref"]
            resolved_nested = self._resolve_ref(nested_ref_val, spec)
            self._visited_refs.remove(ref) # Remove parent ref after resolving child
            return resolved_nested

        self._visited_refs.remove(ref) # remove after successful resolution
        return current

    def _parse_schema(
        self, schema_name: str, schema_def: Dict[str, Any], spec: Dict[str, Any]
    ) -> Schema:
        """Parses a schema definition, handling references."""
        original_ref = f"#/components/schemas/{schema_name}" # Assuming schema_name is raw here

        # Sanitize schema_name early for consistent dictionary keys
        clean_schema_name_for_dict_key = self._sanitize_name(schema_name)

        if original_ref in self._visited_refs and clean_schema_name_for_dict_key in self.schemas:
            return self.schemas[clean_schema_name_for_dict_key]

        self._visited_refs.add(original_ref)

        if clean_schema_name_for_dict_key in self.schemas:
             self._visited_refs.remove(original_ref)
             return self.schemas[clean_schema_name_for_dict_key]

        current_schema_def = schema_def
        if "$ref" in current_schema_def:
            resolved_schema_def = self._resolve_ref(current_schema_def["$ref"], spec)
            current_schema_def = resolved_schema_def
            # If the original schema_def was just a ref, its name might be derived from the ref.
            # However, schema_name parameter is what was passed from components/schemas key.

        schema_type = current_schema_def.get("type", "object")
        properties = {}
        required_properties = current_schema_def.get("required", [])
        description = current_schema_def.get("description")

        if "properties" in current_schema_def:
            for prop_name, prop_def in current_schema_def["properties"].items():
                if "$ref" in prop_def:
                    ref_path = prop_def["$ref"]
                    try:
                        resolved_prop_def = self._resolve_ref(ref_path, spec)
                        ref_schema_name = self._extract_schema_name(ref_path) # Gets sanitized name
                        if ref_schema_name:
                            if ref_schema_name not in self.schemas:
                                if ref_path.startswith("#/components/schemas/"):
                                    raw_ref_schema_name = ref_path.split('/')[-1] # Get raw name for spec lookup
                                    if spec.get("components", {}).get("schemas", {}).get(raw_ref_schema_name):
                                       self._parse_schema(raw_ref_schema_name, spec["components"]["schemas"][raw_ref_schema_name], spec)
                                    else:
                                        logger.warning(f"Could not find definition for referenced schema: {raw_ref_schema_name}")
                                        properties[prop_name] = {"type": "object", "description": f"Unresolved reference: {ref_path}"}
                                        continue
                                else:
                                    logger.warning(f"Unsupported reference type for property {prop_name}: {ref_path}")
                                    properties[prop_name] = {"type": "object", "description": f"Complex reference: {ref_path}"}
                                    continue
                            properties[prop_name] = {"type": ref_schema_name, "is_ref": True} # Use sanitized name
                        else:
                            properties[prop_name] = self._get_python_type(resolved_prop_def)
                    except OpenAPIParserError as e:
                        logger.warning(f"Could not resolve reference {ref_path} for property {prop_name}: {e}")
                        properties[prop_name] = {"type": "any", "description": f"Unresolved reference: {ref_path}"}
                else:
                    properties[prop_name] = self._get_python_type(prop_def)

        elif schema_type == "array" and "items" in current_schema_def:
            items_def = current_schema_def["items"]
            if "$ref" in items_def:
                ref_path = items_def["$ref"]
                try:
                    resolved_items_def = self._resolve_ref(ref_path, spec)
                    ref_schema_name = self._extract_schema_name(ref_path) # Gets sanitized name
                    if ref_schema_name:
                        if ref_schema_name not in self.schemas :
                             if ref_path.startswith("#/components/schemas/"):
                                raw_ref_schema_name = ref_path.split('/')[-1]
                                if spec.get("components", {}).get("schemas", {}).get(raw_ref_schema_name):
                                    self._parse_schema(raw_ref_schema_name, spec["components"]["schemas"][raw_ref_schema_name], spec)
                                else:
                                    logger.warning(f"Could not find definition for array item's referenced schema: {raw_ref_schema_name}")
                                    schema_type = f"List[Any]"
else:
                                    logger.warning(f"Unsupported reference type for array items: {ref_path}")
                                    schema_type = f"List[Any]"
                        schema_type = f"List[{ref_schema_name}]" # Use sanitized name
                    else:
                        item_type_info = self._get_python_type(resolved_items_def)
                        schema_type = f"List[{item_type_info.get('type', 'Any') if isinstance(item_type_info, dict) else item_type_info}]"

                except OpenAPIParserError as e:
                    logger.warning(f"Could not resolve reference {ref_path} for array items: {e}")
                    schema_type = "List[Any]"
            else:
                item_type_info = self._get_python_type(items_def)
                schema_type = f"List[{item_type_info.get('type', 'Any') if isinstance(item_type_info, dict) else item_type_info}]"

        final_schema_name = self._sanitize_name(schema_name) # Sanitize the original schema_name for the Schema object

        schema = Schema(
            name=final_schema_name,
            type=schema_type if schema_type != "object" or not properties else final_schema_name,
            properties=properties,
            required_properties=required_properties,
            description=description,
            raw_schema=current_schema_def,
        )
        self.schemas[final_schema_name] = schema # Store with sanitized name

        if original_ref in self._visited_refs:
            self._visited_refs.remove(original_ref)
        return schema

    def _parse_path(
        self, path: str, path_item: Dict[str, Any], spec: Dict[str, Any]
    ) -> None:
        """Parses a path item and its operations."""
        for method_str, op_def in path_item.items():
            if method_str.upper() not in HttpMethod.__members__:
                continue

            method = HttpMethod(method_str.lower())
            operation_id = op_def.get("operationId")
            if not operation_id:
                clean_path = path.replace("/", "_").replace("{", "").replace("}", "")
                operation_id = f"{method.value}{clean_path}"
                logger.info(f"Synthesized operationId for {method.value.upper()} {path}: {operation_id}")

            sanitized_op_id = self._sanitize_name(operation_id)

            parameters: List[Parameter] = []
            # Process path-level parameters first
            path_level_params_defs = path_item.get("parameters", [])
            for param_def_or_ref in path_level_params_defs:
                param_def = self._resolve_ref(param_def_or_ref["$ref"], spec) if "$ref" in param_def_or_ref else param_def_or_ref
                parameters.append(self._parse_parameter(param_def, spec))

            # Process operation-level parameters, allowing override by name and location
            op_level_params_defs = op_def.get("parameters", [])
            processed_op_params: List[Parameter] = []
            for param_def_or_ref in op_level_params_defs:
                param_def = self._resolve_ref(param_def_or_ref["$ref"], spec) if "$ref" in param_def_or_ref else param_def_or_ref
                parsed_param = self._parse_parameter(param_def, spec)

                # Check if this parameter (by name and location) was already defined at path level
                overridden = False
                for i, path_param in enumerate(parameters):
                    if path_param.name == parsed_param.name and path_param.location == parsed_param.location:
                        parameters[i] = parsed_param # Override with more specific definition
                        overridden = True
                        break
                if not overridden:
                    processed_op_params.append(parsed_param) # Add as new parameter for this operation

            parameters.extend(processed_op_params) # Add any new (non-overriding) operation parameters


            request_body_schema: Optional[Schema] = None
            if "requestBody" in op_def:
                request_body_def_or_ref = op_def["requestBody"]
                request_body_def = self._resolve_ref(request_body_def_or_ref["$ref"], spec) if "$ref" in request_body_def_or_ref else request_body_def_or_ref

                content = request_body_def.get("content", {})
                json_content = content.get("application/json", content.get("*/*"))
                if json_content and "schema" in json_content:
                    rb_schema_def_or_ref = json_content["schema"]
                    rb_schema_def = self._resolve_ref(rb_schema_def_or_ref["$ref"], spec) if "$ref" in rb_schema_def_or_ref else rb_schema_def_or_ref

                    ref_path = rb_schema_def_or_ref.get("$ref") if isinstance(rb_schema_def_or_ref, dict) else None

                    if ref_path:
                        ref_schema_name = self._extract_schema_name(ref_path) # Sanitized
                        if ref_schema_name:
                            if ref_schema_name not in self.schemas:
                                raw_ref_name = ref_path.split('/')[-1] # For spec lookup
                                self._parse_schema(raw_ref_name, self._resolve_ref(ref_path, spec), spec) # _parse_schema handles storing by sanitized name
                            request_body_schema = self.schemas[ref_schema_name]
                        else:
                            synthetic_name = self._sanitize_name(f"{sanitized_op_id}_RequestBody")
                            request_body_schema = self._parse_schema(synthetic_name, rb_schema_def, spec)
                    else:
                        synthetic_name = self._sanitize_name(f"{sanitized_op_id}_RequestBody")
                        request_body_schema = self._parse_schema(synthetic_name, rb_schema_def, spec)


            response_schema: Optional[Schema] = None
            if "responses" in op_def:
                success_response_def_or_ref = None
                for code, resp_def_ref in op_def["responses"].items():
                    if code.startswith("2"): # Prioritize 2xx responses
                        success_response_def_or_ref = resp_def_ref
                        break

                if success_response_def_or_ref:
                    success_response_def = self._resolve_ref(success_response_def_or_ref["$ref"], spec) if "$ref" in success_response_def_or_ref else success_response_def_or_ref

                    content = success_response_def.get("content", {})
                    json_content = content.get("application/json", content.get("*/*"))
                    if json_content and "schema" in json_content:
                        resp_schema_def_or_ref = json_content["schema"]
                        resp_schema_def = self._resolve_ref(resp_schema_def_or_ref["$ref"], spec) if "$ref" in resp_schema_def_or_ref else resp_schema_def_or_ref

                        ref_path = resp_schema_def_or_ref.get("$ref") if isinstance(resp_schema_def_or_ref, dict) else None

                        if ref_path:
                            ref_schema_name = self._extract_schema_name(ref_path) # Sanitized
                            if ref_schema_name:
                                if ref_schema_name not in self.schemas:
                                     raw_ref_name = ref_path.split('/')[-1]
                                     self._parse_schema(raw_ref_name, self._resolve_ref(ref_path, spec), spec)
                                response_schema = self.schemas[ref_schema_name]
                            else:
                                synthetic_name = self._sanitize_name(f"{sanitized_op_id}_ResponseBody")
                                response_schema = self._parse_schema(synthetic_name, resp_schema_def, spec)
                        else:
                            synthetic_name = self._sanitize_name(f"{sanitized_op_id}_ResponseBody")
                            response_schema = self._parse_schema(synthetic_name, resp_schema_def, spec)

            self.operations.append(
                Operation(
                    operation_id=sanitized_op_id,
                    method=method,
                    path=path,
                    summary=op_def.get("summary"),
                    description=op_def.get("description"),
                    parameters=parameters,
                    request_body_schema=request_body_schema,
                    response_schema=response_schema,
                    tags=op_def.get("tags", []),
                )
            )

    def _parse_parameter(
        self, param_def: Dict[str, Any], spec: Dict[str, Any]
    ) -> Parameter:
        """Parses a parameter definition. Assumes param_def is already resolved if it was a ref."""
        name = param_def["name"]
        location = ParameterLocation(param_def["in"])
        required = param_def.get("required", False)
        description = param_def.get("description")

        param_schema_or_ref = param_def.get("schema")
        param_type = "Any"

        if param_schema_or_ref:
            param_schema = self._resolve_ref(param_schema_or_ref["$ref"], spec) if "$ref" in param_schema_or_ref else param_schema_or_ref

            ref_path = param_schema_or_ref.get("$ref") if isinstance(param_schema_or_ref, dict) else None

            if ref_path: # Check if the schema itself was a reference
                ref_schema_name = self._extract_schema_name(ref_path) # Sanitized
                if ref_schema_name:
                    if ref_schema_name not in self.schemas:
                        raw_ref_name = ref_path.split('/')[-1] # For spec lookup
                        component_schema_def = spec.get("components", {}).get("schemas", {}).get(raw_ref_name)
                        if component_schema_def:
                            self._parse_schema(raw_ref_name, component_schema_def, spec)
                        else:
                            logger.warning(f"Could not find schema component for parameter ref {ref_path}. Defaulting type.")
                            # Attempt to get type from resolved schema if not a component
                            type_info = self._get_python_type(param_schema) # param_schema is resolved_ref here
                            param_type = type_info.get('type', 'Any') if isinstance(type_info, dict) else type_info

                    # If schema was found and parsed (or already existed), use its sanitized name
                    if ref_schema_name in self.schemas:
                         param_type = ref_schema_name # Use the schema's sanitized name as type
                    # else: it means it was not found in components and type_info was used above
                else:
                    type_info = self._get_python_type(param_schema) # param_schema is resolved_ref
                    param_type = type_info.get('type', 'Any') if isinstance(type_info, dict) else type_info
            else: # Inline schema definition for the parameter
                type_info = self._get_python_type(param_schema)
                param_type = type_info.get('type', 'Any') if isinstance(type_info, dict) else type_info
        else: # No schema for the parameter (OpenAPI 2.0 style, or simple type)
            type_info = self._get_python_type(param_def)
            param_type = type_info.get('type', 'Any') if isinstance(type_info, dict) else type_info


        return Parameter(
            name=name,
            location=location,
            type=param_type,
            required=required,
            description=description,
        )

    def _get_python_type(self, schema_prop: Dict[str, Any]) -> Union[str, Dict[str, Any]]:
        """Converts OpenAPI schema type to Python type hint. schema_prop is assumed to be resolved."""
        prop_type = schema_prop.get("type")
        prop_format = schema_prop.get("format")
        prop_ref = schema_prop.get("$ref") # Should not happen if schema_prop is resolved, but as a fallback

        if prop_ref:
            ref_name = self._extract_schema_name(prop_ref) # Sanitized
            return ref_name if ref_name else "Any"


        if prop_type == "string":
            if prop_format == "date-time":
                return "datetime"
            elif prop_format == "date":
                return "date"
            elif prop_format == "email": # Pydantic's EmailStr can be used by generator
                return "str"
            elif prop_format == "binary": # e.g. for file uploads
                return "bytes"
            return "str"
        elif prop_type == "integer":
            return "int"
        elif prop_type == "number":
            if prop_format == "float" or prop_format == "double":
                return "float"
            return "float"
        elif prop_type == "boolean":
            return "bool"
        elif prop_type == "array":
            items_schema_or_ref = schema_prop.get("items", {})
            items_schema = self._resolve_ref(items_schema_or_ref["$ref"], {}) if "$ref" in items_schema_or_ref else items_schema_or_ref # Pass empty spec for resolving item ref if it's not a component ref

            item_type_info = self._get_python_type(items_schema) # Recursive call
            item_type_str = item_type_info.get('type', 'Any') if isinstance(item_type_info, dict) else str(item_type_info)
            return f"List[{item_type_str}]"
        elif prop_type == "object":
            if "additionalProperties" in schema_prop:
                additional_props_schema_or_ref = schema_prop["additionalProperties"]
                if isinstance(additional_props_schema_or_ref, dict):
                    additional_props_schema = self._resolve_ref(additional_props_schema_or_ref["$ref"], {}) if "$ref" in additional_props_schema_or_ref else additional_props_schema_or_ref
                    additional_prop_type_info = self._get_python_type(additional_props_schema)
                    additional_prop_type_str = additional_prop_type_info.get('type', 'Any') if isinstance(additional_prop_type_info, dict) else str(additional_prop_type_info)
                    return f"Dict[str, {additional_prop_type_str}]"
                elif isinstance(additional_props_schema_or_ref, bool) and additional_props_schema_or_ref:
                    return "Dict[str, Any]"

            if "properties" in schema_prop:
                 # This indicates an inline anonymous object.
                 # The caller (_parse_schema) should handle creating a Schema for this if it's a top-level schema.
                 # If it's a property, the generator needs to decide to make an inline class or use Dict.
                 # Returning a special dict structure can signal this.
                return {"type": "object", "is_inline_complex": True, "properties": schema_prop["properties"]}

            return "Dict[str, Any]" # Default for object type if no specific structure

        return "Any" # Fallback

    def _extract_schema_name(self, ref_path: str) -> Optional[str]:
        """Extracts schema name from a $ref path like '#/components/schemas/MySchema' and sanitizes it."""
        match = re.match(r"^#/components/schemas/([^/]+)$", ref_path)
        if match:
            return self._sanitize_name(match.group(1))

        # Handle other types of local references if necessary, e.g. parameters, responses
        # For now, focus on schemas.
        return None

    def _sanitize_name(self, name: str) -> str:
        """Sanitizes a name to be a valid Python identifier."""
        if not isinstance(name, str): # Ensure name is a string
            name = str(name)

        # Replace invalid characters with underscore
        name = re.sub(r"[^0-9a-zA-Z_]", "_", name)

        # Remove leading characters until a letter or underscore is found
        name = re.sub(r"^[^a-zA-Z_]+", "", name)

        if not name: # Handle empty string after sanitization
            return "_Schema"

        # If first char is a digit after initial sanitization (e.g. _0_Schema), prepend underscore
        if name[0].isdigit():
            name = "_" + name

        # Basic check for python keywords (can be expanded)
        # For now, we assume names like 'list', 'dict' are unlikely for top-level schemas
        # but could be for properties. This might need more sophisticated handling if it collides.
        # A common practice is to append an underscore if it's a keyword.
        # For now, let's keep it simple. If 'list' is a schema name, it becomes 'list'.
        # The generator should handle potential keyword clashes for variable names.

        return name
