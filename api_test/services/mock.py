"""Mock Server lifecycle management, loopback enforcement, and Studio service bindings."""
from __future__ import annotations
import asyncio
import socket
import threading
import time
from typing import Any, Dict, Optional
import uvicorn
from api_test.mock_engine import MockApp

LOOPBACK_HOSTS = {"127.0.0.1", "::1", "localhost"}


def is_port_available(host: str, port: int) -> bool:
    sock_type = socket.AF_INET6 if ":" in host else socket.AF_INET
    try:
        with socket.socket(sock_type, socket.SOCK_STREAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind((host, port))
            return True
    except OSError:
        return False


def find_available_port(host: str, start_port: int = 8880) -> int:
    for port in range(start_port, start_port + 100):
        if is_port_available(host, port):
            return port
    sock_type = socket.AF_INET6 if ":" in host else socket.AF_INET
    with socket.socket(sock_type, socket.SOCK_STREAM) as sock:
        sock.bind((host, 0))
        return sock.getsockname()[1]


def validate_loopback_host(host: Optional[str], studio) -> str:
    if host is None:
        return "127.0.0.1"
    if not isinstance(host, str):
        raise studio.ApiError("Mock bind host는 문자열이어야 합니다.", status_code=400)
    clean_host = host.strip()
    if clean_host not in LOOPBACK_HOSTS:
        raise studio.ApiError("Mock Server는 loopback 주소(127.0.0.1, ::1, localhost)로만 바인드할 수 있습니다.", status_code=400)
    return clean_host


def validate_port(port: Any, studio) -> Optional[int]:
    if port is None:
        return None
    if type(port) is not int:
        raise studio.ApiError("포트 번호는 1 이상 65535 이하의 유효한 정수여야 합니다.", status_code=400)
    val = port
    if not (1 <= val <= 65535):
        raise studio.ApiError("포트 번호는 1 이상 65535 이하의 유효한 정수여야 합니다.", status_code=400)
    return val


def validate_seed(seed: Any, studio) -> int:
    if seed is None:
        return 42
    if type(seed) is not int:
        raise studio.ApiError("시드 값은 정수여야 합니다.", status_code=400)
    return seed


def validate_scenario(scenario: Any, studio) -> str:
    if scenario is None:
        return "default"
    s = str(scenario)
    if s not in ("default", "error_simulation", "not_found"):
        raise studio.ApiError(f"유효하지 않은 시나리오입니다: '{s}'", status_code=400)
    return s


def validate_latency(latency: Any, studio) -> int:
    if latency is None:
        return 0
    if type(latency) is not int:
        raise studio.ApiError("지연 시간은 0 이상 5000 이하의 정수여야 합니다.", status_code=400)
    val = latency
    if not (0 <= val <= 5000):
        raise studio.ApiError("지연 시간은 0 이상 5000 이하의 정수여야 합니다.", status_code=400)
    return val


def validate_overrides(overrides: Any, studio) -> dict:
    if overrides is None:
        return {}
    if not isinstance(overrides, dict):
        raise studio.ApiError("overrides는 객체여야 합니다.", status_code=400)
    for op_key, op_val in overrides.items():
        if not isinstance(op_val, dict):
            raise studio.ApiError(f"override '{op_key}'의 값은 객체여야 합니다.", status_code=400)
        if "status" in op_val:
            st = op_val["status"]
            if type(st) is not int:
                raise studio.ApiError(f"override '{op_key}'의 status는 정수여야 합니다.", status_code=400)
            if not (200 <= st <= 599):
                raise studio.ApiError(f"override '{op_key}'의 status는 200~599 사이여야 합니다.", status_code=400)
        if "latencyMs" in op_val:
            lat = op_val["latencyMs"]
            if type(lat) is not int:
                raise studio.ApiError(f"override '{op_key}'의 latencyMs는 정수여야 합니다.", status_code=400)
            if not (0 <= lat <= 5000):
                raise studio.ApiError(f"override '{op_key}'의 latencyMs는 0~5000 사이여야 합니다.", status_code=400)
        for field in ("mediaType", "exampleKey"):
            if field in op_val and (not isinstance(op_val[field], str) or not op_val[field].strip()):
                raise studio.ApiError(f"override '{op_key}'의 {field}는 비어 있지 않은 문자열이어야 합니다.", status_code=400)
        if "errorResponse" in op_val and type(op_val["errorResponse"]) is not bool:
            raise studio.ApiError(f"override '{op_key}'의 errorResponse는 boolean이어야 합니다.", status_code=400)
    return overrides


class MockServerInstance:
    def __init__(
        self,
        project_ref: str,
        host: str,
        port: int,
        document: dict,
        seed: int = 42,
        scenario: str = "default",
        default_latency_ms: int = 0,
        overrides: Optional[dict] = None,
    ):
        self.project_ref = project_ref
        self.host = host
        self.port = port
        bracketed_host = f"[{host}]" if ":" in host else host
        self.base_url = f"http://{bracketed_host}:{port}"
        self.document = document
        self.seed = seed
        self.scenario = scenario
        self.default_latency_ms = default_latency_ms
        self.overrides = overrides or {}
        self.mock_app = MockApp(
            document=document,
            seed=seed,
            scenario=scenario,
            default_latency_ms=default_latency_ms,
            overrides=overrides,
        )
        self.server: Optional[uvicorn.Server] = None
        self.thread: Optional[threading.Thread] = None
        self.loop: Optional[asyncio.AbstractEventLoop] = None
        self.started_at = time.time()

    def start(self, studio=None):
        config = uvicorn.Config(
            self.mock_app,
            host=self.host,
            port=self.port,
            log_level="error",
            access_log=False,
            timeout_graceful_shutdown=2,
        )
        server = uvicorn.Server(config)
        self.server = server

        def run_server():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            self.loop = loop
            try:
                loop.run_until_complete(server.serve())
            finally:
                pending = asyncio.all_tasks(loop)
                for task in pending:
                    task.cancel()
                if pending:
                    loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
                loop.run_until_complete(loop.shutdown_asyncgens())
                loop.run_until_complete(loop.shutdown_default_executor())
                loop.close()

        self.thread = threading.Thread(target=run_server, daemon=True, name=f"mock-{self.project_ref}")
        self.thread.start()

        deadline = time.time() + 3.0
        while time.time() < deadline:
            if server.started:
                break
            if not self.thread.is_alive():
                break
            time.sleep(0.05)

        if not server.started or not self.thread.is_alive():
            self.stop()
            message = "Mock Server 시작에 실패했습니다 (바인드 실패 또는 타임아웃)."
            if studio:
                raise studio.ApiError(message, status_code=500)
            raise RuntimeError(message)

    def stop(self):
        if self.server:
            self.server.should_exit = True
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=3.0)
            if self.thread.is_alive() and self.loop and self.loop.is_running():
                def _force_cancel():
                    for task in asyncio.all_tasks(self.loop):
                        task.cancel()
                self.loop.call_soon_threadsafe(_force_cancel)
                self.thread.join(timeout=2.0)
        if self.thread and self.thread.is_alive():
            raise RuntimeError("Mock server did not stop within the shutdown limit")

    def reset_state(self):
        if self.loop and self.loop.is_running():
            future = asyncio.run_coroutine_threadsafe(self.mock_app.reset_state(), self.loop)
            future.result(timeout=2.0)

    async def _async_update_config(self, seed: Optional[int], scenario: Optional[str], default_latency_ms: Optional[int], overrides: Optional[dict]):
        self._apply_config(seed, scenario, default_latency_ms, overrides)

    def _apply_config(self, seed: Optional[int], scenario: Optional[str], default_latency_ms: Optional[int], overrides: Optional[dict]):
        if seed is not None:
            self.seed = seed
        if scenario is not None:
            self.scenario = scenario
        if default_latency_ms is not None:
            self.default_latency_ms = default_latency_ms
        if overrides is not None:
            self.overrides = overrides
        self.mock_app.update_config(
            seed=seed,
            scenario=scenario,
            default_latency_ms=default_latency_ms,
            overrides=overrides,
        )

    def update_config(self, seed: Optional[int], scenario: Optional[str], default_latency_ms: Optional[int], overrides: Optional[dict]):
        if self.loop and self.loop.is_running():
            future = asyncio.run_coroutine_threadsafe(
                self._async_update_config(seed, scenario, default_latency_ms, overrides),
                self.loop,
            )
            future.result(timeout=2.0)
        else:
            self._apply_config(seed, scenario, default_latency_ms, overrides)

    def status_dict(self) -> dict:
        is_alive = bool(self.thread and self.thread.is_alive() and self.server and self.server.started and not self.server.should_exit)
        return {
            "status": "running" if is_alive else "stopped",
            "host": self.host,
            "port": self.port,
            "url": self.base_url,
            "seed": self.seed,
            "scenario": self.scenario,
            "defaultLatencyMs": self.default_latency_ms,
            "activeOperations": len(self.mock_app.routes),
            "requestCount": self.mock_app.request_count,
            "overrides": self.overrides,
        }


