import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from .parser import (HttpMethod, OpenAPIParser, Operation, Parameter,
                     ParameterLocation, Schema)

logger = logging.getLogger(__name__)

# EN: Python keywords that cannot be used as variable names.
# RU: Ключевые слова Python, которые нельзя использовать в качестве имен переменных.
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

    Очищает строку, чтобы она стала допустимым именем переменной Python.
    - Заменяет недопустимые символы подчеркиваниями.
    - Добавляет подчеркивание спереди, если строка начинается с цифры или пуста.
    - Добавляет подчеркивание в конце, если строка является ключевым словом Python.
    """
    if not isinstance(name, str):
        name = str(name)

    # EN: Replace invalid characters (anything not a letter, digit, or underscore).
    # RU: Заменяем недопустимые символы (все, что не является буквой, цифрой или подчеркиванием).
    name = re.sub(r'[^0-9a-zA-Z_]', '_', name)

    # EN: If name became empty after sanitization (e.g., "---" -> "").
    # RU: Если имя стало пустым после очистки (например, "---" -> "").
    if not name:
        return "_var" # Default for empty sanitized name

    # EN: Prepend an underscore if the name starts with a digit.
    # RU: Добавляем подчеркивание спереди, если имя начинается с цифры.
    if name[0].isdigit():
        name = "_" + name

    # EN: Append an underscore if the name is a Python keyword.
    # RU: Добавляем подчеркивание в конце, если имя является ключевым словом Python.
    if name in PYTHON_KEYWORDS:
        name += "_"
    return name


class MCPGenerator:
    """
    Generates MCP server code from a parsed OpenAPI specification.

    Генерирует код MCP-сервера из разобранной спецификации OpenAPI.

    Attributes:
        parser (OpenAPIParser): An instance of OpenAPIParser containing the parsed specification.
                                Экземпляр OpenAPIParser, содержащий разобранную спецификацию.
        transport (str): The transport mechanism for the MCP server (e.g., "stdio", "google_pubsub").
                         Транспортный механизм для MCP-сервера (например, "stdio", "google_pubsub").
        mount_path (str): A base path to prepend to all generated resource/tool paths.
                          Базовый путь для добавления ко всем путям генерируемых ресурсов/инструментов.
    """
    def __init__(self, parser: OpenAPIParser, transport: str = "stdio", mount_path: str = ""):
        """
        Initializes the MCPGenerator.

        Инициализирует MCPGenerator.

        Args:
            parser (OpenAPIParser): The parsed OpenAPI specification.
                                    Разобранная спецификация OpenAPI.
            transport (str): The transport mechanism for the server.
                             Транспортный механизм для сервера.
            mount_path (str): Optional base path for all API endpoints.
                              Необязательный базовый путь для всех конечных точек API.
        """
        self.parser = parser
        self.transport = transport
        self.mount_path = mount_path.strip("/") # EN: Ensure no leading/trailing slashes for mount_path. RU: Удаляем начальные/конечные слеши для mount_path.
        self._model_name_map: Dict[str, str] = {} # EN: Maps original schema name to Pydantic model name. RU: Сопоставляет исходное имя схемы с именем модели Pydantic.
        self._generated_model_names: Set[str] = set() # EN: Tracks names of models already generated to avoid duplicates. RU: Отслеживает имена уже сгенерированных моделей во избежание дубликатов.

    def generate(self, output_file: str) -> bool:
        """
        Orchestrates the code generation process and writes the generated code to a file.

        Организует процесс генерации кода и записывает сгенерированный код в файл.

        Args:
            output_file (str): The path to the output Python file.
                               Путь к выходному Python-файлу.

        Returns:
            bool: True if code generation is successful, False otherwise.
                  True, если генерация кода прошла успешно, иначе False.
        """
        logger.info(f"Starting MCP server code generation for transport: {self.transport}")
        try:
            # EN: First pass: prepare a map of original schema names to sanitized Pydantic model names.
            # EN: This is crucial for resolving type hints correctly, especially for forward references or dependencies.
            # RU: Первый проход: подготавливаем карту сопоставления исходных имен схем с очищенными именами моделей Pydantic.
            # RU: Это крайне важно для корректного разрешения подсказок типов, особенно для опережающих ссылок или зависимостей.
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
        """
        Performs a first pass to collect all schema names from the parser
        and map them to sanitized, valid Pydantic model class names.
        This map is essential for generating correct type hints for models,
        especially when schemas reference each other.

        Выполняет первый проход для сбора всех имен схем из парсера
        и сопоставления их с очищенными, допустимыми именами классов моделей Pydantic.
        Эта карта необходима для генерации правильных подсказок типов для моделей,
        особенно когда схемы ссылаются друг на друга.
        """
        for schema_name in self.parser.schemas.keys():
            # EN: The schema_name here is the original key from the OpenAPI spec (e.g., "User", "user-input").
            # RU: schema_name здесь - это исходный ключ из спецификации OpenAPI (например, "User", "user-input").
            pydantic_model_name = self._sanitize_pydantic_model_name(schema_name)
            self._model_name_map[schema_name] = pydantic_model_name


    def _sanitize_pydantic_model_name(self, name: str) -> str:
        """
        Sanitizes a schema name to be a valid Pydantic model class name.
        It ensures the name starts with an uppercase letter and is a valid Python identifier,
        typically in CamelCase or PascalCase. Appends "Model" if it clashes with a Python keyword.

        Очищает имя схемы, чтобы оно стало допустимым именем класса модели Pydantic.
        Гарантирует, что имя начинается с заглавной буквы и является допустимым идентификатором Python,
        обычно в стиле CamelCase или PascalCase. Добавляет "Model", если оно конфликтует с ключевым словом Python.

        Args:
            name (str): The original schema name.
                        Исходное имя схемы.

        Returns:
            str: The sanitized Pydantic model class name.
                 Очищенное имя класса модели Pydantic.
        """
        # EN: Use the parser's base sanitization to make it a valid Python identifier first.
        # RU: Используем базовую очистку парсера, чтобы сначала сделать его допустимым идентификатором Python.
        name = self.parser._sanitize_name(name)
        if not name:
            # EN: This case should ideally be prevented by robust sanitization in the parser.
            # RU: Этот случай в идеале должен предотвращаться надежной очисткой в парсере.
            return "_Model"

        # EN: Ensure CamelCase/PascalCase style for class names.
        # EN: A simple approach: capitalize parts separated by underscores.
        # RU: Обеспечиваем стиль CamelCase/PascalCase для имен классов.
        # RU: Простой подход: капитализируем части, разделенные подчеркиваниями.
        if '_' in name:
            name = "".join(part.capitalize() or '_' for part in name.split('_')) # Retain underscore if part is empty, though unlikely after initial sanitize

        # EN: Ensure the first letter is uppercase.
        # RU: Убеждаемся, что первая буква заглавная.
        if not name[0].isupper():
             name = name[0].upper() + name[1:]

        # EN: Double-check for keyword clashes after CamelCasing, append "Model" if necessary.
        # RU: Повторно проверяем на конфликты с ключевыми словами после преобразования в CamelCase, при необходимости добавляем "Model".
        if name in PYTHON_KEYWORDS:
            name += "Model" # e.g., "List" -> "ListModel", "Class" -> "ClassModel"
        return name


    def _generate_code(self) -> str:
        """
        Assembles the full Python code string for the MCP server by calling
        various internal _generate_* methods for each code section (imports, models, etc.).

        Собирает полную строку Python-кода для MCP-сервера путем вызова
        различных внутренних методов _generate_* для каждого раздела кода (импорты, модели и т.д.).

        Returns:
            str: The complete generated Python code as a string.
                 Полный сгенерированный Python-код в виде строки.
        """
        imports = self._generate_imports()
        # EN: Models must be generated after _prepare_model_name_map has run,
        # EN: as _generate_models uses self._model_name_map for type hints.
        # RU: Модели должны генерироваться после выполнения _prepare_model_name_map,
        # RU: так как _generate_models использует self._model_name_map для подсказок типов.
        models = self._generate_models()
        app_init = self._generate_app_init()
        resources = self._generate_resources()
        tools = self._generate_tools()
        main_block = self._generate_main()

        return f"{imports}\n\n{models}\n\n{app_init}\n\n{resources}\n\n{tools}\n\n{main_block}\n"

    def _generate_imports(self) -> str:
        """
        Generates necessary import statements based on the types used in the OpenAPI specification
        and the chosen transport mechanism.

        Генерирует необходимые операторы импорта на основе типов, используемых в спецификации OpenAPI,
        и выбранного транспортного механизма.

        Returns:
            str: A string containing all required import statements.
                 Строка, содержащая все необходимые операторы импорта.
        """
        # EN: Flags to track if specific datetime types are needed.
        # RU: Флаги для отслеживания необходимости импорта определенных типов datetime.
        uses_datetime = False
        uses_date = False

        # EN: Collect all type strings from schemas, parameters, request/response bodies
        # EN: to determine if datetime or date imports are needed.
        # RU: Собираем все строки типов из схем, параметров, тел запросов/ответов,
        # RU: чтобы определить, нужны ли импорты datetime или date.
        type_strings_to_check = []
        for schema in self.parser.schemas.values():
            type_strings_to_check.append(schema.type) # This might be a name or a basic type like "List[Item]"
            for prop_def in schema.properties.values(): # prop_def is a dict from parser._get_python_type or a type string
                type_strings_to_check.append(prop_def['type'] if isinstance(prop_def, dict) and 'type' in prop_def else str(prop_def))

        for op in self.parser.operations:
            for param in op.parameters:
                type_strings_to_check.append(param.type) # param.type is a string from _get_python_type
            if op.request_body_schema:
                type_strings_to_check.append(op.request_body_schema.type) # schema.type
            if op.response_schema:
                type_strings_to_check.append(op.response_schema.type) # schema.type

        for type_str_item in type_strings_to_check:
            s_type_str = str(type_str_item) # Ensure it's a string
            if "datetime" in s_type_str: # Check for "datetime" (OpenAPI format "date-time")
                uses_datetime = True
            if "date" in s_type_str and "datetime" not in s_type_str: # Check for "date" but not "datetime"
                uses_date = True

        import_statements = [
            "import logging",
            # EN: Basic typing imports, useful for custom code and older Python versions.
            # RU: Базовые импорты типов, полезные для пользовательского кода и старых версий Python.
            "from typing import List, Optional, Any, Dict, Union",
            "from pydantic import BaseModel, Field",
            # EN: Core MCP imports.
            # RU: Основные импорты MCP.
            "from mcp import AbstractResource, AbstractTool, BlockingStdioTransport, Server, Message, Context"
        ]
        if uses_datetime:
            import_statements.append("from datetime import datetime")
        if uses_date:
            import_statements.append("from datetime import date")

        # EN: Add transport-specific imports.
        # RU: Добавляем импорты, специфичные для транспорта.
        if self.transport == "google_pubsub":
            import_statements.append("from mcp.transport.gcp_pubsub import GooglePubSubTransport")
        # TODO: Add other transports like HTTP if supported. RU: TODO: Добавить другие транспорты, такие как HTTP, если поддерживаются.

        import_statements.sort() # Keep imports sorted for readability.
        return "\n".join(import_statements) + "\n\nlogger = logging.getLogger(__name__)"


    def _map_openapi_type_to_pydantic(self, openapi_type_info: Union[str, Dict[str, Any]], is_optional: bool = False) -> str:
        """
        Maps an OpenAPI type definition (which can be a string or a dictionary from the parser)
        to a Pydantic field type string. Handles basic types, schema references, lists, and dictionaries.
        Uses the `_model_name_map` to resolve references to Pydantic class names.

        Сопоставляет определение типа OpenAPI (которое может быть строкой или словарем из парсера)
        со строкой типа поля Pydantic. Обрабатывает базовые типы, ссылки на схемы, списки и словари.
        Использует `_model_name_map` для разрешения ссылок на имена классов Pydantic.

        Args:
            openapi_type_info (Union[str, Dict[str, Any]]): The OpenAPI type information.
                Can be a string (e.g., a schema name like "MyModel", a basic type like "str", or "List[MyModel]")
                or a dictionary (a property definition from the parser, like `{'type': 'string', 'format': 'email'}`).
                Информация о типе OpenAPI. Может быть строкой (например, имя схемы "MyModel", базовый тип "str" или "List[MyModel]")
                или словарем (определение свойства из парсера, например, `{'type': 'string', 'format': 'email'}`).
            is_optional (bool): Whether the field should be considered optional (e.g. `Optional[type]`).
                                Следует ли считать поле необязательным (например, `Optional[type]`).

        Returns:
            str: The Pydantic field type string (e.g., "str", "Optional[int]", "MyModel", "List[AnotherModel]").
                 Строка типа поля Pydantic (например, "str", "Optional[int]", "MyModel", "List[AnotherModel]").
        """
        final_type_str = "Any" # Default type

        if isinstance(openapi_type_info, str):
            # EN: The type_info is already a string. This typically means it's either:
            # EN: 1. A direct Python type string (like "str", "int") from simple schema properties.
            # EN: 2. A schema name (e.g., "MySchema") that should be mapped to a Pydantic class name.
            # EN: 3. A generic type string like "List[MyItemSchema]" or "Dict[str, MyValueSchema]".
            # RU: type_info уже является строкой. Обычно это означает, что это либо:
            # RU: 1. Прямая строка типа Python (например, "str", "int") из простых свойств схемы.
            # RU: 2. Имя схемы (например, "MySchema"), которое должно быть сопоставлено с именем класса Pydantic.
            # RU: 3. Общая строка типа, такая как "List[MyItemSchema]" или "Dict[str, MyValueSchema]".
            type_str = openapi_type_info

            list_match = re.match(r"List\[(.+)\]", type_str)
            dict_match = re.match(r"Dict\[str, (.+)\]", type_str) # Assuming Dict[str, Type] for now

            if list_match:
                inner_type_name = list_match.group(1)
                # EN: Recursively map the inner type of the list.
                # RU: Рекурсивно сопоставляем внутренний тип списка.
                mapped_inner_type = self._map_openapi_type_to_pydantic(inner_type_name) # is_optional is False for inner types by default
                final_type_str = f"List[{mapped_inner_type}]"
            elif dict_match:
                value_type_name = dict_match.group(1)
                # EN: Recursively map the value type of the dictionary.
                # RU: Рекурсивно сопоставляем тип значения словаря.
                mapped_value_type = self._map_openapi_type_to_pydantic(value_type_name)
                final_type_str = f"Dict[str, {mapped_value_type}]"
            elif type_str in self._model_name_map:
                # EN: It's a direct reference to another schema by its original name. Use the mapped Pydantic name.
                # RU: Это прямая ссылка на другую схему по ее исходному имени. Используем сопоставленное имя Pydantic.
                final_type_str = self._model_name_map[type_str]
            elif type_str in ["str", "int", "float", "bool", "datetime", "date", "bytes", "Any", "None"]: # Basic Python types
                final_type_str = type_str
            else:
                # EN: Unrecognized string. This could be an issue if it's an unmapped schema name.
                # EN: Or it might be a pre-formatted complex type string from the parser for non-schema elements.
                # EN: We attempt to sanitize it as a Pydantic model name as a fallback if it looks like a custom type.
                # RU: Нераспознанная строка. Это может быть проблемой, если это несопоставленное имя схемы.
                # RU: Или это может быть предварительно отформатированная строка сложного типа из парсера для не-схемных элементов.
                # RU: В качестве запасного варианта пытаемся очистить ее как имя модели Pydantic, если она похожа на пользовательский тип.
                logger.debug(f"Unmapped type string '{type_str}' encountered during Pydantic type mapping. Attempting to use sanitized name or 'Any'.")
                # EN: Map basic OpenAPI types if they appear here directly (e.g. schema.type = "string")
                # RU: Сопоставляем базовые типы OpenAPI, если они появляются здесь напрямую (например, schema.type = "string")
                if type_str == "string": final_type_str = "str"
                elif type_str == "integer": final_type_str = "int"
                elif type_str == "number": final_type_str = "float"
                elif type_str == "boolean": final_type_str = "bool"
                elif type_str == "object": final_type_str = "Dict[str, Any]" # Generic object
                elif type_str == "array": final_type_str = "List[Any]" # Generic array
                else:
                    # EN: If it doesn't match basic types, assume it *could* be an unmapped schema name.
                    # EN: Sanitize it and use that. The Pydantic validation will catch it if it's not defined.
                    # RU: Если он не соответствует базовым типам, предполагаем, что это *может* быть несопоставленное имя схемы.
                    # RU: Очищаем его и используем. Валидация Pydantic выявит это, если он не определен.
                    final_type_str = self._sanitize_pydantic_model_name(type_str)

        elif isinstance(openapi_type_info, dict):
            # EN: The type_info is a dictionary, likely a property definition from the parser.
            # RU: type_info - это словарь, вероятно, определение свойства из парсера.
            oas_type = openapi_type_info.get("type") # This 'type' is from the OAS property definition

            if openapi_type_info.get("is_ref"):
                # EN: Property directly references another schema. 'oas_type' holds the sanitized schema name.
                # RU: Свойство напрямую ссылается на другую схему. 'oas_type' содержит очищенное имя схемы.
                ref_schema_original_name = oas_type # Parser puts the original schema name (key from components/schemas) here
                final_type_str = self._model_name_map.get(ref_schema_original_name, self._sanitize_pydantic_model_name(ref_schema_original_name))
            elif oas_type == "string": final_type_str = "str" # format (date, datetime, byte, binary) is assumed to be handled by parser into specific Python types if needed, or handled by Pydantic's validation
            elif oas_type == "integer": final_type_str = "int"
            elif oas_type == "number": final_type_str = "float"
            elif oas_type == "boolean": final_type_str = "bool"
            elif oas_type == "array":
                # EN: 'items' definition is expected to be a dict or string that can be recursively mapped.
                # RU: Определение 'items', как ожидается, будет словарем или строкой, которые можно рекурсивно сопоставить.
                items_def = openapi_type_info.get("items", {"type": "Any"}) # Default to Any if items not specified
                item_type_str = self._map_openapi_type_to_pydantic(items_def)
                final_type_str = f"List[{item_type_str}]"
            elif oas_type == "object":
                # EN: For inline object definitions within properties.
                # RU: Для встроенных определений объектов внутри свойств.
                if "additionalProperties" in openapi_type_info:
                    ap_def = openapi_type_info["additionalProperties"]
                    if isinstance(ap_def, dict): # Schema for additionalProperties
                        ap_type = self._map_openapi_type_to_pydantic(ap_def)
                        final_type_str = f"Dict[str, {ap_type}]"
                    elif isinstance(ap_def, bool) and ap_def: # additionalProperties: true
                        final_type_str = "Dict[str, Any]"
                    else: # additionalProperties: false or not a schema, implies a closed object model.
                          # If properties are defined, it's an object. If not, it's effectively an empty object.
                          # Pydantic handles this as a regular model. The generator might create an inline model or use Dict.
                          # For now, if no properties and additionalProperties is false, it's a fixed empty object.
                          # We can map to Dict[str, Any] or a specific empty model if desired.
                          # This case usually means there are 'properties' defined.
                        final_type_str = "Dict[str, Any]" # Fallback if no properties and AP is false.
                elif openapi_type_info.get("is_inline_complex") and openapi_type_info.get("properties_def"):
                    # EN: This is a hint from the parser's _get_python_type that this is an inline object
                    # EN: with its own properties. The generator should ideally create a nested Pydantic model
                    # EN: or a top-level one if this object is used in multiple places (though parser tries to make them schemas).
                    # EN: For now, mapping to Dict[str, Any] as a simplification.
                    # RU: Это подсказка из _get_python_type парсера, что это встроенный объект
                    # RU: со своими собственными свойствами. Генератор в идеале должен создать вложенную модель Pydantic
                    # RU: или модель верхнего уровня, если этот объект используется в нескольких местах (хотя парсер пытается сделать их схемами).
                    # RU: Пока что для упрощения сопоставляем с Dict[str, Any].
                    logger.warning("Inline complex object definition found in property. Mapping to Dict[str, Any]. Consider defining it as a separate named schema in OpenAPI for better type generation.")
                    final_type_str = "Dict[str, Any]"
                else:
                    # EN: Default for 'object' type if no specific structure like properties or additionalProperties is given.
                    # RU: По умолчанию для типа 'object', если не задана конкретная структура, такая как properties или additionalProperties.
                    final_type_str = "Dict[str, Any]"
            elif oas_type in self._model_name_map: # Check if oas_type itself is a known schema name
                 final_type_str = self._model_name_map[oas_type]
            # else: oas_type is None or unhandled, final_type_str remains "Any"

        # EN: Apply Optional[...] if the field is not required and not already Optional.
        # RU: Применяем Optional[...], если поле не является обязательным и еще не Optional.
        if is_optional and final_type_str != "Any" and not final_type_str.startswith("Optional[") and not final_type_str.startswith("Union["):
            # EN: Pydantic v2 automatically treats fields with a default value (like None) as optional.
            # EN: So `Optional[X]` is equivalent to `X = None`.
            # EN: We add `Optional` for clarity and to align with common Pydantic style.
            # RU: Pydantic v2 автоматически рассматривает поля со значением по умолчанию (например, None) как необязательные.
            # RU: Таким образом, `Optional[X]` эквивалентно `X = None`.
            # RU: Мы добавляем `Optional` для ясности и соответствия общему стилю Pydantic.
            final_type_str = f"Optional[{final_type_str}]"

        return final_type_str


    def _generate_models(self) -> str:
        """
        Generates Pydantic model class definitions for all schemas defined in the OpenAPI specification.
        Uses `_model_name_map` to get the correct Pydantic class names.

        Генерирует определения классов моделей Pydantic для всех схем, определенных в спецификации OpenAPI.
        Использует `_model_name_map` для получения правильных имен классов Pydantic.

        Returns:
            str: A string containing all generated Pydantic model definitions, separated by newlines.
                 Строка, содержащая все сгенерированные определения моделей Pydantic, разделенные новыми строками.
        """
        model_strs = []
        # EN: Ensure models are generated in a consistent order, e.g., sorted by name.
        # EN: This helps in reducing diffs when the spec changes slightly.
        # RU: Убеждаемся, что модели генерируются в согласованном порядке, например, отсортированном по имени.
        # RU: Это помогает уменьшить различия при незначительных изменениях спецификации.
        sorted_schema_items = sorted(self.parser.schemas.items(), key=lambda item: item[0])


        for schema_original_name, schema_obj in sorted_schema_items:
            # EN: Check if the schema is intended to be a Pydantic model (e.g., an object with properties).
            # EN: The parser sets schema.type to the schema's own name if it's an object type,
            # EN: or it could be 'array', 'string', etc. We generate models primarily for object types.
            # RU: Проверяем, предназначена ли схема для того, чтобы быть моделью Pydantic (например, объект со свойствами).
            # RU: Парсер устанавливает schema.type в собственное имя схемы, если это тип объекта,
            # RU: или это может быть 'array', 'string' и т.д. Мы генерируем модели в основном для типов объектов.

            # EN: A schema should become a Pydantic model if it's an object type (its type is its name after parsing)
            # EN: or if it explicitly has properties defined (even if type is not 'object' due to refs, etc.).
            # RU: Схема должна стать моделью Pydantic, если это тип объекта (ее тип - это ее имя после разбора)
            # RU: или если у нее явно определены свойства (даже если тип не 'object' из-за ссылок и т.д.).
            is_object_like_schema = schema_obj.type == schema_original_name or schema_obj.type == self._model_name_map.get(schema_original_name) or bool(schema_obj.properties)

            if is_object_like_schema and schema_original_name not in self._generated_model_names:
                 # EN: schema_original_name is the key from the parser's schemas dict (e.g. "User", "user-input")
                 # RU: schema_original_name - это ключ из словаря схем парсера (например, "User", "user-input")
                 model_str = self._generate_model(schema_obj) # Pass the Schema object
                 if model_str:
                    model_strs.append(model_str)
                    self._generated_model_names.add(schema_original_name) # Mark original name as generated

        return "\n\n".join(model_strs)

    def _generate_model(self, schema: Schema) -> str:
        """
        Generates a single Pydantic model class string from a Schema object.

        Генерирует строку одного класса модели Pydantic из объекта Schema.

        Args:
            schema (Schema): The Schema object to convert into a Pydantic model.
                             Объект Schema для преобразования в модель Pydantic.

        Returns:
            str: A string representing the Pydantic model class definition.
                 Строка, представляющая определение класса модели Pydantic.
        """
        # EN: Get the sanitized Pydantic class name from the pre-populated map.
        # RU: Получаем очищенное имя класса Pydantic из предварительно заполненной карты.
        class_name = self._model_name_map.get(schema.name) # schema.name is the original key
        if not class_name:
            logger.error(f"Pydantic model name not found in map for schema: {schema.name}. This should not happen if _prepare_model_name_map ran correctly. Skipping model.")
            return ""

        fields = []
        # EN: Sort properties for consistent field order in the generated model.
        # RU: Сортируем свойства для согласованного порядка полей в генерируемой модели.
        sorted_properties = sorted(schema.properties.items(), key=lambda item: item[0])

        for prop_original_name, prop_def_raw in sorted_properties:
            # EN: Sanitize the property name for use as a Python variable.
            # RU: Очищаем имя свойства для использования в качестве переменной Python.
            field_name = sanitize_variable_name(prop_original_name)
            is_required = prop_original_name in schema.required_properties

            # EN: `prop_def_raw` is the processed property definition from the parser.
            # EN: It can be a dictionary (e.g., {'type': 'str', 'description': '...'}) or a type string.
            # RU: `prop_def_raw` - это обработанное определение свойства из парсера.
            # RU: Это может быть словарь (например, {'type': 'str', 'description': '...'}) или строка типа.
            pydantic_type_str = self._map_openapi_type_to_pydantic(prop_def_raw, is_optional=not is_required)

            field_constructor_args = []
            # EN: Set default for Pydantic Field. `None` for optional, `...` (Ellipsis) for required.
            # RU: Устанавливаем значение по умолчанию для Pydantic Field. `None` для необязательных, `...` (многоточие) для обязательных.
            if not is_required:
                field_constructor_args.append("default=None")
            else:
                field_constructor_args.append("default=...")

            description = None
            # EN: Extract description if prop_def_raw is a dictionary (full property schema).
            # RU: Извлекаем описание, если prop_def_raw является словарем (полная схема свойства).
            if isinstance(prop_def_raw, dict):
                description = prop_def_raw.get("description")
            elif isinstance(prop_def_raw, str) and schema.raw_schema.get("properties", {}).get(prop_original_name, {}).get("description"):
                # EN: Fallback for simple type strings if description is in raw_schema
                # RU: Запасной вариант для простых строк типов, если описание есть в raw_schema
                description = schema.raw_schema.get("properties", {}).get(prop_original_name, {}).get("description")


            if description:
                # EN: Escape quotes in description string for valid Python string literal.
                # RU: Экранируем кавычки в строке описания для допустимого строкового литерала Python.
                escaped_description = description.replace('"', '\\"').replace('\n', ' ') # Also replace newlines
                field_constructor_args.append(f'description="{escaped_description}"')

            # EN: Add serialization alias if the sanitized field_name is different from the original prop_name.
            # EN: This ensures the model still uses the original OpenAPI names for JSON serialization/deserialization.
            # RU: Добавляем псевдоним сериализации, если очищенное field_name отличается от исходного prop_original_name.
            # RU: Это гарантирует, что модель по-прежнему будет использовать исходные имена OpenAPI для сериализации/десериализации JSON.
            if field_name != prop_original_name:
                field_constructor_args.append(f'alias="{prop_original_name}"')


            # EN: Construct the field string: `field_name: Type = Field(...)` or `field_name: Type`
            # RU: Конструируем строку поля: `field_name: Type = Field(...)` или `field_name: Type`
            # EN: Pydantic v2: For optional fields (default=None), the type hint should be Optional[ActualType].
            # EN: _map_openapi_type_to_pydantic already handles adding Optional[] based on is_optional.
            # EN: For required fields (default=...), the type hint should be the actual type.
            # RU: Pydantic v2: Для необязательных полей (default=None) подсказка типа должна быть Optional[ActualType].
            # RU: _map_openapi_type_to_pydantic уже обрабатывает добавление Optional[] на основе is_optional.
            # RU: Для обязательных полей (default=...) подсказка типа должна быть фактическим типом.
            actual_type_for_annotation = pydantic_type_str
            if not is_required and not actual_type_for_annotation.startswith("Optional["):
                 # EN: Ensure Optional for non-required fields if not already handled by _map_openapi_type_to_pydantic (e.g. for Any)
                 # RU: Убеждаемся, что для необязательных полей указан Optional, если это еще не обработано _map_openapi_type_to_pydantic (например, для Any)
                 if actual_type_for_annotation != "Any": # Optional[Any] is just Any
                    actual_type_for_annotation = f"Optional[{actual_type_for_annotation}]"
            elif is_required and actual_type_for_annotation.startswith("Optional["):
                 # EN: Strip Optional if it's marked required (e.g. if type was Any and became Optional[Any])
                 # RU: Удаляем Optional, если поле помечено как обязательное (например, если тип был Any и стал Optional[Any])
                 match = re.match(r"Optional\[(.+)\]", actual_type_for_annotation)
                 if match: actual_type_for_annotation = match.group(1)

            # EN: Use Field() only if there are arguments for it (like default, description, alias).
            # RU: Используем Field() только если для него есть аргументы (например, default, description, alias).
            if len(field_constructor_args) > 1 or (len(field_constructor_args) == 1 and not field_constructor_args[0].startswith("default=")): # More than just default=... or default=None
                 fields.append(f"    {field_name}: {actual_type_for_annotation} = Field({', '.join(field_constructor_args)})")
            elif not is_required : # Optional field with no other Field args, e.g. my_field: Optional[str] = None
                 fields.append(f"    {field_name}: {actual_type_for_annotation} = None")
            else: # Required field with no other Field args, e.g. my_field: str
                 fields.append(f"    {field_name}: {actual_type_for_annotation}")


        # EN: Add a 'pass' statement if the model has no fields, which is valid in Pydantic.
        # RU: Добавляем оператор 'pass', если модель не имеет полей, что допустимо в Pydantic.
        if not fields:
             fields.append("    pass  # EN: No properties defined for this model in the OpenAPI spec. RU: Для этой модели в спецификации OpenAPI не определены свойства.")

        model_docstring_content = schema.description or f"Pydantic model for schema {schema.name}."
        # EN: Ensure docstring content is properly escaped and formatted for a Python multiline string.
        # RU: Убеждаемся, что содержимое строки документации правильно экранировано и отформатировано для многострочной строки Python.
        escaped_doc_content = model_docstring_content.replace("\\", "\\\\").replace('"""',"'''").replace("\n", "\n    ")
        model_docstring = f'    """\n    {escaped_doc_content}\n    """'

        model_def = f"class {class_name}(BaseModel):\n"
        if model_docstring_content.strip(): # Add docstring only if there's content
            model_def += f"{model_docstring}\n"
        model_def += "\n".join(fields)

        return model_def

    def _generate_app_init(self) -> str:
        """
        Generates the MCP Server initialization code.

        Генерирует код инициализации MCP Server.

        Returns:
            str: A string for server initialization (e.g., "app = Server()").
                 Строка для инициализации сервера (например, "app = Server()").
        """
        return "app = Server()  # EN: Main MCP application instance. RU: Главный экземпляр приложения MCP."

    def _generate_resources(self) -> str:
        """
        Generates all MCP Resource class definitions for GET operations.

        Генерирует все определения классов MCP Resource для операций GET.

        Returns:
            str: A string containing all generated Resource class definitions.
                 Строка, содержащая все сгенерированные определения классов Resource.
        """
        # EN: Filter operations that should be Resources (typically GET requests).
        # RU: Фильтруем операции, которые должны быть Ресурсами (обычно GET-запросы).
        resource_strs = [self._generate_resource(op) for op in self.parser.operations if op.method == HttpMethod.GET]
        return "\n\n".join(filter(None, resource_strs))

    def _generate_resource(self, operation: Operation) -> str:
        """
        Generates a single MCP Resource class string for a GET operation.

        Генерирует строку одного класса MCP Resource для операции GET.

        Args:
            operation (Operation): The Operation object (must be a GET operation).
                                   Объект Operation (должен быть операцией GET).

        Returns:
            str: A string representing the generated Resource class.
                 Строка, представляющая сгенерированный класс Resource.
        """
        # EN: Sanitize operation_id for class name, ensure CamelCase.
        # RU: Очищаем operation_id для имени класса, обеспечиваем CamelCase.
        class_name_base = self.parser._sanitize_name(operation.operation_id)
        class_name = (class_name_base[0].upper() + class_name_base[1:] if class_name_base else "Generic") + "Resource"
        if not class_name_base: class_name = "_" + class_name # Should not happen if op_id is always present

        # EN: Determine the response model type string.
        # RU: Определяем строку типа модели ответа.
        response_model_name = "None" # Default if no response schema
        if operation.response_schema:
            # EN: Use the mapped Pydantic model name. This could be "List[MyModel]", "MyModel", etc.
            # RU: Используем сопоставленное имя модели Pydantic. Это может быть "List[MyModel]", "MyModel" и т.д.
            response_model_name = self._map_openapi_type_to_pydantic(operation.response_schema.type)


        # EN: Construct the resource path, including the mount_path if provided.
        # RU: Конструируем путь ресурса, включая mount_path, если он предоставлен.
        # EN: Resource path for MCP is usually based on operation_id for GETs, not the original URL path.
        # RU: Путь ресурса для MCP обычно основан на operation_id для GET-запросов, а не на исходном URL-пути.
        resource_path = f"{self.mount_path}/{operation.operation_id}" if self.mount_path else operation.operation_id

        # EN: Generate class docstring.
        # RU: Генерируем строку документации класса.
        class_docstring_content = operation.summary or f"Resource for operation ID: {operation.operation_id}"
        class_docstring = f'    """\n    {class_docstring_content}\n\n    EN: Corresponds to OpenAPI GET {operation.path}\n    RU: Соответствует OpenAPI GET {operation.path}\n    """'

        # EN: Handle query parameters for the resource.
        # EN: In MCP, query parameters for resources are typically passed in ctx.payload.
        # RU: Обрабатываем параметры запроса для ресурса.
        # RU: В MCP параметры запроса для ресурсов обычно передаются в ctx.payload.
        param_extraction_lines = []
        param_usage_comments = []
        query_params = [p for p in operation.parameters if p.location == ParameterLocation.QUERY]
        if query_params:
            param_extraction_lines.append("        # EN: Extract query parameters from ctx.payload")
            param_extraction_lines.append("        # RU: Извлекаем параметры запроса из ctx.payload")
            for param in query_params:
                var_name = sanitize_variable_name(param.name)
                param_type_hint = self._map_openapi_type_to_pydantic(param.type, is_optional=not param.required)

                if param.required:
                    param_extraction_lines.append(f"        {var_name}: {param_type_hint} = ctx.payload['{param.name}']")
                else:
                    # EN: For optional params, use .get() and provide type hint for clarity.
                    # RU: Для необязательных параметров используем .get() и предоставляем подсказку типа для ясности.
                    param_extraction_lines.append(f"        {var_name}: {param_type_hint} = ctx.payload.get('{param.name}') # type: ignore")
                param_usage_comments.append(var_name)
        else:
            param_extraction_lines.append("        # EN: No query parameters defined for this resource in OpenAPI spec.")
            param_extraction_lines.append("        # RU: Для этого ресурса в спецификации OpenAPI не определены параметры запроса.")


        param_extraction_str = "\n".join(param_extraction_lines)
        param_usage_str = ", ".join(param_usage_comments) if param_usage_comments else "any relevant parameters"

        # EN: Assemble the resource class string.
        # RU: Собираем строку класса ресурса.
        return f"""
@Server.resource(path="{resource_path}")
class {class_name}(AbstractResource[{response_model_name}]):
{class_docstring}
    async def query(self, ctx: Context, **kwargs) -> {response_model_name}:
        logger.info(f"Executing resource: {class_name} with query payload: {{ctx.payload}}")
{param_extraction_str}

        # --- Begin User-Implemented Logic ---
        # EN: Use extracted parameters ({param_usage_str}) to fetch/compute the result.
        # EN: The result should be an instance of '{response_model_name}' or None if response is optional.
        # RU: Используйте извлеченные параметры ({param_usage_str}) для получения/вычисления результата.
        # RU: Результат должен быть экземпляром '{response_model_name}' или None, если ответ необязателен.
        raise NotImplementedError("Resource logic not implemented by the user.")
        # Example:
        # if "{response_model_name}" != "None":
        #     return {response_model_name}(...) # Construct your response model
        # else:
        #     return None
        # --- End User-Implemented Logic ---
"""

    def _generate_tools(self) -> str:
        """
        Generates all MCP Tool class definitions for non-GET operations.

        Генерирует все определения классов MCP Tool для операций, отличных от GET.

        Returns:
            str: A string containing all generated Tool class definitions.
                 Строка, содержащая все сгенерированные определения классов Tool.
        """
        # EN: Filter operations that should be Tools (typically POST, PUT, DELETE, PATCH).
        # RU: Фильтруем операции, которые должны быть Инструментами (обычно POST, PUT, DELETE, PATCH).
        tool_strs = [self._generate_tool(op) for op in self.parser.operations if op.method != HttpMethod.GET]
        return "\n\n".join(filter(None, tool_strs))

    def _generate_tool(self, operation: Operation) -> str:
        """
        Generates a single MCP Tool class string for a non-GET operation.

        Генерирует строку одного класса MCP Tool для операции, отличной от GET.

        Args:
            operation (Operation): The Operation object (must be a non-GET operation).
                                   Объект Operation (должен быть операцией, отличной от GET).

        Returns:
            str: A string representing the generated Tool class.
                 Строка, представляющая сгенерированный класс Tool.
        """
        class_name_base = self.parser._sanitize_name(operation.operation_id)
        class_name = (class_name_base[0].upper() + class_name_base[1:] if class_name_base else "Generic") + "Tool"
        if not class_name_base: class_name = "_" + class_name

        # EN: Determine request model. If no explicit body, but has parameters, consider them.
        # EN: MCP Tool's `arg` is typically the request body. Other params (query, header, path) might be in `ctx`.
        # RU: Определяем модель запроса. Если нет явного тела, но есть параметры, учитываем их.
        # RU: `arg` Инструмента MCP обычно является телом запроса. Другие параметры (query, header, path) могут быть в `ctx`.
        request_model_name = "BaseModel" # Default if no specific request body schema
        if operation.request_body_schema:
            request_model_name = self._map_openapi_type_to_pydantic(operation.request_body_schema.type)
        # else: If no request body, 'arg' will be of type BaseModel.
        # User might need to create a Pydantic model if non-body parameters are to be passed in 'arg'.
        # For now, we assume 'arg' maps to requestBody. Other params are informational.

        response_model_name = "None"
        if operation.response_schema:
            response_model_name = self._map_openapi_type_to_pydantic(operation.response_schema.type)

        # EN: MCP tool name is typically the operation_id.
        # RU: Имя инструмента MCP обычно является operation_id.
        tool_name_mcp = operation.operation_id
        class_docstring_content = operation.summary or f"Tool for operation ID: {operation.operation_id}"
        class_docstring = f'    """\n    {class_docstring_content}\n\n    EN: Corresponds to OpenAPI {operation.method.value.upper()} {operation.path}\n    RU: Соответствует OpenAPI {operation.method.value.upper()} {operation.path}\n    """'

        # EN: Guidance for parameters not directly part of the input model `arg`.
        # RU: Руководство по параметрам, не являющимся непосредственной частью входной модели `arg`.
        param_guidance_lines = ["        # EN: This tool might use parameters not directly in the input model `arg`:"]
        param_guidance_lines.append("        # RU: Этот инструмент может использовать параметры, не входящие напрямую во входную модель `arg`:")
        has_other_params = False
        for p in operation.parameters:
            # EN: Request body schema is mapped to `arg`. Path, query, header params might be in `ctx` or need to be passed differently.
            # RU: Схема тела запроса сопоставляется с `arg`. Параметры path, query, header могут быть в `ctx` или должны передаваться иначе.
            if p.location != ParameterLocation.BODY: # Body params are part of the request_model_name
                 p_type_hint = self._map_openapi_type_to_pydantic(p.type, is_optional=not p.required)
                 line = f"#   - {p.name} (location: {p.location.value}, type: {p_type_hint})"
                 if not p.required: line += " (optional)"
                 param_guidance_lines.append(f"        {line}")
                 has_other_params = True

        param_guidance = "\n".join(param_guidance_lines) if has_other_params else "        # EN: All parameters are expected to be in the input model `arg` (if defined) or handled via URL path construction.\n        # RU: Все параметры, как ожидается, будут во входной модели `arg` (если определена) или обработаны через построение URL-пути."

        # EN: Construct placeholder URL for HTTP call guidance.
        # RU: Конструируем URL-заполнитель для руководства по HTTP-вызову.
        url_path_template = operation.path
        path_param_vars_assignments = [] # For f-string or .format()
        path_param_placeholders_for_url = {} # For .format() style

        for p_op_param in operation.parameters:
            if p_op_param.location == ParameterLocation.PATH:
                sanitized_param_name = sanitize_variable_name(p_op_param.name)
                # EN: Placeholder for how user might get this value (e.g., from arg or ctx).
                # RU: Заполнитель для того, как пользователь может получить это значение (например, из arg или ctx).
                path_param_vars_assignments.append(f'{sanitized_param_name}=arg.{sanitized_param_name} if hasattr(arg, "{sanitized_param_name}") else "TODO_path_param_{p_op_param.name}"')
                path_param_placeholders_for_url[p_op_param.name] = f"{{{sanitized_param_name}}}" # Use original name in URL template part
                # Modify url_path_template to use sanitized names for f-string compatibility if needed,
                # but it's often clearer to use .format(**path_params_dict)

        # EN: Build the URL string, preferably using .format() for clarity with potentially many path params.
        # RU: Строим строку URL, предпочтительно используя .format() для ясности с потенциально большим количеством параметров пути.
        url_construction_comment = "# EN: Construct path_params_dict from 'arg' or 'ctx' as needed.\n        # RU: Сконструируйте path_params_dict из 'arg' или 'ctx' по мере необходимости."
        if path_param_vars_assignments:
            url_construction_comment += "\n        # Example path parameter assignments (adapt as needed):\n        # " + "\n        # ".join(path_param_vars_assignments)
            url_construction_comment += "\n        # path_params_dict = {" + ", ".join([f"'{p_name}': {sanitize_variable_name(p_name)}" for p_name in path_param_placeholders_for_url.keys()]) + "}"
            url_string = f'"http://your-api-base{operation.path}".format(**path_params_dict)'
        else:
            url_string = f'"http://your-api-base{operation.path}"'


        # EN: Tool execute method body with guidance.
        # RU: Тело метода execute Инструмента с руководством.
        execute_body = f"""
        logger.info(f"Executing tool: {{self.__class__.__name__}} with input: {{arg}}")
{param_guidance}
{url_construction_comment}
        # --- Begin User-Implemented Logic ---
        # EN: Replace with actual service call. Example for an HTTP endpoint:
        # RU: Замените фактическим вызовом сервиса. Пример для конечной точки HTTP:
        # import httpx
        # async with httpx.AsyncClient() as client:
        #     response = await client.{operation.method.value.lower()}(
        #         url={url_string},
        #         json=arg.model_dump(exclude_none=True, by_alias=True) if isinstance(arg, BaseModel) and request_model_name != "BaseModel" else None,
        #         # params={{key: val for key, val in query_params_dict.items() if val is not None}} # Construct query_params_dict if needed
        #     )
        #     response.raise_for_status() # Ensure HTTP errors are raised
        #     if "{response_model_name}" != "None" and response.content: # Check if there is content to parse
        #         return {response_model_name}(**response.json())
        #     return None # Or handle empty responses as appropriate
        raise NotImplementedError("Tool logic not implemented by the user. Implement the actual call to the service.")
        # --- End User-Implemented Logic ---
"""
        return f"""
@Server.tool(name="{tool_name_mcp}")
class {class_name}(AbstractTool[{request_model_name}, {response_model_name}]):
{class_docstring}
    async def execute(self, arg: {request_model_name}, ctx: Context) -> {response_model_name}:
{execute_body}
"""

    def _generate_function_params(self, operation: Operation, include_ctx: bool = False) -> str:
        """
        Generates a string of function parameters for an operation.
        (Currently less used as Resource/Tool signatures are fixed, but can be useful for documentation or helpers).

        Генерирует строку параметров функции для операции.
        (В настоящее время используется реже, так как сигнатуры Resource/Tool фиксированы, но может быть полезно для документации или вспомогательных функций).

        Args:
            operation (Operation): The operation to generate parameters for.
                                   Операция, для которой генерируются параметры.
            include_ctx (bool): Whether to include 'ctx: Context' as the first parameter.
                                Следует ли включать 'ctx: Context' в качестве первого параметра.

        Returns:
            str: A comma-separated string of function parameters.
                 Строка параметров функции, разделенных запятыми.
        """
        params_list = []
        if include_ctx:
            params_list.append("ctx: Context")

        # EN: Add parameters from the OpenAPI operation definition.
        # RU: Добавляем параметры из определения операции OpenAPI.
        for param in operation.parameters:
            param_name = sanitize_variable_name(param.name)
            param_type_str = self._map_openapi_type_to_pydantic(param.type, is_optional=not param.required)
            if param.required:
                params_list.append(f"{param_name}: {param_type_str}")
            else:
                # EN: _map_openapi_type_to_pydantic should have made it Optional[T] or Union[T, None]
                # EN: Default value is added for optional parameters.
                # RU: _map_openapi_type_to_pydantic должен был сделать его Optional[T] или Union[T, None]
                # RU: Для необязательных параметров добавляется значение по умолчанию.
                params_list.append(f"{param_name}: {param_type_str} = None")

        # EN: Add request body as a parameter if present.
        # RU: Добавляем тело запроса в качестве параметра, если оно присутствует.
        if operation.request_body_schema:
            body_model_name = self._map_openapi_type_to_pydantic(operation.request_body_schema.type)
            # EN: Sanitize name for payload parameter, ensure it's unique.
            # RU: Очищаем имя для параметра полезной нагрузки, обеспечиваем его уникальность.
            payload_param_name = sanitize_variable_name(operation.request_body_schema.name + "_payload") # Or a fixed name like 'request_body'
            params_list.append(f"{payload_param_name}: {body_model_name}")

        return ", ".join(params_list)


    def _generate_main(self) -> str:
        """
        Generates the main execution block (if __name__ == "__main__":) for the server,
        including transport setup and server start.

        Генерирует основной блок выполнения (if __name__ == "__main__":) для сервера,
        включая настройку транспорта и запуск сервера.

        Returns:
            str: A string for the main execution block.
                 Строка для основного блока выполнения.
        """
        transport_details = {
            "stdio": "    transport = BlockingStdioTransport()", # Indented for placement in main()
            "google_pubsub": """
    # EN: Replace with your Google Cloud Project ID and Pub/Sub topic/subscription names.
    # RU: Замените вашим ID проекта Google Cloud и именами топика/подписки Pub/Sub.
    project_id = "YOUR_GCP_PROJECT_ID"
    mcp_subscription_id = "YOUR_MCP_PUBSUB_SUBSCRIPTION"  # Subscription for messages from MCP master/client
    agent_topic_id = "YOUR_AGENT_PUBSUB_TOPIC"      # Topic for messages sent by this agent/server
    transport = GooglePubSubTransport(
        project_id=project_id,
        mcp_subscription_id=mcp_subscription_id,
        agent_topic_id=agent_topic_id,
    )"""
        }
        transport_config_str = transport_details.get(self.transport, "    transport = BlockingStdioTransport() # Default or unrecognized transport")
        if self.transport not in transport_details:
            logger.warning(f"Unsupported transport '{self.transport}' specified. Defaulting to StdioTransport.")

        return f"""
def main():
    # EN: Basic logging setup for the server.
    # RU: Базовая настройка логирования для сервера.
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    logger.info("Starting MCP server...")

{transport_config_str}

    # EN: 'app' is the Server instance, defined globally (typically after imports).
    # EN: Resources and Tools are registered to 'app' using decorators (@Server.resource, @Server.tool).
    # RU: 'app' - это экземпляр Server, определенный глобально (обычно после импортов).
    # RU: Ресурсы и Инструменты регистрируются в 'app' с помощью декораторов (@Server.resource, @Server.tool).
    app.serve(transport=transport)

if __name__ == "__main__":
    # EN: This block runs when the script is executed directly.
    # RU: Этот блок выполняется, когда скрипт запускается напрямую.
    main()
"""

    def generate_llms_txt(self, output_dir_str: str) -> bool:
        """
        Generates a human-readable llms.txt file describing the available tools and resources.
        This file is intended for use with Large Language Models (LLMs) to provide context about the API.

        Генерирует человекочитаемый файл llms.txt, описывающий доступные инструменты и ресурсы.
        Этот файл предназначен для использования с большими языковыми моделями (LLM) для предоставления контекста об API.

        Args:
            output_dir_str (str): The directory path where 'llms.txt' will be created.
                                  Путь к каталогу, в котором будет создан 'llms.txt'.

        Returns:
            bool: True if generation is successful, False otherwise.
                  True, если генерация прошла успешно, иначе False.
        """
        logger.info("Generating llms.txt content...")
        # EN: Ensure model name map is fresh if this method is called standalone or if parser changed.
        # RU: Убеждаемся, что карта имен моделей актуальна, если этот метод вызывается отдельно или если парсер изменился.
        if not self._model_name_map or self.parser.schemas.keys() != self._model_name_map.keys():
             self._prepare_model_name_map()

        content_lines = [
            "This document describes the tools (actions/commands) and resources (data queries) available through an MCP (Meta-Calling Protocol) server.",
            "The server was generated from an OpenAPI specification.",
            "---"
        ]

        # EN: Section for Resources (typically GET operations)
        # RU: Раздел для Ресурсов (обычно операции GET)
        content_lines.append("Available Resources (for querying data, typically using GET requests):")
        resource_ops = [op for op in self.parser.operations if op.method == HttpMethod.GET]
        if not resource_ops:
            content_lines.append("  No data resources (GET operations) are defined in this API.")
        else:
            for op in resource_ops:
                # EN: Resource path in MCP is often the operationId or a simplified path.
                # RU: Путь ресурса в MCP часто является operationId или упрощенным путем.
                res_mcp_path = f"{self.mount_path}/{op.operation_id}" if self.mount_path else op.operation_id
                content_lines.append(f"\nResource MCP Path: {res_mcp_path}")
                content_lines.append(f"  OpenAPI Operation: GET {op.path}")
                if op.summary: content_lines.append(f"  Summary: {op.summary}")
                if op.description: content_lines.append(f"  Description: {op.description}")

                response_type_str = "None (no specific response body defined)"
                if op.response_schema:
                     response_type_str = self._map_openapi_type_to_pydantic(op.response_schema.type)
                content_lines.append(f"  Returns (Expected Pydantic Model or Type): {response_type_str}")

                query_params = [p for p in op.parameters if p.location == ParameterLocation.QUERY]
                if query_params:
                    content_lines.append("  Query Parameters (passed in request payload to the MCP resource):")
                    for param in query_params:
                        p_type = self._map_openapi_type_to_pydantic(param.type, is_optional=not param.required)
                        req_opt = "REQUIRED" if param.required else "OPTIONAL"
                        desc = f" - Description: {param.description}" if param.description else ""
                        content_lines.append(f"    - Name: {param.name} (Type: {p_type}, {req_opt}){desc}")
                else:
                    content_lines.append("  Query Parameters: None specific to the resource query payload (path params are part of the URL).")

        content_lines.append("\n---\n")

        # EN: Section for Tools (non-GET operations)
        # RU: Раздел для Инструментов (операции, отличные от GET)
        content_lines.append("Available Tools (for actions/commands, typically using POST, PUT, DELETE, PATCH):")
        tool_ops = [op for op in self.parser.operations if op.method != HttpMethod.GET]
        if not tool_ops:
            content_lines.append("  No action tools (non-GET operations) are defined in this API.")
        else:
            for op in tool_ops:
                tool_mcp_name = op.operation_id # MCP tool name is the operationId
                content_lines.append(f"\nTool MCP Name: {tool_mcp_name}")
                content_lines.append(f"  OpenAPI Operation: {op.method.value.upper()} {op.path}")
                if op.summary: content_lines.append(f"  Summary: {op.summary}")
                if op.description: content_lines.append(f"  Description: {op.description}")

                input_model_str = "None (tool takes no specific input model, or parameters are passed differently)"
                if op.request_body_schema:
                    input_model_str = self._map_openapi_type_to_pydantic(op.request_body_schema.type)
                content_lines.append(f"  Input Model (Pydantic model for tool argument `arg`): {input_model_str}")

                # EN: List other parameters (path, query, header) which are not part of the main input model `arg`.
                # RU: Список других параметров (path, query, header), которые не являются частью основной входной модели `arg`.
                contextual_params = [p for p in op.parameters if p.location != ParameterLocation.BODY]
                if contextual_params:
                    content_lines.append("  Contextual Parameters (may be part of URL path, query string, or headers; not in `arg`):")
                    for param in contextual_params:
                        p_type = self._map_openapi_type_to_pydantic(param.type, is_optional=not param.required)
                        req_opt = "REQUIRED" if param.required else "OPTIONAL"
                        desc = f" - Description: {param.description}" if param.description else ""
                        content_lines.append(f"    - Name: {param.name} (Location: {param.location.value}, Type: {p_type}, {req_opt}){desc}")

                response_type_str = "None (tool returns no specific data structure or operation has no response body)"
                if op.response_schema:
                    response_type_str = self._map_openapi_type_to_pydantic(op.response_schema.type)
                content_lines.append(f"  Returns (Expected Pydantic Model or Type from tool execution): {response_type_str}")

        content_lines.append("\n---\nNote: Type names like 'MyModel' or 'List[ItemModel]' refer to Pydantic models defined in the generated server code. Basic types are Python types (str, int, bool, float, datetime, date, bytes, List, Dict, Optional, Any).")

        try:
            output_dir = Path(output_dir_str)
            # EN: Ensure the output directory exists.
            # RU: Убеждаемся, что выходной каталог существует.
            output_dir.mkdir(parents=True, exist_ok=True)
            llms_txt_path = output_dir / "llms.txt"
            with open(llms_txt_path, "w", encoding="utf-8") as f: # Specify UTF-8 encoding
                f.write("\n".join(content_lines))
            logger.info(f"llms.txt successfully generated at {llms_txt_path}")
            return True
        except Exception as e:
            logger.error(f"Error generating llms.txt: {e}", exc_info=True)
            return False
