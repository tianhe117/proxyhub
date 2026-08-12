# engine 优化

## 现状

```
engine/
├── __init__.py   # 分发器: build_outbound_config, get_run_args, get_exe
├── xray.py       # build_xray_outbound + build_xray_inbound + stream settings
├── sslocal.py    # generate_sslocal_config
└── singbox.py    # generate_singbox_config
```

## 问题

1. **返回值无用后缀**。`build_outbound_config` 返回 `(config_dict, 'xray_out.json')`，3 个调用方全部 `config, _ = ...` 丢弃。
2. **函数内延迟 import**。4 处 `from .x import ...` 在函数体内，每次调用都执行，没有循环引用需要避免。
3. **`__init__.py` 顶部 `import json` 未使用**。
4. **`config_json` 解析重复**。`sslocal.py`、`singbox.py`、`xray.py` 三者各自判断 `isinstance(cfg, str)` 再 `json.loads`。

## 改动

| 文件 | 操作 |
|------|------|
| `__init__.py` | 删 `import json`；4 个 `from .x import ...` 提到文件头；`get_run_args` 改为 `return [arg.format(config=config_path) for arg in registry['run_args']]`；返回值从 `(dict, str)` 改为 `dict` |
| `xray.py` | `build_xray_outbound` 直接收已解析的 config dict |
| `sslocal.py` | `generate_sslocal_config` 直接收已解析的 config dict |
| `singbox.py` | `generate_singbox_config` 直接收已解析的 config dict |

调用方适配：`app/services/config_service.py`、`app/services/service_manager.py` 中 `config, _ = build_outbound_config(...)` 改为 `config = build_outbound_config(...)`。

`build_xray_inbound`、`get_run_args`、`get_exe` 保留不动（入站逻辑独立，不参与本次优化）。
