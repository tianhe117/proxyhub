/* ============ 全局 JS ============ */

function escapeHtml(text) {
    if (text === null || text === undefined) return '';
    var div = document.createElement('div');
    div.textContent = String(text);
    return div.innerHTML;
}

function closeModal(id) { document.getElementById(id).classList.remove('show'); }
function openModal(id) { document.getElementById(id).classList.add('show'); }

function showMessage(msg) {
    document.getElementById('messageText').textContent = msg;
    openModal('messageModal');
}

function showConfirm(title, msg, onConfirm, confirmLabel, danger) {
    document.getElementById('confirmTitle').textContent = title || 'Confirm';
    document.getElementById('confirmMessage').textContent = msg;
    var btn = document.getElementById('confirmOkBtn');
    btn.textContent = confirmLabel || 'OK';
    btn.className = danger ? 'btn btn-danger' : 'btn btn-primary';
    btn.onclick = function() { closeModal('confirmModal'); if (onConfirm) onConfirm(); };
    openModal('confirmModal');
}

/* ---- fetch 封装: 401 统一跳登录 ---- */
async function api(path, method, body) {
    var opts = { method: method || 'GET', headers: {} };
    if (body !== undefined) {
        opts.headers['Content-Type'] = 'application/json';
        opts.body = JSON.stringify(body);
    }
    var resp = await fetch(path, opts);
    if (resp.status === 401) {
        location.href = '/login?next=' + encodeURIComponent(location.pathname);
        throw new Error('unauthorized');
    }
    return resp.json();
}

/* ---- localStorage 缓存秒开 ---- */
function cacheKey(page) { return 'ph_cache_' + page; }
function loadCache(page) {
    try {
        var raw = localStorage.getItem(cacheKey(page));
        return raw ? JSON.parse(raw) : null;
    } catch (e) { return null; }
}
function saveCache(page, data) {
    try { localStorage.setItem(cacheKey(page), JSON.stringify(data)); } catch (e) {}
}
function loadUiState(key, fallback) {
    try {
        var raw = localStorage.getItem('ph_ui_' + key);
        return raw !== null ? JSON.parse(raw) : fallback;
    } catch (e) { return fallback; }
}
function saveUiState(key, val) {
    try { localStorage.setItem('ph_ui_' + key, JSON.stringify(val)); } catch (e) {}
}

/* ---- 轮询 + 切回页面立即刷新 ---- */
var _pollers = [];
function startPolling(fn, intervalMs) {
    fn();
    var iv = setInterval(fn, intervalMs);
    _pollers.push({ fn: fn, iv: iv });
    return iv;
}
document.addEventListener('visibilitychange', function() {
    if (document.visibilityState === 'visible') {
        _pollers.forEach(function(p) { p.fn(); });
    }
});

/* ---- 状态栏: sing-box 状态 + 节点数 ---- */
async function checkSingboxStatus() {
    try {
        var data = await api('/api/status');
        var dot = document.getElementById('sbDot');
        dot.className = 'status-dot ' + (data.running ? 'ok' : 'idle');
        document.getElementById('sbLabel').textContent = data.running ? 'sing-box running' : 'sing-box stopped';
        document.getElementById('sbVersion').textContent = data.version && data.version !== 'N/A' ? data.version : '';
    } catch (e) {}
    try {
        var nodes = await api('/api/nodes');
        document.getElementById('nodeCount').textContent = (nodes.nodes || []).length + ' nodes';
    } catch (e) {}
}
startPolling(checkSingboxStatus, 10000);

/* ---- 移动端重定向 ---- */
if (window.matchMedia('(max-width: 768px)').matches) {
    location.replace('/m');
}
