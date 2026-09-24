"""OpenAPI-based Mock Server engine with deterministic synthesis, declarative state, and strict schema compliance."""
from __future__ import annotations
import asyncio
import copy
import json
import math
import random
import re
import urllib.parse
import uuid
from typing import Any, Dict, List, Optional, Tuple
from api_test.contracts.validation import schema_errors


class MockEngineError(Exception):
    """Raised when mock engine cannot generate or process a request."""
    def __init__(self, message: str, status_code: int = 500, code: str = "MOCK_ERROR"):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.code = code


def resolve_local_ref(document: dict, ref: str) -> dict:
    """Resolve an internal #/components/... reference within the OpenAPI document."""
    if not isinstance(ref, str) or not ref.startswith("#/"):
        raise MockEngineError(f"External reference '{ref}' is forbidden in mock engine", status_code=400, code="FORBIDDEN_REFERENCE")
    parts = ref[2:].split("/")
    current: Any = document
    for part in parts:
        decoded = part.replace("~1", "/").replace("~0", "~")
        if isinstance(current, dict) and decoded in current:
            current = current[decoded]
        elif isinstance(current, list) and decoded.isdigit() and int(decoded) < len(current):
            current = current[int(decoded)]
        else:
            raise MockEngineError(f"Cannot resolve reference '{ref}' in document", status_code=500, code="INVALID_REFERENCE")
    if not isinstance(current, dict):
        raise MockEngineError(f"Resolved reference '{ref}' is not an object schema", status_code=500, code="INVALID_REFERENCE")
    return current


def is_nullable(schema: dict) -> bool:
    if schema.get("nullable") is True:
        return True
    stype = schema.get("type")
    if stype == "null":
        return True
    if isinstance(stype, list) and "null" in stype:
        return True
    return False


def synthesize_schema(
    schema: dict,
    document: dict,
    prng: random.Random,
    depth: int = 0,
    visited_refs: Optional[set] = None,
) -> Any:
    """Synthesize a deterministic response value from an OpenAPI schema adhering to constraints."""
    value = _synthesize_schema(schema, document, prng, depth, visited_refs)
    if depth == 0:
        try:
            errors = schema_errors({"openapi": "3.0.3", **document}, schema, value, "#")
        except Exception as exc:
            raise MockEngineError("Schema validation failed", code="UNSUPPORTED_SCHEMA") from exc
        if errors:
            raise MockEngineError("Cannot synthesize a value satisfying this schema", code="UNSUPPORTED_SCHEMA")
    return value


