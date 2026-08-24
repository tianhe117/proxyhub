/* ============ 全局 JS ============ */

function escapeHtml(text) {
    if (text === null || text === undefined) return '';
    var div = document.createElement('div');
    div.textContent = String(text);
    return div.innerHTML;
}

function formatVersion(value) {
    var match = String(value || '').match(/\b\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?\b/);
    return match ? match[0] : (value || 'N/A');
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

/* ---- 状态栏: sing-box 状态 + 节点数 ---- */
function renderGlobalStatus(data) {
    if (!data) return;
    var dot = document.getElementById('sbDot');
    dot.className = 'status-dot ' + (data.running ? 'ok' : 'idle');
    document.getElementById('sbLabel').textContent = data.running ? 'sing-box running' : 'sing-box stopped';
    document.getElementById('sbVersion').textContent = data.version && data.version !== 'N/A' ? formatVersion(data.version) : '';
    if (data.node_count !== undefined) {
        document.getElementById('nodeCount').textContent = data.node_count + ' nodes';
    }
}

async function checkSingboxStatus() {
    try {
        var results = await Promise.all([api('/api/status'), api('/api/nodes')]);
        var data = results[0];
        data.node_count = (results[1].nodes || []).length;
        renderGlobalStatus(data);
    } catch (e) {}
}

/* ---- 移动端重定向 ---- */
if (window.matchMedia('(max-width: 768px)').matches) {
    location.replace('/m');
} else {
    checkSingboxStatus();
}
