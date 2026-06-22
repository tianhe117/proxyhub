"""Proxy engine configuration generators.

Dispatch to the correct generator based on bin_type.
"""

import json

from app.settings import BIN_REGISTRY


def build_outbound_config(node, local_port):
    """Build a JSON config for the outbound proxy binary.

    Args:
        node: Row-like object with .protocol, .address, .port, .config_json, .bin_type
        local_port: SOCKS5 port the binary should listen on

    Returns:
        (config_dict, config_filename_suffix)
    """
    bin_type = node['bin_type']

    if bin_type == 'xray':
        from .xray import build_xray_outbound
        return build_xray_outbound(node, local_port), 'xray_out.json'
    elif bin_type == 'sslocal':
        from .sslocal import generate_sslocal_config
        return generate_sslocal_config(node, local_port), 'sslocal_out.json'
    elif bin_type == 'sing-box':
        from .singbox import generate_singbox_config
        return generate_singbox_config(node, local_port), 'sing-box_out.json'
    else:
        raise ValueError(f'Unknown bin_type: {bin_type}')


def get_run_args(bin_type, config_path):
    """Return the command-line argument list to launch *bin_type*."""
    registry = BIN_REGISTRY[bin_type]
    return [arg.format(config=config_path) for arg in registry['run_args']]


def get_exe(bin_type):
    """Return just the executable name (e.g. 'xray', 'sslocal')."""
    return BIN_REGISTRY[bin_type]['exe']
