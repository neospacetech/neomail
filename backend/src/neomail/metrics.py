"""Minimal Prometheus metrics: request counts and latency per route.

Kept dependency-free on purpose; the text exposition format is small and stable.
"""

import time
from collections import defaultdict
from dataclasses import dataclass, field
from threading import Lock

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from neomail import COMPONENT, __version__

PROMETHEUS_MEDIA_TYPE = "text/plain; version=0.0.4; charset=utf-8"


def _escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")


def _labels(**labels: str) -> str:
    return ",".join(f'{key}="{_escape(value)}"' for key, value in labels.items())


@dataclass
class Metrics:
    prefix: str = COMPONENT
    _requests: defaultdict[tuple[str, str, str], int] = field(
        default_factory=lambda: defaultdict(int)
    )
    _duration_sum: defaultdict[tuple[str, str], float] = field(
        default_factory=lambda: defaultdict(float)
    )
    _duration_count: defaultdict[tuple[str, str], int] = field(
        default_factory=lambda: defaultdict(int)
    )
    _lock: Lock = field(default_factory=Lock)

    def observe(self, method: str, route: str, status: int, seconds: float) -> None:
        with self._lock:
            self._requests[(method, route, str(status))] += 1
            self._duration_sum[(method, route)] += seconds
            self._duration_count[(method, route)] += 1

    def render(self) -> str:
        p = self.prefix
        lines = [
            f"# HELP {p}_build_info Build information.",
            f"# TYPE {p}_build_info gauge",
            f"{p}_build_info{{{_labels(version=__version__)}}} 1",
            f"# HELP {p}_http_requests_total HTTP requests by method, route and status.",
            f"# TYPE {p}_http_requests_total counter",
        ]
        with self._lock:
            for (method, route, status), count in sorted(self._requests.items()):
                labels = _labels(method=method, route=route, status=status)
                lines.append(f"{p}_http_requests_total{{{labels}}} {count}")
            lines += [
                f"# HELP {p}_http_request_duration_seconds Time to send the response head.",
                f"# TYPE {p}_http_request_duration_seconds summary",
            ]
            for (method, route), total in sorted(self._duration_sum.items()):
                labels = _labels(method=method, route=route)
                count = self._duration_count[(method, route)]
                lines.append(f"{p}_http_request_duration_seconds_sum{{{labels}}} {total:.6f}")
                lines.append(f"{p}_http_request_duration_seconds_count{{{labels}}} {count}")
        return "\n".join(lines) + "\n"


class MetricsMiddleware:
    """ASGI middleware recording one observation per HTTP request.

    Routes are labelled by their path template (``/api/v1/messages/{message_id}``),
    never the concrete path, to keep label cardinality bounded.
    """

    def __init__(self, app: ASGIApp, metrics: Metrics) -> None:
        self.app = app
        self.metrics = metrics

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        start = time.perf_counter()
        status = 500

        async def send_wrapper(message: Message) -> None:
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
                route = scope.get("route")
                template = getattr(route, "path_format", None) or "unmatched"
                self.metrics.observe(scope["method"], template, status, time.perf_counter() - start)
            await send(message)

        await self.app(scope, receive, send_wrapper)
