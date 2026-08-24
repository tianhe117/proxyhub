/* ============ 全局 ============ */
function escapeHtml(t) {
    if (t === null || t === undefined) return '';
    var d = document.createElement('div'); d.textContent = String(t); return d.innerHTML;
}
async function api(path, method, body) {
    var opts = { method: method || 'GET', headers: {} };
    if (body !== undefined) { opts.headers['Content-Type'] = 'application/json'; opts.body = JSON.stringify(body); }
    var resp = await fetch(path, opts);
    if (resp.status === 401) { location.href = '/login?next=' + encodeURIComponent('/m'); throw new Error('unauthorized'); }
    return resp.json();
}
function showMsg(t) { document.getElementById('msgText').textContent = t; openSheet('msgSheet'); }
function showConfirm(title, msg, cb, label) {
    document.getElementById('confirmTitle').firstChild.textContent = title;
    document.getElementById('confirmText').textContent = msg;
    var btn = document.getElementById('confirmOk');
    btn.textContent = label || 'OK';
    btn.onclick = function() { closeSheet('confirmSheet'); if (cb) cb(); };
    openSheet('confirmSheet');
}
function openSheet(id) { document.getElementById(id).classList.add('show'); }
function closeSheet(id) { document.getElementById(id).classList.remove('show'); }

function loadCache(k) { try { var r = localStorage.getItem('ph_cache_' + k); return r ? JSON.parse(r) : null; } catch (e) { return null; } }
function saveCache(k, v) { try { localStorage.setItem('ph_cache_' + k, JSON.stringify(v)); } catch (e) {} }
function loadUi(k, f) { try { var r = localStorage.getItem('ph_ui_' + k); return r !== null ? JSON.parse(r) : f; } catch (e) { return f; } }
function saveUi(k, v) { try { localStorage.setItem('ph_ui_' + k, JSON.stringify(v)); } catch (e) {} }

/* 轮询 + 切回页面立即刷新 */
var _pollers = [];
function startPolling(fn, ms) { fn(); var iv = setInterval(fn, ms); _pollers.push(fn); return iv; }
document.addEventListener('visibilitychange', function() {
    if (document.visibilityState === 'visible') _pollers.forEach(function(f) { f(); });
});

/* ============ 视图切换 ============ */
function switchView(name) {
    document.querySelectorAll('.view').forEach(function(v) { v.classList.remove('active'); });
    document.querySelectorAll('.tabbar .tab').forEach(function(t) { t.classList.remove('active'); });
    document.getElementById('view-' + name).classList.add('active');
    document.querySelector('.tabbar .tab[data-view="' + name + '"]').classList.add('active');
    location.hash = name;
    saveUi('m_view', name);
}

/* ============ 数据 ============ */
var _services = [], _inbounds = [], _outbounds = [], _nodes = [], _current = [], _lat = {};

function latHtml(ms, isUrl) {
    if (ms === null || ms === undefined) return '<span class="lat-pending">—</span>';
    if (ms < 0) return '<span class="lat-bad">fail</span>';
    var ok = isUrl ? 1000 : 150, warn = isUrl ? 2000 : 300;
    return '<span class="' + (ms <= ok ? 'lat-ok' : (ms <= warn ? 'lat-warn' : 'lat-bad')) + '">' + ms + 'ms</span>';
}
function nodeName(tag) {
    if (!tag) return '—';
    if (tag === 'direct') return 'direct';
    var m = /^n(\d+)$/.exec(tag);
    if (m) { var n = _nodes.find(function(x) { return x.id == m[1]; }); return n ? n.name : tag; }
    return tag;
}
function servicesOfOutbound(oid) { return _current.filter(function(s) { return s.outbound_id === oid; }); }
function currentNodeOfOutbound(oid) {
    for (var i = 0; i < _current.length; i++) {
        var s = _current[i];
        if (s.outbound_id === oid && s.current_node) {
            var m = /^n(\d+)$/.exec(s.current_node);
            if (m) return parseInt(m[1]);
        }
    }
    return null;
}

/* ---- route 视图 ---- */
async function refreshSb() {
    try {
        var d = await api('/api/status');
        ['sbDot', 'mSbDot'].forEach(function(id) {
            var el = document.getElementById(id);
            if (el) el.className = 'status-dot ' + (d.running ? 'ok' : 'idle');
        });
        document.getElementById('mSbStatus').textContent = d.running ? 'running' : 'stopped';
        document.getElementById('mSbVersion').textContent = d.version || '';
    } catch (e) {}
}
async function sbControl(action) {
    try { var r = await api('/api/' + action, 'POST'); showMsg(r.message || 'OK'); refreshSb(); }
    catch (e) { showMsg('Failed: ' + e); }
}

async function fetchRoute() {
    var r = await Promise.all([api('/api/services'), api('/api/inbounds'), api('/api/outbounds'), api('/api/nodes'), api('/api/services/current-nodes')]);
    _services = r[0].services || []; _inbounds = r[1].inbounds || []; _outbounds = r[2].outbounds || [];
    _nodes = r[3].nodes || []; _current = r[4].services || [];
    saveCache('m_route', { services: _services, inbounds: _inbounds, outbounds: _outbounds, nodes: _nodes, current: _current });
    renderServices();
}

