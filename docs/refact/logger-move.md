# logger 迁移

`app/logger.py` → `app/utils/logger.py`，和 `helpers.py`、`validators.py` 同属通用工具。

改动范围：所有 `from app.logger` → `from app.utils.logger`。
