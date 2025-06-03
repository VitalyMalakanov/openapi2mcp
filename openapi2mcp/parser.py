import json
import logging
import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Union

logger = logging.getLogger(__name__)


class OpenAPIParserError(Exception):
    """
    Custom exception for OpenAPI parsing errors.

    Пользовательское исключение для ошибок парсинга OpenAPI.
    """
    pass


class HttpMethod(Enum):
    """
    Enumeration of HTTP methods supported by OpenAPI.

    Перечисление HTTP-методов, поддерживаемых OpenAPI.
    """
    GET = "get"
    POST = "post"
    PUT = "put"
    DELETE = "delete"
    PATCH = "patch"
    OPTIONS = "options"
    HEAD = "head"


class ParameterLocation(Enum):
    """
    Enumeration of parameter locations in an OpenAPI specification.

    Перечисление мест расположения параметров в спецификации OpenAPI.
    """
    PATH = "path"
    QUERY = "query"
    HEADER = "header"
    COOKIE = "cookie"


@dataclass
class Parameter:
    """
    Represents a parameter in an OpenAPI operation.

    Представляет параметр в операции OpenAPI.

    Attributes:
        name (str): The name of the parameter.
                    Имя параметра.
        location (ParameterLocation): The location of the parameter (e.g., path, query).
                                      Местоположение параметра (например, path, query).
        type (str): The Python type of the parameter.
                    Python-тип параметра.
        required (bool): Whether the parameter is required.
                         Является ли параметр обязательным.
        description (Optional[str]): An optional description of the parameter.
                                     Необязательное описание параметра.
    """
    name: str
    location: ParameterLocation
    type: str
    required: bool
    description: Optional[str] = None