def _synthesize_schema(schema, document, prng, depth, visited_refs):
    if not isinstance(schema, dict):
        raise MockEngineError("Unsupported schema shape", code="UNSUPPORTED_SCHEMA")

    if depth > 10:
        raise MockEngineError("Schema exceeds mock generation depth", code="UNSUPPORTED_SCHEMA")

    if "$ref" in schema:
        ref = schema["$ref"]
        if not isinstance(ref, str) or not ref.startswith("#/"):
            raise MockEngineError(f"External reference '{ref}' is forbidden in mock engine", status_code=400, code="FORBIDDEN_REFERENCE")
        visited = set() if visited_refs is None else visited_refs
        if ref in visited:
            raise MockEngineError("Recursive schema requires an explicit example", code="UNSUPPORTED_SCHEMA")
        resolved = resolve_local_ref(document, ref)
        return synthesize_schema(resolved, document, prng, depth=depth + 1, visited_refs=visited | {ref})

    if "allOf" in schema:
        merged: dict = {}
        for sub in schema["allOf"]:
            sub_val = synthesize_schema(sub, document, prng, depth=depth + 1, visited_refs=visited_refs)
            if isinstance(sub_val, dict):
                merged.update(sub_val)
        return merged

    if "oneOf" in schema or "anyOf" in schema:
        options = schema.get("oneOf") or schema.get("anyOf") or []
        if not options:
            raise MockEngineError("Empty schema alternatives", code="UNSUPPORTED_SCHEMA")
        return synthesize_schema(options[0], document, prng, depth=depth + 1, visited_refs=visited_refs)

    if schema.get("enum"):
        return schema["enum"][0]

    schema_type = schema.get("type")

    # Object synthesis
    if schema_type == "object" or "properties" in schema:
        result = {}
        properties = schema.get("properties", {})
        for prop_name, prop_schema in properties.items():
            result[prop_name] = synthesize_schema(prop_schema, document, prng, depth=depth + 1, visited_refs=visited_refs)
        return result

    # Array synthesis
    if schema_type == "array":
        items_schema = schema.get("items", {})
        min_items = schema.get("minItems")
        max_items = schema.get("maxItems")
        if min_items is not None and max_items is not None and min_items > max_items:
            raise MockEngineError(f"Contradictory schema: minItems ({min_items}) > maxItems ({max_items})", status_code=500, code="INVALID_SCHEMA")
        target_count = 2
        if min_items is not None:
            target_count = max(target_count, min_items)
        if max_items is not None:
            target_count = min(target_count, max_items)
        if target_count > 100:
            raise MockEngineError("Array exceeds mock generation limit (100)", code="UNSUPPORTED_SCHEMA")
        count = target_count
        return [synthesize_schema(items_schema, document, prng, depth=depth + 1, visited_refs=visited_refs) for _ in range(count)]

    # String synthesis
    if schema_type == "string":
        min_len = schema.get("minLength")
        max_len = schema.get("maxLength")
        if min_len is not None and min_len > 65536:
            raise MockEngineError("String exceeds mock generation limit", code="UNSUPPORTED_SCHEMA")
        if min_len is not None and max_len is not None and min_len > max_len:
            raise MockEngineError(f"Contradictory schema: minLength ({min_len}) > maxLength ({max_len})", status_code=500, code="INVALID_SCHEMA")

        fmt = schema.get("format", "")
        if fmt == "date-time":
            s = "2026-09-21T00:00:00Z"
        elif fmt == "date":
            s = "2026-09-21"
        elif fmt == "uuid":
            s = str(uuid.UUID(int=prng.getrandbits(128), version=4))
        elif fmt == "email":
            s = "user@example.test"
        elif fmt == "uri":
            s = "https://example.test"
        else:
            s = schema.get("default", "mock_string")

        if max_len is not None and len(s) > max_len:
            s = s[:max_len]
        if min_len is not None and len(s) < min_len:
            s = s + ("s" * (min_len - len(s)))
        return s

    # Integer synthesis
    if schema_type == "integer":
        min_val = schema.get("minimum")
        if "exclusiveMinimum" in schema:
            ex_min = schema["exclusiveMinimum"]
            if isinstance(ex_min, bool):
                if ex_min and min_val is not None:
                    min_val = math.floor(min_val) + 1
            else:
                min_val = math.floor(ex_min) + 1

        max_val = schema.get("maximum")
        if "exclusiveMaximum" in schema:
            ex_max = schema["exclusiveMaximum"]
            if isinstance(ex_max, bool):
                if ex_max and max_val is not None:
                    max_val = math.ceil(max_val) - 1
            else:
                max_val = math.ceil(ex_max) - 1

        min_val = math.ceil(min_val) if min_val is not None else None
        max_val = math.floor(max_val) if max_val is not None else None

        if min_val is not None and max_val is not None and min_val > max_val:
            raise MockEngineError(f"Contradictory schema: minimum ({min_val}) > maximum ({max_val})", status_code=500, code="INVALID_SCHEMA")

        if "default" in schema:
            def_val = schema["default"]
            if (min_val is None or def_val >= min_val) and (max_val is None or def_val <= max_val):
                return def_val

        if min_val is not None and max_val is not None:
            if min_val <= 0 <= max_val:
                return 0
            return min_val
        elif min_val is not None:
            return max(min_val, 1)
        elif max_val is not None:
            return min(max_val, 0)
        return 1

    # Number synthesis
    if schema_type == "number":
        min_val = schema.get("minimum")
        if "exclusiveMinimum" in schema:
            ex_min = schema["exclusiveMinimum"]
            if isinstance(ex_min, bool):
                if ex_min and min_val is not None:
                    min_val = float(min_val) + 0.1
            else:
                min_val = float(ex_min) + 0.1

        max_val = schema.get("maximum")
        if "exclusiveMaximum" in schema:
            ex_max = schema["exclusiveMaximum"]
            if isinstance(ex_max, bool):
                if ex_max and max_val is not None:
                    max_val = float(max_val) - 0.1
            else:
                max_val = float(ex_max) - 0.1

        if min_val is not None and max_val is not None and min_val > max_val:
            raise MockEngineError(f"Contradictory schema: minimum ({min_val}) > maximum ({max_val})", status_code=500, code="INVALID_SCHEMA")

        if "default" in schema:
            def_val = float(schema["default"])
            if (min_val is None or def_val >= min_val) and (max_val is None or def_val <= max_val):
                return def_val

        if min_val is not None and max_val is not None:
            if min_val <= 0.0 <= max_val:
                return 0.0
            return float(min_val)
        elif min_val is not None:
            return max(float(min_val), 1.0)
        elif max_val is not None:
            return min(float(max_val), 0.0)
        return 1.0

    if schema_type == "boolean":
        return schema.get("default", True)

    if is_nullable(schema):
        return None

    raise MockEngineError(f"Unsupported schema type '{schema_type}' cannot be synthesized", status_code=500, code="UNSUPPORTED_SCHEMA")