function renderServices() {
    var box = document.getElementById('mSvcList');
    if (!_services.length) { box.innerHTML = '<div class="empty-state">No services</div>'; return; }
    box.innerHTML = _services.map(function(s) {
        var ib = _inbounds.find(function(x) { return x.id === s.inbound_id; });
        var ob = _outbounds.find(function(x) { return x.id === s.outbound_id; });
        var cur = _current.find(function(x) { return x.id === s.id; }) || {};
        var running = cur.status === 'running';
        var canSwitch = s.outbound_id !== 0 && ob && (ob.pool || []).length;
        return '<div class="row-flex">' +
            '<span class="status-dot ' + (running ? 'ok' : 'idle') + '"></span>' +
            '<div style="flex:1;">' +
                '<div><strong>' + escapeHtml(s.name) + '</strong> <span class="muted">' + escapeHtml(ib ? ib.protocol + ':' + ib.port : '') + '</span></div>' +
                '<div class="muted">→ ' + escapeHtml(nodeName(cur.current_node)) + '</div>' +
            '</div>' +
            (canSwitch ? '<button class="btn btn-sm" onclick="openSwitch(' + s.id + ')">&#8644;</button>' : '') +
            (running
                ? '<button class="btn btn-sm btn-danger" onclick="svcControl(' + s.id + ',\'stop\')">stop</button>'
                : (s.outbound_id !== 0 ? '<button class="btn btn-sm btn-ok" onclick="svcControl(' + s.id + ',\'start\')">start</button>' : '')) +
        '</div>';
    }).join('');
}

async function svcControl(id, action) {
    try { var r = await api('/api/services/' + id + '/' + action, 'POST'); if (!r.success) showMsg(r.message || 'Failed'); fetchRoute(); }
    catch (e) { showMsg('Failed: ' + e); }
}

function openSwitch(svcId) {
    var s = _services.find(function(x) { return x.id === svcId; });
    if (!s) return;
    var ob = _outbounds.find(function(x) { return x.id === s.outbound_id; });
    if (!ob) return;
    var cur = (_current.find(function(x) { return x.id === svcId; }) || {}).current_node;
    document.getElementById('switchBody').innerHTML = (ob.pool || []).map(function(p) {
        var active = 'n' + p.node_id === cur;
        return '<div class="row-flex' + (active ? ' row-active' : '') + '" style="cursor:pointer;padding:14px 16px;" onclick="doSwitch(' + svcId + ',' + p.node_id + ')">' +
            '<span style="flex:1;">' + escapeHtml(p.name) + (active ? ' ✓' : '') + '</span>' +
            '<span class="muted">' + escapeHtml(p.protocol) + '</span></div>';
    }).join('') || '<div class="empty-state">Pool is empty</div>';
    openSheet('switchSheet');
}

async function doSwitch(svcId, nodeId) {
    closeSheet('switchSheet');
    try { var r = await api('/api/services/' + svcId + '/switch', 'POST', { node_id: nodeId }); if (!r.success) showMsg(r.message || 'Failed'); fetchRoute(); }
    catch (e) { showMsg('Failed: ' + e); }
}

/* ---- inbound 视图 ---- */
function renderInbounds() {
    var box = document.getElementById('mIbList');
    if (!_inbounds.length) { box.innerHTML = '<div class="empty-state">No inbounds</div>'; return; }
    box.innerHTML = _inbounds.map(function(ib) {
        var svcCount = _services.filter(function(s) { return s.inbound_id === ib.id; }).length;
        var params = '';
        try {
            var p = JSON.parse(ib.params_json || '{}');
            params = ib.protocol === 'ss' ? (p.method || '') : (p.username ? 'user: ' + p.username : (ib.protocol === 'vmess' ? (p.uuid || '').slice(0, 8) : 'no auth'));
        } catch (e) {}
        return '<div class="section"><div class="section-body">' +
            '<div><strong>' + escapeHtml(ib.name) + '</strong> <span class="tag">' + escapeHtml(ib.protocol) + '</span></div>' +
            '<div class="muted" style="margin-top:4px;">' + escapeHtml(ib.listen_addr) + ':' + ib.port +
            ' &middot; ' + escapeHtml(params) + ' &middot; ' + svcCount + ' service(s)</div>' +
        '</div></div>';
    }).join('');
}

/* ---- outbound 视图 ---- */
async function fetchOutboundLat() {
    var ids = [];
    _outbounds.forEach(function(o) { (o.pool || []).forEach(function(p) { if (ids.indexOf(p.node_id) < 0) ids.push(p.node_id); }); });
    await Promise.all(ids.map(function(id) {
        return api('/api/nodes/' + id + '/latency').then(function(r) { if (r.latency) _lat[id] = r.latency; }).catch(function() {});
    }));
    saveCache('m_ob_lat', _lat);
}