@dataclass
class Schema:
    """
    Represents a schema definition from the OpenAPI specification.

    Представляет определение схемы из спецификации OpenAPI.

    Attributes:
        name (str): The sanitized name of the schema, suitable for use as a Python identifier.
                    Очищенное имя схемы, подходящее для использования в качестве идентификатора Python.
        type (str): The type of the schema (e.g., 'object', 'array', 'string', or a referenced schema name).
                    Тип схемы (например, 'object', 'array', 'string' или имя связанной схемы).
        properties (Dict[str, Any]): A dictionary of property names to their types or schema definitions.
                                     Словарь имен свойств и их типов или определений схем.
        required_properties (List[str]): A list of required property names.
                                         Список обязательных имен свойств.
        description (Optional[str]): An optional description of the schema.
                                     Необязательное описание схемы.
        raw_schema (Dict[str, Any]): The original, unresolved schema definition from the OpenAPI document.
                                     Исходное, неразрешенное определение схемы из документа OpenAPI.
    """
    name: str
    type: str
    properties: Dict[str, Any] = field(default_factory=dict)
    required_properties: List[str] = field(default_factory=list)
    description: Optional[str] = None
    raw_schema: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Operation:
    """
    Represents an operation (API endpoint) defined in the OpenAPI specification.

    Представляет операцию (конечную точку API), определенную в спецификации OpenAPI.

    Attributes:
        operation_id (str): The sanitized operation ID, suitable for use as a Python method name.
                            Очищенный ID операции, подходящий для использования в качестве имени метода Python.
        method (HttpMethod): The HTTP method of the operation (e.g., GET, POST).
                             HTTP-метод операции (например, GET, POST).
        path (str): The URL path of the operation.
                    URL-путь операции.
        summary (Optional[str]): A short summary of what the operation does.
                                 Краткое описание того, что делает операция.
        description (Optional[str]): A detailed description of the operation.
                                     Подробное описание операции.
        parameters (List[Parameter]): A list of parameters for the operation.
                                      Список параметров для операции.
        request_body_schema (Optional[Schema]): The schema for the request body, if any.
                                                Схема для тела запроса, если таковая имеется.
        response_schema (Optional[Schema]): The schema for the successful response body, if any.
                                            Схема для успешного тела ответа, если таковая имеется.
        tags (List[str]): A list of tags for grouping operations.
                          Список тегов для группировки операций.
    """
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
    """
    Parses an OpenAPI 3.x specification and transforms it into a list of operations and schemas.

    Разбирает спецификацию OpenAPI 3.x и преобразует ее в список операций и схем.

    Attributes:
        schemas (Dict[str, Schema]): A dictionary mapping sanitized schema names to Schema objects.
                                     Словарь, сопоставляющий очищенные имена схем с объектами Schema.
        operations (List[Operation]): A list of Operation objects representing the API endpoints.
                                      Список объектов Operation, представляющих конечные точки API.
    """
    def __init__(self):
        """
        Initializes the OpenAPIParser.

        Инициализирует OpenAPIParser.
        """
        self.schemas: Dict[str, Schema] = {}
        self.operations: List[Operation] = []
        self._visited_refs: Set[str] = set() # Used to detect and attempt to break circular $ref dependencies. / Используется для обнаружения и попытки разорвать циклические зависимости $ref.

    def parse_file(self, filepath: Path) -> None:
        """
        Parses an OpenAPI specification file (JSON or YAML).

        Разбирает файл спецификации OpenAPI (JSON или YAML).

        Args:
            filepath (Path): The path to the OpenAPI specification file.
                             Путь к файлу спецификации OpenAPI.

        Raises:
            OpenAPIParserError: If the file is not found, unsupported, or an error occurs during parsing.
                                Если файл не найден, не поддерживается или возникает ошибка во время разбора.
        """
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
        """
        Parses the main OpenAPI specification structure.
        It first parses all schemas defined in '#/components/schemas' because paths might reference them.

        Разбирает основную структуру спецификации OpenAPI.
        Сначала разбирает все схемы, определенные в '#/components/schemas', так как пути могут на них ссылаться.

        Args:
            spec (Dict[str, Any]): The loaded OpenAPI specification as a dictionary.
                                   Загруженная спецификация OpenAPI в виде словаря.
        """
        # EN: Parse component schemas first, as they can be referenced by paths and other schemas.
        # RU: Сначала разбираем схемы компонентов, так как на них могут ссылаться пути и другие схемы.
        if "components" in spec and "schemas" in spec["components"]:
            for schema_name, schema_def in spec["components"]["schemas"].items():
                self._parse_schema(schema_name, schema_def, spec)

        # EN: Then parse paths and their operations.
        # RU: Затем разбираем пути и их операции.
        if "paths" in spec:
            for path, path_item in spec["paths"].items():
                self._parse_path(path, path_item, spec)

    def _resolve_ref(self, ref: str, spec: Dict[str, Any]) -> Dict[str, Any]:
        """
        Resolves a JSON reference string (e.g., '#/components/schemas/MySchema') to its actual definition.
        Handles simple circular reference detection by tracking visited references.

        Разрешает строку JSON-ссылки (например, '#/components/schemas/MySchema') до ее фактического определения.
        Обрабатывает простое обнаружение циклических ссылок путем отслеживания посещенных ссылок.

        Args:
            ref (str): The JSON reference string.
                       Строка JSON-ссылки.
            spec (Dict[str, Any]): The full OpenAPI specification dictionary.
                                   Полный словарь спецификации OpenAPI.

        Returns:
            Dict[str, Any]: The resolved schema or component definition.
                            Разрешенная схема или определение компонента.

        Raises:
            OpenAPIParserError: If the reference format is unsupported or the reference cannot be resolved.
                                Если формат ссылки не поддерживается или ссылка не может быть разрешена.
        """
        if not ref.startswith("#/"):
            # EN: Currently, only local references (within the same document) are supported.
            # RU: В настоящее время поддерживаются только локальные ссылки (внутри того же документа).
            raise OpenAPIParserError(f"Unsupported reference format: {ref}. Only local references starting with '#/' are supported.")

        if ref in self._visited_refs:
            # EN: Circular reference detected.
            # RU: Обнаружена циклическая ссылка.
            schema_name = self._extract_schema_name(ref) # Sanitized name
            if schema_name and schema_name in self.schemas:
                # EN: If the schema has already been processed (even partially), return a marker.
                # RU: Если схема уже была обработана (даже частично), возвращаем маркер.
                # EN: The generator will need to handle this, possibly by using a forward reference if the language supports it,
                # EN: or by using a generic type like 'Any' or 'Dict'.
                # RU: Генератору потребуется обработать это, возможно, используя опережающую ссылку, если язык это поддерживает,
                # RU: или используя общий тип, такой как 'Any' или 'Dict'.
                logger.warning(f"Circular reference detected and already processed for: {ref}. Returning placeholder.")
                return {"type": "object", "x-circular-ref": schema_name, "description": f"Circular reference to {schema_name}"}
            else:
                # EN: This case implies a circular reference to a schema that hasn't started parsing yet.
                # EN: This is a more complex scenario. For now, we log a warning and return a generic object type.
                # EN: A more robust solution might involve deferring resolution or multiple parsing passes.
                # RU: Этот случай подразумевает циклическую ссылку на схему, которая еще не начала разбираться.
                # RU: Это более сложный сценарий. Пока что мы регистрируем предупреждение и возвращаем общий тип объекта.
                # RU: Более надежное решение может включать отложенное разрешение или несколько проходов разбора.
                logger.warning(f"Circular reference detected to an unprocessed schema: {ref}. Returning generic object. This might lead to incomplete type information.")
                return {"type": "object", "description": f"Circular reference to an unprocessed schema: {ref}"}

        self._visited_refs.add(ref)

        parts = ref[2:].split("/")
        # EN: Navigate through the spec dictionary using the parts of the reference string.
        # RU: Перемещаемся по словарю спецификации, используя части строки ссылки.
        current = spec
        for part in parts:
            if isinstance(current, dict) and part in current:
                current = current[part]
            elif isinstance(current, list) and part.isdigit() and int(part) < len(current): # Check for valid list index
                current = current[int(part)]
            else:
                # EN: Part of the reference path could not be found in the specification.
                # RU: Часть пути ссылки не найдена в спецификации.
                self._visited_refs.remove(ref) # Clean up before raising
                raise OpenAPIParserError(f"Could not resolve reference: {ref}. Part '{part}' not found.")

        # EN: If the resolved part is itself a reference, recursively resolve it.
        # RU: Если разрешенная часть сама является ссылкой, рекурсивно разрешаем ее.
        if isinstance(current, dict) and "$ref" in current:
            nested_ref_val = current["$ref"]
            # EN: Important: Do not remove the current 'ref' from _visited_refs before resolving the nested one,
            # EN: as the nested one might be part of the same circular structure.
            # RU: Важно: не удаляйте текущую 'ref' из _visited_refs перед разрешением вложенной,
            # RU: так как вложенная может быть частью той же циклической структуры.
            resolved_nested = self._resolve_ref(nested_ref_val, spec)
            self._visited_refs.remove(ref) # Remove parent ref from visited set *after* its nested refs are resolved.
            return resolved_nested

        self._visited_refs.remove(ref) # Remove after successful resolution and no further nested refs.
        return current

    def _parse_schema(
        self, schema_name: str, schema_def: Dict[str, Any], spec: Dict[str, Any]
    ) -> Schema:
        """
        Parses an individual schema definition from the OpenAPI specification.
        Handles direct definitions and references ($ref) to other schemas.
        Stores parsed schemas in `self.schemas` using their sanitized names as keys.

        Разбирает отдельное определение схемы из спецификации OpenAPI.
        Обрабатывает прямые определения и ссылки ($ref) на другие схемы.
        Сохраняет разобранные схемы в `self.schemas`, используя их очищенные имена в качестве ключей.

        Args:
            schema_name (str): The original name of the schema (e.g., "User", "ErrorModel").
                               Исходное имя схемы (например, "User", "ErrorModel").
            schema_def (Dict[str, Any]): The dictionary defining the schema.
                                         Словарь, определяющий схему.
            spec (Dict[str, Any]): The full OpenAPI specification.
                                   Полная спецификация OpenAPI.

        Returns:
            Schema: The parsed Schema object.
                    Разобранный объект Schema.
        """
        # EN: schema_name is the key from the components/schemas section (e.g. "User", "User_Input")
        # RU: schema_name - это ключ из раздела components/schemas (например, "User", "User_Input")
        original_ref_path = f"#/components/schemas/{schema_name}"

        # EN: Sanitize the schema name for use as a Python identifier and dictionary key.
        # RU: Очищаем имя схемы для использования в качестве идентификатора Python и ключа словаря.
        sanitized_schema_name = self._sanitize_name(schema_name)

        # EN: Handle potential circular dependencies or already parsed schemas.
        # RU: Обработка потенциальных циклических зависимостей или уже разобранных схем.
        if original_ref_path in self._visited_refs:
            if sanitized_schema_name in self.schemas:
                # logger.debug(f"Schema {sanitized_schema_name} (from {original_ref_path}) already visited and parsed. Returning existing.")
                return self.schemas[sanitized_schema_name]
            else:
                # EN: This indicates a circular reference where the schema is visited but not yet fully stored.
                # EN: We create a placeholder Schema object and add it to self.schemas to break the loop.
                # EN: The properties will be filled in as parsing continues.
                # RU: Это указывает на циклическую ссылку, где схема посещена, но еще не полностью сохранена.
                # RU: Мы создаем объект-заполнитель Schema и добавляем его в self.schemas, чтобы разорвать цикл.
                # RU: Свойства будут заполнены по мере продолжения разбора.
                logger.warning(f"Circular reference detected for schema: {schema_name}. Creating a placeholder and will fill properties later.")
                placeholder_schema = Schema(name=sanitized_schema_name, type=sanitized_schema_name, raw_schema=schema_def)
                self.schemas[sanitized_schema_name] = placeholder_schema
                # Do not return yet, proceed to parse its definition to fill it.
        elif sanitized_schema_name in self.schemas:
            # EN: Schema was already parsed and stored (e.g. by a previous $ref resolution).
            # RU: Схема уже была разобрана и сохранена (например, предыдущим разрешением $ref).
            return self.schemas[sanitized_schema_name]


        self._visited_refs.add(original_ref_path)

        current_schema_def = schema_def
        # EN: If the schema definition is a reference, resolve it.
        # RU: Если определение схемы является ссылкой, разрешаем ее.
        if "$ref" in current_schema_def:
            try:
                resolved_schema_def = self._resolve_ref(current_schema_def["$ref"], spec)
                # EN: Check if the resolved definition indicates a circular ref that was handled by _resolve_ref
                # RU: Проверяем, указывает ли разрешенное определение на циклическую ссылку, обработанную в _resolve_ref
                if resolved_schema_def.get("x-circular-ref"):
                    # If it's a circular reference to an already *parsed* schema, its type is its name.
                    # The generator will handle this by referring to the existing class.
                    # We use the sanitized name of the target schema.
                    circ_ref_name = self._sanitize_name(resolved_schema_def["x-circular-ref"])
                    # Create a "proxy" schema that just points to the actual one by name.
                    proxy_schema = Schema(name=sanitized_schema_name, type=circ_ref_name, raw_schema=current_schema_def, description=f"Circular reference to {circ_ref_name}")
                    self.schemas[sanitized_schema_name] = proxy_schema
                    self._visited_refs.remove(original_ref_path)
                    return proxy_schema
                current_schema_def = resolved_schema_def
            except OpenAPIParserError as e:
                logger.error(f"Failed to resolve $ref {current_schema_def['$ref']} for schema {schema_name}: {e}")
                # Create a fallback schema to avoid crashing
                fallback_schema = Schema(name=sanitized_schema_name, type="Any", description=f"Failed to resolve $ref: {current_schema_def['$ref']}", raw_schema=schema_def)
                self.schemas[sanitized_schema_name] = fallback_schema
                self._visited_refs.remove(original_ref_path)
                return fallback_schema


        schema_type = current_schema_def.get("type", "object") # Default to 'object' if type is not specified
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
                        if ref_schema_name: # This is a sanitized name
                            if ref_schema_name not in self.schemas:
                                # EN: Referenced schema hasn't been parsed yet. Parse it now.
                                # RU: Ссылочная схема еще не была разобрана. Разбираем ее сейчас.
                                if ref_path.startswith("#/components/schemas/"):
                                    raw_ref_schema_name_for_lookup = ref_path.split('/')[-1] # Use raw name for lookup in spec
                                    component_schema_def = spec.get("components", {}).get("schemas", {}).get(raw_ref_schema_name_for_lookup)
                                    if component_schema_def:
                                       self._parse_schema(raw_ref_schema_name_for_lookup, component_schema_def, spec)
                                    else:
                                        logger.warning(f"Could not find definition for referenced schema: {raw_ref_schema_name_for_lookup} (from {ref_path}) in property {prop_name} of {schema_name}. Defaulting to 'Any'.")
                                        properties[prop_name] = {"type": "Any", "description": f"Unresolved reference: {ref_path}"}
                                        continue
                                else:
                                    # EN: Reference is not to a standard component schema (e.g., could be a parameter schema).
                                    # RU: Ссылка не на стандартную схему компонента (например, может быть схемой параметра).
                                    # EN: For now, we try to get its type directly. A more robust solution might involve parsing these too.
                                    # RU: Пока что пытаемся получить ее тип напрямую. Более надежное решение может включать их разбор.
                                    logger.warning(f"Unsupported reference type for property {prop_name} in {schema_name}: {ref_path}. Attempting to get type directly.")
                                    prop_type_info = self._get_python_type(resolved_prop_def) # resolved_prop_def is the content of the $ref
                                    properties[prop_name] = prop_type_info if isinstance(prop_type_info, dict) else {"type": prop_type_info}
                                    continue
                            # EN: Use the sanitized name of the referenced schema as its type.
                            # RU: Используем очищенное имя ссылочной схемы в качестве ее типа.
                            properties[prop_name] = {"type": ref_schema_name, "is_ref": True}
                        else:
                            # EN: $ref was not in '#/components/schemas/' format or _extract_schema_name returned None.
                            # EN: This could be an inline definition or a reference to something not yet supported.
                            # RU: $ref был не в формате '#/components/schemas/' или _extract_schema_name вернул None.
                            # RU: Это может быть встроенное определение или ссылка на что-то еще не поддерживаемое.
                            logger.warning(f"Non-component reference or unextractable name for property {prop_name} in {schema_name}: {ref_path}. Using resolved definition directly.")
                            properties[prop_name] = self._get_python_type(resolved_prop_def)
                    except OpenAPIParserError as e:
                        logger.warning(f"Could not resolve reference {ref_path} for property {prop_name} in {schema_name}: {e}. Defaulting to 'Any'.")
                        properties[prop_name] = {"type": "Any", "description": f"Unresolved reference: {ref_path}"}
                else:
                    # EN: Property is defined inline.
                    # RU: Свойство определено встроенно.
                    properties[prop_name] = self._get_python_type(prop_def)
        # EN: Handling for array type schemas
        # RU: Обработка для схем типа "array"
        elif schema_type == "array" and "items" in current_schema_def:
            items_def = current_schema_def["items"]
            item_schema_type_str = "Any" # Default item type
            if "$ref" in items_def:
                ref_path = items_def["$ref"]
                try:
                    # EN: Resolve the reference for array items.
                    # RU: Разрешаем ссылку для элементов массива.
                    # Note: _resolve_ref itself doesn't take 'spec' for items if they are not component refs,
                    # so we pass the full spec here just in case, though _get_python_type handles nested refs.
                    resolved_items_def = self._resolve_ref(ref_path, spec)
                    ref_schema_name = self._extract_schema_name(ref_path) # Sanitized name
                    if ref_schema_name:
                        if ref_schema_name not in self.schemas:
                            # EN: Referenced item schema hasn't been parsed yet. Parse it now.
                            # RU: Ссылочная схема элемента еще не была разобрана. Разбираем ее сейчас.
                            if ref_path.startswith("#/components/schemas/"):
                                raw_ref_item_schema_name = ref_path.split('/')[-1]
                                component_item_schema_def = spec.get("components", {}).get("schemas", {}).get(raw_ref_item_schema_name)
                                if component_item_schema_def:
                                    self._parse_schema(raw_ref_item_schema_name, component_item_schema_def, spec)
                                else:
                                    logger.warning(f"Could not find definition for array item's referenced schema: {raw_ref_item_schema_name} (from {ref_path}) in {schema_name}.")
                                    # item_schema_type_str remains "Any"
                            else:
                                logger.warning(f"Unsupported reference type for array items in {schema_name}: {ref_path}.")
                                # item_schema_type_str remains "Any"
                        item_schema_type_str = ref_schema_name # Use sanitized name of the referenced schema
                    else:
                        # EN: If ref_schema_name is None, it's likely an inline complex type or non-component ref.
                        # RU: Если ref_schema_name равно None, это, вероятно, встроенный сложный тип или не-компонентная ссылка.
                        item_type_info = self._get_python_type(resolved_items_def)
                        item_schema_type_str = item_type_info.get('type', 'Any') if isinstance(item_type_info, dict) else item_type_info
                except OpenAPIParserError as e:
                    logger.warning(f"Could not resolve reference {ref_path} for array items in {schema_name}: {e}.")
                    # item_schema_type_str remains "Any"
            else:
                # EN: Array items are defined inline.
                # RU: Элементы массива определены встроенно.
                item_type_info = self._get_python_type(items_def)
                item_schema_type_str = item_type_info.get('type', 'Any') if isinstance(item_type_info, dict) else item_type_info
            schema_type = f"List[{item_schema_type_str}]" # Final type for the array schema itself

        # EN: If a schema was already created as a placeholder (due to circular ref), update it.
        # RU: Если схема уже была создана как заполнитель (из-за циклической ссылки), обновляем ее.
        if sanitized_schema_name in self.schemas and self.schemas[sanitized_schema_name].type == sanitized_schema_name : # Check if it's a placeholder
            schema = self.schemas[sanitized_schema_name]
            schema.type = schema_type if schema_type != "object" or not properties else sanitized_schema_name
            schema.properties = properties
            schema.required_properties = required_properties
            schema.description = current_schema_def.get("description", schema.description) # Keep existing if new is None
            schema.raw_schema = current_schema_def # Update raw schema
        else:
            # EN: Create a new Schema object.
            # RU: Создаем новый объект Schema.
            # EN: If schema_type is 'object' and has properties, its type effectively becomes its own name for Pydantic model generation.
            # RU: Если schema_type равен 'object' и имеет свойства, его тип фактически становится его собственным именем для генерации модели Pydantic.
            schema = Schema(
                name=sanitized_schema_name,
                type=schema_type if schema_type != "object" or not properties else sanitized_schema_name,
                properties=properties,
                required_properties=required_properties,
                description=current_schema_def.get("description"),
                raw_schema=current_schema_def, # Store the (possibly resolved) definition
            )
            self.schemas[sanitized_schema_name] = schema

        if original_ref_path in self._visited_refs:
            self._visited_refs.remove(original_ref_path)
        return schema

    def _parse_path(
        self, path: str, path_item: Dict[str, Any], spec: Dict[str, Any]
    ) -> None:
        """
        Parses a path item (e.g., '/users/{id}') and all its HTTP operations (GET, POST, etc.).
        Extracts details for each operation, including parameters, request body, and responses.

        Разбирает элемент пути (например, '/users/{id}') и все его HTTP-операции (GET, POST и т.д.).
        Извлекает детали для каждой операции, включая параметры, тело запроса и ответы.

        Args:
            path (str): The URL path string.
                        Строка URL-пути.
            path_item (Dict[str, Any]): The dictionary defining the path item and its operations.
                                        Словарь, определяющий элемент пути и его операции.
            spec (Dict[str, Any]): The full OpenAPI specification.
                                   Полная спецификация OpenAPI.
        """
        # EN: Common parameters defined at the path level, applicable to all operations under this path.
        # RU: Общие параметры, определенные на уровне пути, применимые ко всем операциям в рамках этого пути.
        common_parameters_defs = path_item.get("parameters", [])

        for method_str, op_def in path_item.items():
            if not isinstance(op_def, dict): # Skip non-dict items like 'summary', 'description' at path level
                continue
            method_str_upper = method_str.upper()
            if method_str_upper not in HttpMethod.__members__:
                # EN: Skip items that are not valid HTTP methods (e.g., 'parameters', 'summary').
                # RU: Пропускаем элементы, которые не являются допустимыми HTTP-методами (например, 'parameters', 'summary').
                continue

            method = HttpMethod(method_str.lower())

            # EN: Synthesize operationId if not provided, crucial for generating method names.
            # RU: Синтезируем operationId, если он не предоставлен, что крайне важно для генерации имен методов.
            operation_id = op_def.get("operationId")
            if not operation_id:
                # EN: Create a readable operationId from method and path. Example: "get_users_by_id"
                # RU: Создаем читаемый operationId из метода и пути. Пример: "get_users_by_id"
                clean_path_parts = [part for part in path.split("/") if part] # remove empty parts
                path_name_part = "_".join(clean_path_parts)
                path_name_part = re.sub(r'[\{\}]', '', path_name_part) # remove braces from path params
                path_name_part = re.sub(r'[^a-zA-Z0-9_]', '_', path_name_part) # sanitize
                operation_id = f"{method.value}_{path_name_part}"
                logger.info(f"Synthesized operationId for {method.value.upper()} {path}: {operation_id}")

            sanitized_op_id = self._sanitize_name(operation_id)

            parameters: List[Parameter] = []
            # EN: Parameter definitions can be at path level or operation level.
            # EN: Operation-level parameters override path-level ones with the same name and location.
            # RU: Определения параметров могут быть на уровне пути или на уровне операции.
            # RU: Параметры уровня операции переопределяют параметры уровня пути с тем же именем и местоположением.

            # EN: Start with path-level parameters.
            # RU: Начинаем с параметров уровня пути.
            path_level_params_map: Dict[tuple[str, ParameterLocation], Parameter] = {}
            for param_def_or_ref in common_parameters_defs:
                try:
                    param_def = self._resolve_ref(param_def_or_ref["$ref"], spec) if "$ref" in param_def_or_ref else param_def_or_ref
                    parsed_param = self._parse_parameter(param_def, spec)
                    path_level_params_map[(parsed_param.name, parsed_param.location)] = parsed_param
                except OpenAPIParserError as e:
                    logger.warning(f"Skipping parameter in path {path} due to error: {e}")
                    continue

            parameters.extend(path_level_params_map.values())

            # EN: Process operation-level parameters and handle overrides.
            # RU: Обрабатываем параметры уровня операции и обрабатываем переопределения.
            op_level_params_defs = op_def.get("parameters", [])
            current_op_params_map: Dict[tuple[str, ParameterLocation], Parameter] = {}

            for param_def_or_ref in op_level_params_defs:
                try:
                    param_def = self._resolve_ref(param_def_or_ref["$ref"], spec) if "$ref" in param_def_or_ref else param_def_or_ref
                    parsed_param = self._parse_parameter(param_def, spec)

                    # EN: If an operation parameter has the same name and location as a path parameter, it overrides it.
                    # RU: Если параметр операции имеет то же имя и местоположение, что и параметр пути, он его переопределяет.
                    if (parsed_param.name, parsed_param.location) in path_level_params_map:
                        # Find and replace in the 'parameters' list
                        for i, p in enumerate(parameters):
                            if p.name == parsed_param.name and p.location == parsed_param.location:
                                parameters[i] = parsed_param
                                break
                    else:
                        # EN: Otherwise, it's a new parameter specific to this operation.
                        # RU: В противном случае это новый параметр, специфичный для этой операции.
                        parameters.append(parsed_param)
                    current_op_params_map[(parsed_param.name, parsed_param.location)] = parsed_param # Track for this op
                except OpenAPIParserError as e:
                    logger.warning(f"Skipping parameter in operation {sanitized_op_id} due to error: {e}")
                    continue

            # EN: Ensure path parameters that were NOT overridden by an operation-specific param are still included.
            # RU: Убеждаемся, что параметры пути, которые НЕ были переопределены специфичным для операции параметром, все еще включены.
            # This is implicitly handled by adding path params first, then overriding or adding operation params.

            # EN: Parse request body, if defined.
            # RU: Разбираем тело запроса, если определено.
            request_body_schema: Optional[Schema] = None
            if "requestBody" in op_def:
                request_body_def_or_ref = op_def["requestBody"]
                try:
                    request_body_def = self._resolve_ref(request_body_def_or_ref["$ref"], spec) if "$ref" in request_body_def_or_ref else request_body_def_or_ref
                    # EN: Prioritize 'application/json' content type.
                    # RU: Приоритезируем тип контента 'application/json'.
                    content = request_body_def.get("content", {})
                    json_content = content.get("application/json", content.get("*/*", content.get("application/octet-stream"))) # Fallback for non-JSON bodies
                    if json_content and "schema" in json_content:
                        rb_schema_def_or_ref = json_content["schema"]
                        rb_schema_def = self._resolve_ref(rb_schema_def_or_ref["$ref"], spec) if "$ref" in rb_schema_def_or_ref else rb_schema_def_or_ref

                        ref_path = rb_schema_def_or_ref.get("$ref") if isinstance(rb_schema_def_or_ref, dict) else None
                        if ref_path:
                            ref_schema_name = self._extract_schema_name(ref_path) # Sanitized name
                            if ref_schema_name and ref_schema_name in self.schemas:
                                request_body_schema = self.schemas[ref_schema_name]
                            elif ref_schema_name: # Schema name extracted but not in self.schemas yet
                                 raw_ref_name = ref_path.split('/')[-1]
                                 comp_schema_def = spec.get("components",{}).get("schemas",{}).get(raw_ref_name)
                                 if comp_schema_def:
                                     request_body_schema = self._parse_schema(raw_ref_name, comp_schema_def, spec)
                                 else: # Not a component schema, try parsing directly
                                     request_body_schema = self._parse_schema(ref_schema_name, rb_schema_def, spec)
                            else: # $ref is not a component schema path, or name extraction failed
                                synthetic_name = self._sanitize_name(f"{sanitized_op_id}_RequestBody")
                                request_body_schema = self._parse_schema(synthetic_name, rb_schema_def, spec)
                        else: # Inline schema definition
                            synthetic_name = self._sanitize_name(f"{sanitized_op_id}_RequestBody")
                            request_body_schema = self._parse_schema(synthetic_name, rb_schema_def, spec)
                except OpenAPIParserError as e:
                    logger.warning(f"Could not parse request body for operation {sanitized_op_id}: {e}")


            # EN: Parse response schema, prioritizing 2xx success responses.
            # RU: Разбираем схему ответа, приоритезируя успешные ответы 2xx.
            response_schema: Optional[Schema] = None
            if "responses" in op_def:
                success_response_def_or_ref = None
                # EN: Find the first 2xx response code.
                # RU: Находим первый код ответа 2xx.
                for code, resp_def_ref in op_def["responses"].items():
                    if code.startswith("2") and isinstance(resp_def_ref, dict): # e.g. "200", "201", "2xx"
                        success_response_def_or_ref = resp_def_ref
                        break
                # EN: If no 2xx, try 'default' response.
                # RU: Если нет 2xx, пробуем ответ 'default'.
                if not success_response_def_or_ref and "default" in op_def["responses"] and isinstance(op_def["responses"]["default"], dict):
                    success_response_def_or_ref = op_def["responses"]["default"]

                if success_response_def_or_ref:
                    try:
                        success_response_def = self._resolve_ref(success_response_def_or_ref["$ref"], spec) if "$ref" in success_response_def_or_ref else success_response_def_or_ref
                        content = success_response_def.get("content", {})
                        json_content = content.get("application/json", content.get("*/*")) # Fallback for non-JSON bodies
                        if json_content and "schema" in json_content:
                            resp_schema_def_or_ref = json_content["schema"]
                            resp_schema_def = self._resolve_ref(resp_schema_def_or_ref["$ref"], spec) if "$ref" in resp_schema_def_or_ref else resp_schema_def_or_ref

                            ref_path = resp_schema_def_or_ref.get("$ref") if isinstance(resp_schema_def_or_ref, dict) else None
                            if ref_path:
                                ref_schema_name = self._extract_schema_name(ref_path) # Sanitized name
                                if ref_schema_name and ref_schema_name in self.schemas:
                                    response_schema = self.schemas[ref_schema_name]
                                elif ref_schema_name: # Schema name extracted but not in self.schemas yet
                                     raw_ref_name = ref_path.split('/')[-1]
                                     comp_schema_def = spec.get("components",{}).get("schemas",{}).get(raw_ref_name)
                                     if comp_schema_def:
                                         response_schema = self._parse_schema(raw_ref_name, comp_schema_def, spec)
                                     else: # Not a component schema, try parsing directly
                                         response_schema = self._parse_schema(ref_schema_name, resp_schema_def, spec)
                                else: # $ref is not a component schema path
                                    synthetic_name = self._sanitize_name(f"{sanitized_op_id}_ResponseBody")
                                    response_schema = self._parse_schema(synthetic_name, resp_schema_def, spec)
                            else: # Inline schema definition
                                synthetic_name = self._sanitize_name(f"{sanitized_op_id}_ResponseBody")
                                response_schema = self._parse_schema(synthetic_name, resp_schema_def, spec)
                    except OpenAPIParserError as e:
                        logger.warning(f"Could not parse response body for operation {sanitized_op_id}: {e}")

            self.operations.append(
                Operation(
                    operation_id=sanitized_op_id, # Use sanitized ID
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
        """
        Parses a parameter definition, which might be inline or a reference.
        Assumes `param_def` is the actual definition (already resolved if it was a $ref at the place of usage).

        Разбирает определение параметра, которое может быть встроенным или ссылкой.
        Предполагается, что `param_def` является фактическим определением (уже разрешенным, если это была $ref в месте использования).

        Args:
            param_def (Dict[str, Any]): The parameter definition dictionary.
                                        Словарь определения параметра.
            spec (Dict[str, Any]): The full OpenAPI specification (for resolving nested schemas if any).
                                   Полная спецификация OpenAPI (для разрешения вложенных схем, если таковые имеются).

        Returns:
            Parameter: The parsed Parameter object.
                       Разобранный объект Parameter.
        """
        name = param_def["name"]
        location = ParameterLocation(param_def["in"]) # 'in' is required by OpenAPI spec for parameters
        required = param_def.get("required", False)
        description = param_def.get("description")

        # EN: Parameters have a 'schema' field that defines their type.
        # RU: Параметры имеют поле 'schema', которое определяет их тип.
        param_schema_definition = param_def.get("schema")
        param_python_type = "Any" # Default type

        if param_schema_definition:
            # EN: The 'schema' itself could be a reference or an inline definition.
            # RU: Сама 'schema' может быть ссылкой или встроенным определением.
            if "$ref" in param_schema_definition:
                try:
                    resolved_param_schema = self._resolve_ref(param_schema_definition["$ref"], spec)
                    ref_schema_name = self._extract_schema_name(param_schema_definition["$ref"]) # Sanitized
                    if ref_schema_name:
                        # EN: If the reference is to a component schema, ensure it's parsed.
                        # RU: Если ссылка ведет на схему компонента, убеждаемся, что она разобрана.
                        if ref_schema_name not in self.schemas:
                            raw_ref_name_for_lookup = param_schema_definition["$ref"].split('/')[-1]
                            component_schema_from_spec = spec.get("components", {}).get("schemas", {}).get(raw_ref_name_for_lookup)
                            if component_schema_from_spec:
                                self._parse_schema(raw_ref_name_for_lookup, component_schema_from_spec, spec)
                            else:
                                logger.warning(f"Parameter '{name}' references schema '{ref_schema_name}' ({param_schema_definition['$ref']}) which is not found in components. Attempting to use its resolved type directly.")
                        # EN: If successfully parsed (or was already there), use its sanitized name as the type.
                        # RU: Если успешно разобрана (или уже была там), используем ее очищенное имя в качестве типа.
                        if ref_schema_name in self.schemas:
                           param_python_type = ref_schema_name
                        else: # Fallback if not found in components after trying to parse
                           type_info = self._get_python_type(resolved_param_schema)
                           param_python_type = type_info.get('type', 'Any') if isinstance(type_info, dict) else type_info
                    else:
                        # EN: The $ref was not to '#/components/schemas/...' or name extraction failed.
                        # EN: Use the resolved definition to determine type.
                        # RU: $ref не вела на '#/components/schemas/...' или извлечение имени не удалось.
                        # RU: Используем разрешенное определение для определения типа.
                        type_info = self._get_python_type(resolved_param_schema)
                        param_python_type = type_info.get('type', 'Any') if isinstance(type_info, dict) else type_info
                except OpenAPIParserError as e:
                    logger.warning(f"Could not resolve schema reference for parameter '{name}': {e}. Defaulting type to 'Any'.")
                    param_python_type = "Any"
            else:
                # EN: Inline schema definition for the parameter.
                # RU: Встроенное определение схемы для параметра.
                type_info = self._get_python_type(param_schema_definition)
                param_python_type = type_info.get('type', 'Any') if isinstance(type_info, dict) else type_info
        else:
            # EN: No 'schema' field, might be an older OpenAPI version style (e.g. type directly under parameter).
            # EN: This is common for simple path/query parameters.
            # RU: Нет поля 'schema', возможно, это стиль старой версии OpenAPI (например, тип прямо под параметром).
            # RU: Это характерно для простых параметров path/query.
            type_info = self._get_python_type(param_def) # Pass the parameter definition itself
            param_python_type = type_info.get('type', 'Any') if isinstance(type_info, dict) else type_info

        return Parameter(
            name=name, # Original name from spec
            location=location,
            type=param_python_type, # Determined Python type
            required=required,
            description=description,
        )

    def _get_python_type(self, schema_prop: Dict[str, Any]) -> Union[str, Dict[str, Any]]:
        """
        Converts an OpenAPI schema property definition to a Python type hint string or a dictionary for complex types.
        `schema_prop` is assumed to be a resolved schema definition (not a $ref itself at this level).

        Преобразует определение свойства схемы OpenAPI в строку подсказки типа Python или словарь для сложных типов.
        Предполагается, что `schema_prop` является разрешенным определением схемы (а не самой $ref на этом уровне).

        Args:
            schema_prop (Dict[str, Any]): The dictionary defining the schema property.
                                         Словарь, определяющий свойство схемы.

        Returns:
            Union[str, Dict[str, Any]]: A string representing the Python type (e.g., "str", "List[int]", "MySchemaName")
                                        or a dictionary if it's an inline anonymous object that needs special handling
                                        (e.g., {"type": "object", "is_inline_complex": True, "properties": ...}).
                                        Строка, представляющая тип Python (например, "str", "List[int]", "MySchemaName")
                                        или словарь, если это встроенный анонимный объект, требующий специальной обработки
                                        (например, {"type": "object", "is_inline_complex": True, "properties": ...}).
        """
        prop_type = schema_prop.get("type")
        prop_format = schema_prop.get("format")
        # EN: Handle direct $ref within a property's definition (e.g. property referencing a schema directly)
        # RU: Обработка прямой $ref в определении свойства (например, свойство, напрямую ссылающееся на схему)
        prop_ref = schema_prop.get("$ref")

        if prop_ref:
            # EN: If a property is defined directly as a $ref, resolve its name.
            # RU: Если свойство определено непосредственно как $ref, разрешаем его имя.
            # EN: This $ref should point to a schema in '#/components/schemas/'.
            # RU: Эта $ref должна указывать на схему в '#/components/schemas/'.
            ref_name = self._extract_schema_name(prop_ref) # Sanitized name
            if ref_name:
                # EN: Ensure this referenced schema is parsed or being parsed.
                # RU: Убеждаемся, что эта ссылочная схема разобрана или разбирается.
                if ref_name not in self.schemas:
                    # EN: This situation implies that a property references a schema that hasn't been
                    # EN: encountered yet during the initial pass of `#/components/schemas`.
                    # EN: This can happen if `_parse_schema` for this property's parent schema
                    # EN: is called before the referenced schema is parsed.
                    # EN: We attempt to parse it now.
                    # RU: Эта ситуация подразумевает, что свойство ссылается на схему, которая еще не
                    # RU: встретилась во время первоначального прохода по `#/components/schemas`.
                    # RU: Это может произойти, если `_parse_schema` для родительской схемы этого свойства
                    # RU: вызвана до разбора ссылочной схемы.
                    # RU: Пытаемся разобрать ее сейчас.
                    raw_ref_name_for_lookup = prop_ref.split('/')[-1]
                    # We need the global spec to find the definition
                    # This part assumes _get_python_type is called from a context that has `spec`
                    # However, to keep _get_python_type more self-contained for direct type lookups,
                    # we might need to adjust how `spec` is passed or handle this scenario.
                    # For now, this path is less common if all component schemas are pre-parsed.
                    # If `spec` is not available here, we can only return ref_name and hope it's parsed elsewhere.
                    logger.debug(f"Property references schema '{ref_name}' ('{prop_ref}') which was not pre-parsed. The generator will need to ensure it exists.")
                return ref_name # Return the sanitized name of the referenced schema
            else: # $ref is not in the expected format or name extraction failed
                logger.warning(f"Encountered a $ref '{prop_ref}' in a property that could not be resolved to a schema name. Defaulting to 'Any'.")
                return "Any"

        # EN: Type mapping based on OpenAPI data types and formats.
        # RU: Сопоставление типов на основе типов данных и форматов OpenAPI.
        if prop_type == "string":
            if prop_format == "date-time":
                return "datetime" # Python's datetime.datetime
            elif prop_format == "date":
                return "date" # Python's datetime.date
            elif prop_format == "byte": # Base64 encoded characters
                return "str" # Often handled as string, can be decoded to bytes by user
            elif prop_format == "binary": # Any sequence of octets
                return "bytes" # For file uploads or binary data
            elif prop_format == "email": # Email format
                return "str" # Pydantic's EmailStr can be used by generator
            return "str"
        elif prop_type == "integer":
            # OpenAPI formats like int32, int64 are mapped to Python's arbitrary-precision int.
            return "int"
        elif prop_type == "number":
            if prop_format == "float" or prop_format == "double":
                return "float"
            return "float" # Default for 'number' type
        elif prop_type == "boolean":
            return "bool"
        elif prop_type == "array":
            items_schema_def = schema_prop.get("items", {}) # Default to empty dict if items not defined
            if not items_schema_def: # Array of Any if items is missing or empty
                 logger.warning("Array schema property is missing 'items' definition. Defaulting to List[Any].")
                 return "List[Any]"

            # EN: Recursively get the type for array items.
            # RU: Рекурсивно получаем тип для элементов массива.
            item_type_info = self._get_python_type(items_schema_def)
            item_type_str = item_type_info.get('type', 'Any') if isinstance(item_type_info, dict) else str(item_type_info)
            return f"List[{item_type_str}]"
        elif prop_type == "object":
            # EN: Handling for 'object' type, which can be a dictionary or an inline complex object.
            # RU: Обработка для типа 'object', который может быть словарем или встроенным сложным объектом.
            if "additionalProperties" in schema_prop:
                additional_props_def = schema_prop["additionalProperties"]
                if isinstance(additional_props_def, dict): # Schema for additional properties
                    additional_prop_type_info = self._get_python_type(additional_props_def)
                    additional_prop_type_str = additional_prop_type_info.get('type', 'Any') if isinstance(additional_prop_type_info, dict) else str(additional_prop_type_info)
                    return f"Dict[str, {additional_prop_type_str}]"
                elif isinstance(additional_props_def, bool) and additional_props_def: # additionalProperties: true
                    return "Dict[str, Any]"
                # If additionalProperties is false or not present, it's not a free-form dict unless properties are also absent.

            if "properties" in schema_prop and schema_prop["properties"]: # Checks if properties is not empty
                 # EN: This indicates an inline anonymous object defined within a property.
                 # EN: The caller (_parse_schema) should handle creating a new Schema object for this if it's a response/request body.
                 # EN: If it's a property of another schema, the generator might create an inline Pydantic model.
                 # EN: Returning a special dict structure signals this for the generator.
                 # RU: Это указывает на встроенный анонимный объект, определенный внутри свойства.
                 # RU: Вызывающий (_parse_schema) должен обработать создание нового объекта Schema для этого, если это тело ответа/запроса.
                 # RU: Если это свойство другой схемы, генератор может создать встроенную модель Pydantic.
                 # RU: Возвращение специальной структуры словаря сигнализирует об этом генератору.
                return {"type": "object", "is_inline_complex": True, "properties_def": schema_prop["properties"]}

            # EN: Default for 'object' if no 'properties' and no 'additionalProperties' allowing arbitrary types.
            # EN: Or if 'additionalProperties' is false and no 'properties', it's an empty object (still Dict[str, Any] for flexibility).
            # RU: По умолчанию для 'object', если нет 'properties' и нет 'additionalProperties', разрешающих произвольные типы.
            # RU: Или если 'additionalProperties' равно false и нет 'properties', это пустой объект (все равно Dict[str, Any] для гибкости).
            return "Dict[str, Any]"

        # EN: Fallback type if none of the above conditions are met.
        # RU: Резервный тип, если ни одно из вышеуказанных условий не выполнено.
        logger.debug(f"Unknown schema property type: {prop_type}, format: {prop_format}. Defaulting to 'Any'. Schema prop: {schema_prop}")
        return "Any"

    def _extract_schema_name(self, ref_path: str) -> Optional[str]:
        """
        Extracts and sanitizes schema name from a $ref path (e.g., '#/components/schemas/MySchema' -> 'MySchema').

        Извлекает и очищает имя схемы из пути $ref (например, '#/components/schemas/MySchema' -> 'MySchema').

        Args:
            ref_path (str): The reference path string.
                            Строка пути ссылки.

        Returns:
            Optional[str]: The sanitized schema name if extraction is successful, otherwise None.
                           Очищенное имя схемы в случае успешного извлечения, иначе None.
        """
        # EN: Regex to capture the schema name from the standard components path.
        # RU: Регулярное выражение для захвата имени схемы из стандартного пути компонентов.
        match = re.match(r"^#/components/schemas/([^/]+)$", ref_path)
        if match:
            return self._sanitize_name(match.group(1))

        # EN: Could be extended to handle other $ref types like parameters, responses if needed.
        # RU: Может быть расширено для обработки других типов $ref, таких как параметры, ответы, если это необходимо.
        # logger.debug(f"Could not extract schema name from ref path: {ref_path}")
        return None

    def _sanitize_name(self, name: str) -> str:
        """
        Sanitizes a string to be a valid Python identifier.
        Replaces invalid characters with underscores, ensures it doesn't start with a digit,
        and handles empty or keyword-like names.

        Очищает строку, чтобы она стала допустимым идентификатором Python.
        Заменяет недопустимые символы подчеркиваниями, гарантирует, что она не начинается с цифры,
        и обрабатывает пустые или похожие на ключевые слова имена.

        Args:
            name (str): The input string name.
                        Входная строка имени.

        Returns:
            str: The sanitized name suitable for use as a Python identifier.
                 Очищенное имя, подходящее для использования в качестве идентификатора Python.
        """
        if not isinstance(name, str):
            name = str(name) # Ensure name is a string

        # EN: Replace non-alphanumeric characters (excluding underscore) with underscore.
        # RU: Заменяем не буквенно-цифровые символы (кроме подчеркивания) на подчеркивание.
        name = re.sub(r"[^0-9a-zA-Z_]", "_", name)

        # EN: Remove leading characters until a letter or underscore is found.
        # RU: Удаляем начальные символы до тех пор, пока не будет найдена буква или подчеркивание.
        # EN: If the name consists only of invalid characters, it will become empty here.
        # RU: Если имя состоит только из недопустимых символов, оно станет здесь пустым.
        name = re.sub(r"^[^a-zA-Z_]+", "", name)

        # EN: If the name became empty after sanitization (e.g., "---" -> ""), provide a default.
        # RU: Если имя стало пустым после очистки (например, "---" -> ""), предоставляем значение по умолчанию.
        if not name:
            return "_Schema" # Or raise an error, depending on desired strictness

        # EN: If the first character is a digit (after initial sanitization, e.g. "_0Schema"), prepend an underscore.
        # RU: Если первый символ - цифра (после первоначальной очистки, например, "_0Schema"), добавляем подчеркивание спереди.
        if name[0].isdigit():
            name = "_" + name

        # EN: Check for Python keywords. This list is not exhaustive.
        # RU: Проверка на ключевые слова Python. Этот список не является исчерпывающим.
        # EN: A more robust solution would use `keyword.iskeyword()`.
        # RU: Более надежное решение использовало бы `keyword.iskeyword()`.
        # For now, a simple list of common problematic keywords.
        # Adding an underscore suffix if it matches a keyword.
        # python_keywords = {"list", "dict", "str", "int", "float", "bool", "return", "class", "def", "None", "True", "False"}
        # if name in python_keywords:
        #    name += "_"
        # Decided against auto-suffixing keywords for now, as Pydantic/FastAPI handle some of these gracefully
        # in field names. Class names matching keywords are a bigger issue, but less common for schema names.
        # The generator should handle specific keyword clashes for generated variable names.

        return name