class MockServerManager:
    """Singleton manager tracking running mock servers by project reference."""
    def __init__(self):
        self._lock = threading.Lock()
        self._instances: Dict[str, MockServerInstance] = {}

    def get_instance(self, project_ref: str) -> Optional[MockServerInstance]:
        with self._lock:
            inst = self._instances.get(project_ref)
            if inst and inst.thread and inst.thread.is_alive() and inst.server and not inst.server.should_exit and inst.server.started:
                return inst
            return None

    def start_server(
        self,
        project_ref: str,
        document: dict,
        host: str = "127.0.0.1",
        port: Optional[int] = None,
        seed: int = 42,
        scenario: str = "default",
        default_latency_ms: int = 0,
        overrides: Optional[dict] = None,
        studio=None,
    ) -> MockServerInstance:
        with self._lock:
            existing = self._instances.get(project_ref)

            # Validate port availability before stopping existing
            if port is not None:
                # If existing server is on this exact port, stopping it will release it; otherwise must be available
                is_same_port = existing and existing.port == port and existing.host == host
                if not is_same_port and not is_port_available(host, port):
                    raise studio.ApiError(f"포트 {port}가 이미 사용 중입니다.", status_code=400)
                selected_port = port
            else:
                selected_port = find_available_port(host)

            # Stop existing instance only after validation succeeds
            if existing:
                existing.stop()
                del self._instances[project_ref]

            instance = MockServerInstance(
                project_ref=project_ref,
                host=host,
                port=selected_port,
                document=document,
                seed=seed,
                scenario=scenario,
                default_latency_ms=default_latency_ms,
                overrides=overrides,
            )
            instance.start(studio=studio)
            self._instances[project_ref] = instance
            return instance

    def stop_server(self, project_ref: str) -> bool:
        with self._lock:
            instance = self._instances.get(project_ref)
            if instance:
                instance.stop()
                del self._instances[project_ref]
                return True
            return False

    def reset_server(self, project_ref: str) -> bool:
        with self._lock:
            instance = self._instances.get(project_ref)
            if instance and instance.status_dict()["status"] == "running":
                instance.reset_state()
                return True
            return False

    def update_server_config(self, project_ref: str, *, seed=None, scenario=None, default_latency_ms=None, overrides=None) -> Optional[dict]:
        with self._lock:
            instance = self._instances.get(project_ref)
            if not instance or instance.status_dict()["status"] != "running":
                return None
            instance.update_config(seed, scenario, default_latency_ms, overrides)
            return instance.status_dict()

    def stop_all(self):
        with self._lock:
            for instance in list(self._instances.values()):
                instance.stop()
            self._instances.clear()


