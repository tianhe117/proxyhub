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

/* ---- 状态栏: sing-box 状态 + 节点数 ---- */
function renderGlobalStatus(data) {
    if (!data) return;
    var dot = document.getElementById('sbDot');
    dot.className = 'status-dot ' + (data.running ? 'ok' : 'idle');
    document.getElementById('sbLabel').textContent = data.running ? 'sing-box running' : 'sing-box stopped';
    document.getElementById('sbVersion').textContent = data.version && data.version !== 'N/A' ? data.version : '';
    if (data.node_count !== undefined) {
        document.getElementById('nodeCount').textContent = data.node_count + ' nodes';
    }
}

async function checkSingboxStatus() {
    try {
        var results = await Promise.all([api('/api/status'), api('/api/nodes')]);
        var data = results[0];
        data.node_count = (results[1].nodes || []).length;
        saveCache('global_status', data);
        renderGlobalStatus(data);
    } catch (e) {}
}

/* ---- 移动端重定向 ---- */
if (window.matchMedia('(max-width: 768px)').matches) {
    location.replace('/m');
} else {
    renderGlobalStatus(loadCache('global_status'));
    checkSingboxStatus();
}