def resolve_operation_response(
    operation: dict,
    document: dict,
    prng: random.Random,
    status_override: Optional[int] = None,
    example_key: Optional[str] = None,
    preferred_media_type: Optional[str] = None,
) -> Tuple[int, str, Optional[Any]]:
    """Determine status code, media type, and response payload adhering to priority rules:
    named examples > example > schema example > schema examples[0] > schema default > schema synthesis.
    Returns (status_code, media_type, payload).
    """
    responses = operation.get("responses", {})
    if not responses:
        status = status_override or 200
        return status, "application/json", {"status": status, "message": "Mock operation"}

    # Find matching status response
    if status_override is not None:
        target_status = status_override
    else:
        success_codes = [int(c) for c in responses if c.isdigit() and 200 <= int(c) < 300]
        if success_codes:
            target_status = min(success_codes)
        else:
            digit_codes = [int(c) for c in responses if c.isdigit()]
            target_status = min(digit_codes) if digit_codes else 200

    # Body prohibited for 204, 205, 304
    if target_status in (204, 205, 304):
        return target_status, "application/json", None

    status_str = str(target_status)
    resp_spec = responses.get(status_str)
    if not resp_spec:
        resp_spec = responses.get(f"{target_status // 100}XX") or responses.get("default")

    if not resp_spec or not isinstance(resp_spec, dict):
        return target_status, "application/json", {"status": target_status, "message": f"Mock response for status {target_status}"}

    if "$ref" in resp_spec:
        resp_spec = resolve_local_ref(document, resp_spec["$ref"])

    content = resp_spec.get("content", {})
    if not content:
        return target_status, "application/json", None

    # Choose media type
    media_type = "application/json"
    if preferred_media_type and preferred_media_type in content:
        media_type = preferred_media_type
    elif "application/json" in content:
        media_type = "application/json"
    elif preferred_media_type:
        matched_type = None
        for ct in content:
            if preferred_media_type == "*/*" or (preferred_media_type.endswith("/*") and ct.startswith(preferred_media_type[:-1])):
                matched_type = ct
                break
        media_type = matched_type or next(iter(content))
    else:
        media_type = next(iter(content))

    media_spec = content.get(media_type, {})

    # 1. Named examples in media_spec
    examples = media_spec.get("examples", {})
    if example_key and (not isinstance(examples, dict) or example_key not in examples):
        raise MockEngineError("Selected example is not declared for this response", 400, "INVALID_SELECTION")
    if isinstance(examples, dict) and examples:
        if example_key and example_key in examples:
            ex_val = examples[example_key]
            val = ex_val.get("value", ex_val) if isinstance(ex_val, dict) else ex_val
            return target_status, media_type, val
        first_key = next(iter(examples))
        ex_val = examples[first_key]
        val = ex_val.get("value", ex_val) if isinstance(ex_val, dict) else ex_val
        return target_status, media_type, val

    # 2. Single example in media_spec
    if "example" in media_spec:
        return target_status, media_type, media_spec["example"]

    # 3. Schema example or default
    schema = media_spec.get("schema")
    if isinstance(schema, dict):
        if "$ref" in schema:
            resolved_schema = resolve_local_ref(document, schema["$ref"])
        else:
            resolved_schema = schema

        if "example" in resolved_schema:
            return target_status, media_type, resolved_schema["example"]
        if "examples" in resolved_schema and isinstance(resolved_schema["examples"], list) and resolved_schema["examples"]:
            return target_status, media_type, resolved_schema["examples"][0]
        if "default" in resolved_schema:
            return target_status, media_type, resolved_schema["default"]

        # 4. Synthesize deterministically from schema
        synthesized = synthesize_schema(schema, document, prng)
        return target_status, media_type, synthesized

    return target_status, media_type, None


