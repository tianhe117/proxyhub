"""Node health checking — public API.

check_node(nodes, timeout=6)  → list[CheckResult]
"""

from .model import CheckResult
from .service import check_node

__all__ = ['check_node', 'CheckResult']
