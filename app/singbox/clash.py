"""clash_api client: /delay, GET/PUT /proxies.

Always reaches the resident sing-box clash_api at 127.0.0.1:9090.
"""


def get_delay(node_name: str, url: str, timeout: int) -> dict:
    raise NotImplementedError("Health-check layer to be refined")


def get_proxies() -> dict:
    raise NotImplementedError("Health-check layer to be refined")


def select_proxy(group: str, node: str) -> bool:
    raise NotImplementedError("Scheduler layer to be refined")