class CompiledRoute:
    def __init__(self, path_template: str, path_spec: dict):
        self.path_template = path_template
        self.path_spec = path_spec
        segments = [s for s in path_template.strip("/").split("/") if s]
        self.segments = segments
        self.param_names: List[str] = []
        regex_parts = []
        static_count = 0
        param_count = 0
        for seg in segments:
            if seg.startswith("{") and seg.endswith("}"):
                pname = seg[1:-1]
                self.param_names.append(pname)
                regex_parts.append(r"([^/]+)")
                param_count += 1
            else:
                regex_parts.append(re.escape(seg))
                static_count += 1
        regex_str = "^/" + "/".join(regex_parts) + "/?$" if segments else "^/?$"
        self.regex = re.compile(regex_str)
        self.static_count = static_count
        self.param_count = param_count

        # Item route detection: last segment is parameter
        self.is_item_route = len(segments) >= 1 and segments[-1].startswith("{") and segments[-1].endswith("}")
        if self.is_item_route:
            self.item_param_name = segments[-1][1:-1]
            parent_segs = segments[:-1]
            self.collection_template = "/" + "/".join(parent_segs) if parent_segs else "/"
        else:
            self.item_param_name = None
            self.collection_template = "/" + "/".join(segments) if segments else "/"

    def match(self, path: str) -> Optional[Dict[str, str]]:
        m = self.regex.match(path)
        if not m:
            return None
        values = [urllib.parse.unquote(v) for v in m.groups()]
        return dict(zip(self.param_names, values))

    def resolve_collection_key(self, path_params: Dict[str, str]) -> str:
        """Instantiate parent collection template with actual path parameter values."""
        key = self.collection_template
        for param_name, param_val in path_params.items():
            if param_name != self.item_param_name:
                key = key.replace(f"{{{param_name}}}", str(param_val))
        return key


