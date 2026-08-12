"""Proxy engine configuration generators.

Dispatch to the correct generator based on bin_type.
"""

import json

from app.settings import BIN_REGISTRY
from .xray import build_xray_outbound
from .sslocal import generate_sslocal_config
from .singbox import generate_singbox_config


def build_outbound_config(node, local_port):
    """Build a JSON config for the outbound proxy binary.

    Args:
        node:       dict with protocol, address, port, config_json, bin_type
        local_port: SOCKS5 port the binary should listen on

    Returns:
        config dict  (JSON-serialisable)
    """
    # Parse config_json once — sub-modules receive the parsed dict
    try:
        cfg = node['config_json']
    except (KeyError, TypeError):
        cfg = {}
    if isinstance(cfg, str):
        try:
            cfg = json.loads(cfg)
        except (json.JSONDecodeError, TypeError):
            cfg = {}
    cfg = cfg or {}

    bin_type = node['bin_type']

    if bin_type == 'xray':
        return build_xray_outbound(node, local_port, cfg)
    elif bin_type == 'sslocal':
        return generate_sslocal_config(node, local_port, cfg)
    elif bin_type == 'sing-box':
        return generate_singbox_config(node, local_port, cfg)
    else:
        raise ValueError(f'Unknown bin_type: {bin_type}')


def get_run_args(bin_type, config_path):
    """Return the command-line argument list to launch *bin_type*."""
    registry = BIN_REGISTRY[bin_type]
    return [arg.format(config=config_path) for arg in registry['run_args']]


def get_exe(bin_type):
    """Return just the executable name (e.g. 'xray', 'sslocal')."""
    return BIN_REGISTRY[bin_type]['exe']