manager = MockServerManager()


def get_status(request, studio):
    reference = request.request.path_params["reference"]
    studio.ensure_example_project_enabled(reference)
    instance = manager.get_instance(reference)
    if instance:
        return request.json_response(200, instance.status_dict())
    return request.json_response(200, {
        "status": "stopped",
        "host": "127.0.0.1",
        "port": 8880,
        "url": "",
        "seed": 42,
        "scenario": "default",
        "defaultLatencyMs": 0,
        "activeOperations": 0,
        "requestCount": 0,
        "overrides": {},
    })


def start_server(request, studio):
    reference = request.request.path_params["reference"]
    studio.ensure_example_project_enabled(reference)
    store = studio.collaboration_store()
    project = store.get("projects", reference)
    if project is None:
        raise studio.ApiError("선택한 프로젝트를 찾을 수 없습니다.", status_code=404)

    body = request.read_body() if hasattr(request, "read_body") else {}
    if not isinstance(body, dict):
        raise studio.ApiError("Mock 설정은 JSON 객체여야 합니다.", status_code=400)

    host = validate_loopback_host(body.get("host", "127.0.0.1"), studio)
    port = validate_port(body.get("port"), studio)
    seed = validate_seed(body.get("seed", 42), studio)
    scenario = validate_scenario(body.get("scenario", "default"), studio)
    default_latency_ms = validate_latency(body.get("defaultLatencyMs", 0), studio)
    overrides = validate_overrides(body.get("overrides"), studio)

    document = studio.project_openapi_document(project.document)
    instance = manager.start_server(
        project_ref=reference,
        document=document,
        host=host,
        port=port,
        seed=seed,
        scenario=scenario,
        default_latency_ms=default_latency_ms,
        overrides=overrides,
        studio=studio,
    )
    return request.json_response(200, instance.status_dict())


def stop_server(request, studio):
    reference = request.request.path_params["reference"]
    studio.ensure_example_project_enabled(reference)
    manager.stop_server(reference)
    return request.json_response(200, {"status": "stopped", "message": "Mock server stopped"})


def reset_server(request, studio):
    reference = request.request.path_params["reference"]
    studio.ensure_example_project_enabled(reference)
    if not manager.reset_server(reference):
        raise studio.ApiError("실행 중인 Mock Server가 없습니다.", status_code=400)
    return request.json_response(200, {"status": "reset", "message": "Mock server state reset"})


def update_config(request, studio):
    reference = request.request.path_params["reference"]
    studio.ensure_example_project_enabled(reference)
    body = request.read_body()
    if not isinstance(body, dict):
        raise studio.ApiError("Mock 설정은 JSON 객체여야 합니다.", status_code=400)
    seed = validate_seed(body.get("seed"), studio) if "seed" in body and body.get("seed") is not None else None
    scenario = validate_scenario(body.get("scenario"), studio) if "scenario" in body and body.get("scenario") is not None else None
    default_latency_ms = validate_latency(body.get("defaultLatencyMs"), studio) if "defaultLatencyMs" in body and body.get("defaultLatencyMs") is not None else None
    overrides = validate_overrides(body.get("overrides"), studio) if "overrides" in body and body.get("overrides") is not None else None

    status = manager.update_server_config(
        reference,
        seed=seed,
        scenario=scenario,
        default_latency_ms=default_latency_ms,
        overrides=overrides,
    )
    if status is None:
        raise studio.ApiError("실행 중인 Mock Server가 없습니다.", status_code=400)
    return request.json_response(200, status)
