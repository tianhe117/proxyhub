"""Node health checking — public API.

check_node(nodes)  → list[CheckResult]  (CheckResult 从 app.utils 取)
"""

from .service import check_node

__all__ = ['check_node']
