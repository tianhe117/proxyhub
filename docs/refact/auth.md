# auth_service 重构方案

## 目标

密码不再明文存储，改为保存 hash。前端传 hash，后端存 hash、比对 hash。

## 现状

```python
# auth_service.py — 明文对比
def login(username, password):
    cfg_pass = get_setting('web_password') or ''
    if username == cfg_user and password == cfg_pass:  # 明文比对
        ...

# 前端 settings.html — 明文传
data['web_password'] = pw;  # 明文
```

`data/setting.json` 里 `web_password` 存的是明文。

## 方案

### 1. 密码存储：只存 hash

`web_password` 字段存 hash 值（如 SHA-256 hex），不再存明文。

### 2. 前端：传 hash

前端登录/设置时，JS 端先算 hash，再传：

```javascript
// 登录/保存前
function hashPw(pw) {
    // SHA-256，前端 crypto.subtle 或简单实现
    return sha256(pw);
}
data['web_password'] = hashPw(pw);  // 传 hash
```

### 3. 后端：比对 hash

```python
import hashlib

def _hash(pw: str) -> str:
    return hashlib.sha256(pw.encode()).hexdigest()

def login(username, password_hash):
    cfg_pass = get_setting('web_password') or ''
    if username == cfg_user and password_hash == cfg_pass:  # hash 比对
        ...
```

## 关键决策点

### 前端 hash 算法选择

| 方案 | 优点 | 缺点 |
|------|------|------|
| SHA-256（crypto.subtle） | 标准、简单 | 需 https（crypto.subtle 在非 https 下不可用） |
| 纯 JS 实现 SHA-256 | 无需 https | 引入外部库或手写 |
| 后端 hash（明文传后端） | 前端最简单 | 密码仍以明文过网络（但你的场景是本地/内网） |

### 用户名是否也 hash

用户名通常不需要 hash（非敏感），保持明文即可。只有密码敏感。

## 待确认

1. **前端 hash 怎么实现**——用 `crypto.subtle`（需 https）还是引入 sha256 JS 库，还是后端 hash？
2. **兼容已有密码**——DB 里当前存的是明文 `liruixiang`，迁移后需要先把它 hash 一次，否则登录失败。
3. **空密码语义**——空密码 = 禁用认证，这个逻辑保留不变。

## 文件变更

| 文件 | 操作 |
|------|------|
| `app/services/auth_service.py` | login 改为 hash 比对 |
| `templates/login.html` | 登录前 hash 密码 |
| `templates/settings.html` | 保存前 hash 密码 |
| `data/setting.json` | web_password 改存 hash（一次性迁移） |
| `app/routes/api_settings.py` | 可能需要在后端 hash（若前端不改） |

## 验证

1. 迁移后 `web_password` 为 hash 值
2. 前端登录传 hash，后端比对成功
3. 空密码仍禁用认证
