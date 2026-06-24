"""Protocol, port, and bin_type validators."""

from app.settings import PROTOCOL_BIN_MAP, VALID_INBOUND_PROTOCOLS


VALID_PROTOCOLS = frozenset(list(PROTOCOL_BIN_MAP.keys()) + ['ss'])
VALID_BIN_TYPES_SET = frozenset(['xray', 'sslocal', 'sing-box'])


def is_valid_protocol(protocol):
    """Return True if *protocol* is a recognised proxy protocol string."""
    return protocol in VALID_PROTOCOLS


def is_valid_inbound_protocol(protocol):
    """Return True if *protocol* can be used as an inbound listener."""
    return protocol in VALID_INBOUND_PROTOCOLS


def is_valid_port(port):
    """Return True if *port* is an integer in [1, 65535]."""
    try:
        p = int(port)
        return 1 <= p <= 65535
    except (TypeError, ValueError):
        return False


def is_valid_bin_type(bin_type):
    """Return True if *bin_type* is one of the three supported engines."""
    return bin_type in VALID_BIN_TYPES_SET
