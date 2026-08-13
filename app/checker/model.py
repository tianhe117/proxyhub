"""CheckResult — result type for health checks."""

from dataclasses import dataclass


@dataclass
class CheckResult:
    success: bool
    tcp_latency_ms: int       # TCP handshake latency (-1 if failed)
    url_latency_ms: int       # URL latency (-1 if not done)
    http_code: str            # URL HTTP code ("0" if not done)
    error: str