class DeclarativeStateStore:
    """In-memory declarative state store with monotonic ID counters and byte/item limits."""
    MAX_ITEMS_PER_COLLECTION = 1000
    MAX_TOTAL_ITEMS = 10000
    MAX_STATE_BYTES = 10 * 1024 * 1024  # 10MB limit
    MAX_ITEM_BYTES = 1024 * 1024

    def __init__(self, seed: int = 42, scenario: str = "default"):
        self.seed = seed
        self.scenario = scenario
        self.lock = asyncio.Lock()
        self.collections: Dict[str, Dict[str, dict]] = {}
        self._next_ids: Dict[str, int] = {}
        self._total_bytes: int = 0
        self.prng = random.Random(seed)
        self._init_scenario()

    def _init_scenario(self):
        self.collections.clear()
        self._next_ids.clear()
        self._total_bytes = 0
        self.prng = random.Random(self.seed)

    async def reset(self):
        async with self.lock:
            self._init_scenario()

    async def get_item(self, collection: str, item_id: str) -> Optional[dict]:
        async with self.lock:
            return copy.deepcopy(self.collections.get(collection, {}).get(str(item_id)))

    async def list_items(self, collection: str) -> List[dict]:
        async with self.lock:
            return copy.deepcopy(list(self.collections.get(collection, {}).values()))

    async def create_item(self, collection: str, body: dict) -> dict:
        async with self.lock:
            col = self.collections.get(collection, {})

            total_items = sum(len(c) for c in self.collections.values())
            if len(col) >= self.MAX_ITEMS_PER_COLLECTION or total_items >= self.MAX_TOTAL_ITEMS:
                raise MockEngineError(f"State item limit exceeded for collection '{collection}'", status_code=413, code="STATE_LIMIT_EXCEEDED")

            item = copy.deepcopy(body)
            explicit_id = item.get("id") or item.get("uuid")
            next_id = self._next_ids.get(collection, 1)
            if explicit_id is not None:
                str_id = str(explicit_id)
                if str_id in col:
                    raise MockEngineError(f"Item with ID '{str_id}' already exists in collection '{collection}'", status_code=409, code="CONFLICT")
                item_id = str_id
                if item_id.isdigit():
                    next_id = max(next_id, int(item_id) + 1)
            else:
                curr = next_id
                while str(curr) in col:
                    curr += 1
                item_id = str(curr)
                next_id = curr + 1

            item["id"] = item_id

            item_bytes = len(json.dumps(item, default=str).encode("utf-8"))
            if item_bytes > self.MAX_ITEM_BYTES:
                raise MockEngineError("Mock item exceeds maximum response size (1MB)", status_code=413, code="RESPONSE_TOO_LARGE")
            if self._total_bytes + item_bytes > self.MAX_STATE_BYTES:
                raise MockEngineError("Mock server total state byte limit exceeded (10MB)", status_code=413, code="STATE_LIMIT_EXCEEDED")

            self._total_bytes += item_bytes
            self._next_ids[collection] = next_id
            if collection not in self.collections:
                self.collections[collection] = col
            col[item_id] = item
            return copy.deepcopy(item)

    async def update_item(self, collection: str, item_id: str, body: dict) -> Optional[dict]:
        async with self.lock:
            col = self.collections.get(collection, {})
            str_id = str(item_id)
            if str_id not in col:
                return None
            old_item = col[str_id]
            old_bytes = len(json.dumps(old_item, default=str).encode("utf-8"))

            new_item = copy.deepcopy(old_item)
            new_item.update(body)
            new_item["id"] = str_id

            new_bytes = len(json.dumps(new_item, default=str).encode("utf-8"))
            if new_bytes > self.MAX_ITEM_BYTES:
                raise MockEngineError("Mock item exceeds maximum response size (1MB)", status_code=413, code="RESPONSE_TOO_LARGE")
            if self._total_bytes - old_bytes + new_bytes > self.MAX_STATE_BYTES:
                raise MockEngineError("Mock server total state byte limit exceeded (10MB)", status_code=413, code="STATE_LIMIT_EXCEEDED")

            self._total_bytes = self._total_bytes - old_bytes + new_bytes
            col[str_id] = new_item
            return copy.deepcopy(new_item)

    async def delete_item(self, collection: str, item_id: str) -> bool:
        async with self.lock:
            col = self.collections.get(collection, {})
            str_id = str(item_id)
            if str_id in col:
                old_item = col.pop(str_id)
                old_bytes = len(json.dumps(old_item, default=str).encode("utf-8"))
                self._total_bytes = max(0, self._total_bytes - old_bytes)
                return True
            return False


