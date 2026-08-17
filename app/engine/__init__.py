"""Proxy engine configuration generators."""

from .service import build_outbound_config
from .xray import build_xray_inbound

__all__ = ['build_outbound_config', 'build_xray_inbound']
