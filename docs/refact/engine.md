# engine 最终架构

## 目标

薄 `__init__.py` 聚合导出，配置生成逻辑独立为 `service.py`。对外接口稳定，内部自由重组。

```
app/engine/
├── __init__.py     # 聚合导出（纯接口表）
├── service.py      # build_outbound_config + get_run_args + get_exe — 调度/工具
├── xray.py         # build_xray_outbound + build_xray_inbound — Xray 生成器
├── sslocal.py      # generate_sslocal_config — sslocal 生成器
└── singbox.py      # generate_singbox_config — sing-box 生成器
```

## 各模块职责

### __init__.py — 聚合导出

```python
from .service import build_outbound_config, get_run_args, get_exe
from .xray import build_xray_inbound  # 或只导出 build_outbound_config

__all__ = ['build_outbound_config']
```

对外主接口是 `build_outbound_config`。`get_run_args`/`get_exe` 是次要工具，`build_xray_inbound` 被 config_service 直接 import。

### service.py — 调度 + 工具

```python
def build_outbound_config(node, local_port):
    """按 bin_type 分发到 xray/sslocal/singbox 生成器。

    - config_json 统一解析一次，子模块直接收 dict
    """

def get_run_args(bin_type, config_path):
    """BIN_REGISTRY 查运行参数。"""

def get_exe(bin_type):
    """BIN_REGISTRY 查可执行文件名。"""
```

从 `__init__.py` 移入，含 config_json 解析 + bin_type 分发逻辑。

### xray.py / sslocal.py / singbox.py — 生成器（不动）

保持现状。各协议 outbound/inbound 配置生成。

## 对外契约

外部调用不变：

```python
from app.engine import build_outbound_config      # 主接口
from app.engine.xray import build_xray_inbound    # 入站生成（config_service 直调）
from app.engine import get_exe                    # 可执行名（config_service 用）
```

## 文件变更

| 操作 | 文件 | 内容 |
|------|------|------|
| 新增 | `app/engine/service.py` | build_outbound_config + get_run_args + get_exe（从 __init__ 移入） |
| 精简 | `app/engine/__init__.py` | 变为纯聚合导出 |
| 不动 | `app/engine/xray.py` / `sslocal.py` / `singbox.py` | 生成器保持现状 |

## 验证

```bash
python3 test/test_checker.py   # 全链路（依赖 engine）
python3 -c "from app.engine import build_outbound_config"  # 对外契约不变
```