function renderOutbounds() {
    var box = document.getElementById('mObList');
    if (!_outbounds.length) { box.innerHTML = '<div class="empty-state">No outbounds</div>'; return; }
    var collapsed = loadUi('m_ob_collapsed', {});
    box.innerHTML = _outbounds.map(function(o) {
        var pool = o.pool || [];
        var isCol = !!collapsed[String(o.id)];
        var rows = pool.map(function(p) {
            var lat = _lat[p.node_id] || {};
            var isCur = currentNodeOfOutbound(o.id) === p.node_id;
            return '<div class="row-flex' + (isCur ? ' row-active' : '') + '">' +
                '<div style="flex:1;">' +
                    '<div>' + escapeHtml(p.name) + '</div>' +
                    '<div class="muted">' + escapeHtml(p.protocol) + ' &middot; tcp ' + latHtml(lat.tcp_latency_ms, false) + ' url ' + latHtml(lat.url_latency_ms, true) + '</div>' +
                '</div>' +
                '<button class="btn btn-sm" onclick="switchOutbound(' + o.id + ',' + p.node_id + ',\'' + escapeHtml(p.name) + '\')"' + (isCur ? ' disabled' : '') + '>&#8644;</button>' +
                '<button class="btn btn-sm btn-ok" onclick="checkNode(' + p.node_id + ',this)">&#8635;</button>' +
            '</div>';
        }).join('');
        return '<div class="section">' +
            '<div class="collapse-header section-title' + (isCol ? ' collapsed' : '') + '" onclick="toggleOb(this,' + o.id + ')">' +
                '<strong>' + escapeHtml(o.name) + '</strong> &middot; ' + pool.length +
                '<span style="float:right;"><button class="btn btn-sm" onclick="event.stopPropagation();checkAllInOutbound(' + o.id + ')">check all</button></span>' +
            '</div>' +
            '<div class="collapse-body' + (isCol ? '' : ' show') + '" style="padding:0 12px;">' + rows + '</div>' +
        '</div>';
    }).join('');
}

function toggleOb(hdr, obId) {
    var body = hdr.nextElementSibling;
    var shown = body.classList.toggle('show');
    hdr.classList.toggle('collapsed', !shown);
    var c = loadUi('m_ob_collapsed', {});
    c[String(obId)] = !shown;
    saveUi('m_ob_collapsed', c);
}

function switchOutbound(obId, nodeId, nodeName) {
    var svcs = servicesOfOutbound(obId);
    if (!svcs.length) { showMsg('No service is bound to this outbound'); return; }
    showConfirm('Switch', 'Switch ' + svcs.length + ' service(s) to "' + nodeName + '"?', async function() {
        for (var i = 0; i < svcs.length; i++) {
            try { await api('/api/services/' + svcs[i].id + '/switch', 'POST', { node_id: nodeId }); } catch (e) {}
        }
        fetchRoute().then(renderOutbounds);
    }, 'Switch');
}

async function checkNode(nodeId, btn) {
    if (btn) btn.disabled = true;
    try {
        var r = await api('/api/nodes/check', 'POST', { node_id: nodeId });
        if (r.result) { _lat[nodeId] = r.result; saveCache('m_ob_lat', _lat); renderOutbounds(); }
    } catch (e) { showMsg('Check failed: ' + e); }
    if (btn) btn.disabled = false;
}

async function checkAllInOutbound(obId) {
    var o = _outbounds.find(function(x) { return x.id === obId; });
    if (!o || !(o.pool || []).length) return;
    try {
        var r = await api('/api/nodes/check', 'POST', { node_ids: (o.pool || []).map(function(p) { return p.node_id; }) });
        if (r.task_id) {
            var iv = setInterval(async function() {
                try {
                    var t = await api('/api/nodes/check/' + r.task_id);
                    Object.keys(t.results || {}).forEach(function(nid) { _lat[parseInt(nid)] = t.results[nid]; });
                    renderOutbounds();
                    if (t.status !== 'running') { clearInterval(iv); saveCache('m_ob_lat', _lat); }
                } catch (e) { clearInterval(iv); }
            }, 1000);
        }
    } catch (e) { showMsg('Check failed: ' + e); }
}

/* ---- 刷新全部 ---- */
function refreshAll() {
    document.getElementById('menuPop').classList.remove('show');
    refreshSb();
    fetchRoute().then(function() {
        renderInbounds();
        return fetchOutboundLat();
    }).then(renderOutbounds);
}

/* ---- 初始化: 缓存秒开 ---- */
(function init() {
    var cached = loadCache('m_route');
    if (cached) {
        _services = cached.services || []; _inbounds = cached.inbounds || [];
        _outbounds = cached.outbounds || []; _nodes = cached.nodes || []; _current = cached.current || [];
        renderServices(); renderInbounds();
    }
    _lat = loadCache('m_ob_lat') || {};
    if (_outbounds.length) renderOutbounds();

    var view = loadUi('m_view', null) || (location.hash || '#route').slice(1);
    if (['route', 'inbound', 'outbound'].indexOf(view) < 0) view = 'route';
    switchView(view);

    refreshSb();
    startPolling(function() {
        fetchRoute().then(function() { renderInbounds(); return fetchOutboundLat(); }).then(renderOutbounds);
    }, 10000);
})();
