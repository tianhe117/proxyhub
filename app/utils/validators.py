"""Protocol and inbound validators for frontend data validation."""

from app.settings import SUPPORTED_PROTOCOLS, VALID_INBOUND_PROTOCOLS


def is_valid_protocol(protocol):
    """Return True if *protocol* is a supported outbound protocol."""
    return protocol in SUPPORTED_PROTOCOLS


def is_valid_inbound_protocol(protocol):
    """Return True if *protocol* can be used as an inbound listener."""
    return protocol in VALID_INBOUND_PROTOCOLS