class MockApp:
    """ASGI application serving project OpenAPI mock endpoints."""
    MAX_BODY_BYTES = 1024 * 1024  # 1MB limit for incoming requests
    MAX_RESPONSE_BYTES = 1024 * 1024

    def __init__(
        self,
        document: dict,
        seed: int = 42,
        scenario: str = "default",
        default_latency_ms: int = 0,
        overrides: Optional[dict] = None,
    ):
        self.document = copy.deepcopy(document)
        self.seed = seed
        self.scenario = scenario
        self.default_latency_ms = min(5000, max(0, default_latency_ms))
        self.overrides = copy.deepcopy(overrides or {})
        self.state_store = DeclarativeStateStore(seed=seed, scenario=scenario)
        self.request_count = 0
        self.state_generation = 0
        self.lock = asyncio.Lock()

        # Compile and sort routes (static segments prioritized over params)
        self.routes: List[CompiledRoute] = []
        paths = self.document.get("paths", {})
        for path_template, path_spec in paths.items():
            if isinstance(path_spec, dict):
                self.routes.append(CompiledRoute(path_template, path_spec))
        self.routes.sort(key=lambda r: (-r.static_count, r.param_count, -len(r.path_template)))

    def update_config(
        self,
        seed: Optional[int] = None,
        scenario: Optional[str] = None,
        default_latency_ms: Optional[int] = None,
        overrides: Optional[dict] = None,
    ):
        reset_required = (seed is not None and seed != self.seed) or (scenario is not None and scenario != self.scenario)
        if seed is not None:
            self.seed = seed
        if scenario is not None:
            self.scenario = scenario
        if default_latency_ms is not None:
            self.default_latency_ms = min(5000, max(0, default_latency_ms))
        if overrides is not None:
            self.overrides = copy.deepcopy(overrides)
        if reset_required:
            self.state_generation += 1
            self.state_store = DeclarativeStateStore(seed=self.seed, scenario=self.scenario)

    async def reset_state(self):
        # Requests waiting on latency/body cannot populate the new state.
        self.state_generation += 1
        self.state_store = DeclarativeStateStore(seed=self.seed, scenario=self.scenario)

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http" and scope["method"].upper() == "HEAD":
            original_send = send
            async def send_head(message):
                if message["type"] == "http.response.body":
                    message = {**message, "body": b""}
                await original_send(message)
            send = send_head
        try:
            await self._handle_request(scope, receive, send)
        except MockEngineError as exc:
            await self._send_json(send, exc.status_code, {"error": exc.message, "code": exc.code})

    async def _handle_request(self, scope, receive, send):
        if scope["type"] != "http":
            return

        async with self.lock:
            self.request_count += 1

        path = scope["path"]
        method = scope["method"].upper()
        generation = self.state_generation

        # Internal management endpoints
        if path == "/__mock/health":
            await self._send_json(send, 200, {"status": "ok", "mock": True, "scenario": self.scenario})
            return
        if path == "/__mock/reset" and method == "POST":
            await self.reset_state()
            await self._send_json(send, 200, {"status": "reset", "message": "State reset"})
            return

        # Match route
        matched_route = None
        path_params = {}
        for route in self.routes:
            params = route.match(path)
            if params is not None:
                matched_route = route
                path_params = params
                break

        if not matched_route:
            await self._send_json(send, 404, {"error": f"Path '{path}' not found in mock specification", "code": "PATH_NOT_FOUND"})
            return

        # Check HTTP method
        method_lower = method.lower()
        if method_lower not in matched_route.path_spec and not (method == "HEAD" and "get" in matched_route.path_spec):
            allowed = [m.upper() for m in matched_route.path_spec if m in ("get", "post", "put", "delete", "patch", "options", "head")]
            headers = [("allow", ", ".join(allowed))]
            await self._send_json(send, 405, {"error": f"Method '{method}' not allowed for path '{path}'", "code": "METHOD_NOT_ALLOWED"}, headers=headers)
            return

        op_spec = matched_route.path_spec.get(method_lower) or matched_route.path_spec.get("get", {})
        op_id = op_spec.get("operationId") or f"{method} {matched_route.path_template}"

        # Operation overrides & latency
        override = self.overrides.get(op_id) or self.overrides.get(matched_route.path_template, {})
        op_latency = override.get("latencyMs") if override.get("latencyMs") is not None else self.default_latency_ms
        if op_latency > 0:
            await asyncio.sleep(min(5000, op_latency) / 1000.0)

        # Receive request body with size limit
        body_bytes = b""
        more_body = True
        while more_body:
            msg = await receive()
            if msg.get("type") == "http.disconnect":
                return
            chunk = msg.get("body", b"")
            if len(body_bytes) + len(chunk) > self.MAX_BODY_BYTES:
                await self._send_json(send, 413, {"error": "Request body exceeds maximum size limit (1MB)", "code": "PAYLOAD_TOO_LARGE"})
                return
            body_bytes += chunk
            more_body = msg.get("more_body", False)

        if generation != self.state_generation:
            raise MockEngineError("Mock state changed while the request was pending; retry the request", 409, "STATE_CHANGED")

        req_body = {}
        if body_bytes:
            try:
                req_body = json.loads(body_bytes.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                raise MockEngineError("Invalid JSON request body", 400, "INVALID_BODY") from None

        # Parse client accept header
        accept_header = "application/json"
        for hname, hval in scope.get("headers", []):
            if hname.lower() == b"accept":
                accept_header = hval.decode("utf-8", errors="replace")
                break
        preferred_media_type = override.get("mediaType") or accept_header

        # Check if collection has a corresponding detail route (R1 scope isolation)
        collection_key = matched_route.resolve_collection_key(path_params)
        has_detail_route = any(
            r.is_item_route and r.collection_template == matched_route.collection_template
            for r in self.routes
        )

        # Target status selection
        if override.get("status") is not None:
            target_status = int(override["status"])
        elif self.scenario == "error_simulation" or override.get("errorResponse"):
            target_status = 500
        elif self.scenario == "not_found":
            target_status = 404
        else:
            target_status = None

        # R3: If status override or scenario demands an error (>= 400), return error and DO NOT mutate state!
        if target_status is not None and target_status >= 400:
            code, mtype, payload = resolve_operation_response(
                op_spec, self.document, self.state_store.prng,
                status_override=target_status,
                example_key=override.get("exampleKey"),
                preferred_media_type=preferred_media_type,
            )
            err_payload = payload or {"error": f"Mock error for '{op_id}'", "code": "MOCK_ERROR", "status": target_status}
            if method == "HEAD":
                await self._send_response(send, target_status, b"", mtype)
            else:
                await self._send_content(send, target_status, err_payload, mtype)
            return

        # An explicit response selection uses the specification without CRUD mutation.
        # This also permits replaying an example before a resource exists in state.
        if override.get("exampleKey") or override.get("mediaType") or preferred_media_type not in ("application/json", "*/*"):
            code, mtype, payload = resolve_operation_response(
                op_spec, self.document, self.state_store.prng,
                status_override=target_status, example_key=override.get("exampleKey"),
                preferred_media_type=preferred_media_type,
            )
            if override.get("mediaType") and mtype != override["mediaType"]:
                raise MockEngineError("Selected media type is not declared for this response", 400, "INVALID_SELECTION")
            if method == "HEAD":
                await self._send_response(send, code, b"", mtype)
            else:
                await self._send_content(send, code, payload, mtype)
            return

        # Declarative CRUD state machine handling
        if matched_route.is_item_route and has_detail_route:
            item_id = path_params.get(matched_route.item_param_name, "")
            if method == "GET":
                stored = await self.state_store.get_item(collection_key, item_id)
                if stored is not None:
                    code = target_status or 200
                    await self._send_content(send, code, stored, "application/json")
                    return
                # 404 Not Found
                _, mtype, err_resp = resolve_operation_response(
                    op_spec, self.document, self.state_store.prng, status_override=404, preferred_media_type=preferred_media_type
                )
                await self._send_content(send, 404, err_resp or {"error": f"Item '{item_id}' not found in '{collection_key}'", "code": "NOT_FOUND"}, mtype)
                return
            elif method in ("PUT", "PATCH"):
                if not isinstance(req_body, dict):
                    raise MockEngineError("CRUD request body must be a JSON object", 400, "INVALID_BODY")
                updated = await self.state_store.update_item(collection_key, item_id, req_body)
                if updated is not None:
                    code = target_status or 200
                    await self._send_content(send, code, updated, "application/json")
                    return
                await self._send_json(send, 404, {"error": f"Item '{item_id}' not found for update", "code": "NOT_FOUND"})
                return
            elif method == "DELETE":
                deleted = await self.state_store.delete_item(collection_key, item_id)
                if deleted:
                    code = target_status or 204
                    await self._send_response(send, code, b"", "application/json")
                    return
                await self._send_json(send, 404, {"error": f"Item '{item_id}' not found for deletion", "code": "NOT_FOUND"})
                return

        elif method == "POST" and not matched_route.is_item_route and has_detail_route:
            if not isinstance(req_body, dict):
                raise MockEngineError("CRUD request body must be a JSON object", 400, "INVALID_BODY")
            # Resolve default schema response to merge with req_body (R3, R6)
            code, mtype, synth = resolve_operation_response(
                op_spec, self.document, self.state_store.prng,
                status_override=target_status or 201,
                example_key=override.get("exampleKey"),
                preferred_media_type=preferred_media_type,
            )
            item_to_store = copy.deepcopy(synth) if isinstance(synth, dict) else {}
            item_to_store.update(req_body)
            # If client didn't supply explicit id in req_body, remove synth placeholder so create_item generates one
            if "id" not in req_body and "uuid" not in req_body and "id" in item_to_store:
                del item_to_store["id"]
            created = await self.state_store.create_item(collection_key, item_to_store)
            await self._send_content(send, code, created, mtype)
            return

        elif method == "GET" and not matched_route.is_item_route and has_detail_route:
            items = await self.state_store.list_items(collection_key)
            if items:
                code, mtype, default_val = resolve_operation_response(
                    op_spec, self.document, self.state_store.prng,
                    status_override=target_status,
                    example_key=override.get("exampleKey"),
                    preferred_media_type=preferred_media_type,
                )
                if isinstance(default_val, dict) and "items" in default_val:
                    resp_val = copy.deepcopy(default_val)
                    resp_val["items"] = items
                    await self._send_content(send, code, resp_val, mtype)
                    return
                elif isinstance(default_val, list):
                    await self._send_content(send, code, items, mtype)
                    return

        # General OpenAPI example / schema resolution
        code, mtype, payload = resolve_operation_response(
            op_spec, self.document, self.state_store.prng,
            status_override=target_status,
            example_key=override.get("exampleKey"),
            preferred_media_type=preferred_media_type,
        )

        if method == "HEAD" or code in (204, 205, 304):
            await self._send_response(send, code, b"", mtype)
            return

        await self._send_content(send, code, payload, mtype)

    async def _send_content(self, send, status: int, payload: Any, media_type: str, headers: Optional[List[Tuple[str, str]]] = None):
        """Send response formatted appropriately for media type (JSON, text, etc.)."""
        if status in (204, 205, 304):
            await self._send_response(send, status, b"", media_type, headers=headers)
            return

        if media_type.startswith("text/"):
            body_str = str(payload) if payload is not None else ""
            content_type = f"{media_type}; charset=utf-8" if "charset" not in media_type else media_type
            await self._send_response(send, status, body_str.encode("utf-8"), content_type, headers=headers)
            return

        if media_type == "application/octet-stream" and isinstance(payload, bytes):
            await self._send_response(send, status, payload, media_type, headers=headers)
            return

        # Default: JSON serialization
        body_bytes = json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8")
        await self._send_response(send, status, body_bytes, media_type, headers=headers)

    async def _send_json(self, send, status: int, payload: Any, headers: Optional[List[Tuple[str, str]]] = None):
        await self._send_content(send, status, payload, "application/json", headers=headers)

    async def _send_response(self, send, status: int, body: bytes, content_type: str, headers: Optional[List[Tuple[str, str]]] = None):
        if status in (204, 205, 304):
            body = b""
        if len(body) > self.MAX_RESPONSE_BYTES:
            raise MockEngineError("Mock response exceeds maximum size (1MB)", status_code=413, code="RESPONSE_TOO_LARGE")
        response_headers = [(b"content-type", content_type.encode("utf-8"))]
        if status not in (204, 205, 304):
            response_headers.append((b"content-length", str(len(body)).encode("utf-8")))
        if headers:
            for k, v in headers:
                response_headers.append((k.lower().encode("utf-8"), v.encode("utf-8")))

        await send({
            "type": "http.response.start",
            "status": status,
            "headers": response_headers,
        })
        await send({
            "type": "http.response.body",
            "body": body,
        })
