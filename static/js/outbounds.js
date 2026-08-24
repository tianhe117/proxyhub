var _outbounds = [], _nodes = [], _currentNodes = [], _latencies = {};
var _selectedNodes = [];
var _poolAddObId = null;

/* ---- 延迟着色 ---- */
function latHtml(ms, isUrl) {
    if (ms === null || ms === undefined) return '<span class="lat-pending">—</span>';
    if (ms < 0) return '<span class="lat-bad">fail</span>';
    var ok = isUrl ? 1000 : 150, warn = isUrl ? 2000 : 300;
    var cls = ms <= ok ? 'lat-ok' : (ms <= warn ? 'lat-warn' : 'lat-bad');
    return '<span class="' + cls + '">' + ms + 'ms</span>';
}

async function fetchLatencies(nodeIds) {
    var jobs = nodeIds.map(function(id) {
        return api('/api/nodes/' + id + '/latency').then(function(d) {
            if (d.latency) _latencies[id] = d.latency;
        }).catch(function() {});
    });
    await Promise.all(jobs);
}

/* ---- 当前节点: outbound_id → node_id ---- */
function currentNodeOfOutbound(oid) {
    for (var i = 0; i < _currentNodes.length; i++) {
        var s = _currentNodes[i];
        if (s.outbound_id === oid && s.current_node) {
            var m = /^n(\d+)$/.exec(s.current_node);
            if (m) return parseInt(m[1]);
        }
    }
    return null;
}
function servicesOfOutbound(oid) {
    return _currentNodes.filter(function(s) { return s.outbound_id === oid; });
}

async function fetchOutbounds() {
    var results = await Promise.all([
        api('/api/outbounds'),
        api('/api/nodes'),
        api('/api/services/current-nodes'),
    ]);
    _outbounds = results[0].outbounds || [];
    _nodes = results[1].nodes || [];
    _currentNodes = results[2].services || [];
    saveCache('outbounds', { outbounds: _outbounds, current: _currentNodes });
    var ids = [];
    _outbounds.forEach(function(o) {
        (o.pool || []).forEach(function(p) { if (ids.indexOf(p.node_id) < 0) ids.push(p.node_id); });
    });
    await fetchLatencies(ids);
    saveCache('outbounds_lat', _latencies);
    renderOutbounds();
}

function isCollapsed(obId) {
    var saved = loadUiState('ob_collapsed', {});
    return !!saved[String(obId)];
}
function toggleCollapse(hdr, obId) {
    var body = hdr.nextElementSibling;
    var shown = body.classList.toggle('show');
    hdr.classList.toggle('collapsed', !shown);
    var saved = loadUiState('ob_collapsed', {});
    saved[String(obId)] = !shown;
    saveUiState('ob_collapsed', saved);
}

function poolRowHtml(o, p, idx) {
    var lat = _latencies[p.node_id] || {};
    var isCur = currentNodeOfOutbound(o.id) === p.node_id;
    var switchBtn = isCur
        ? '<button class="btn btn-sm btn-ok" disabled>&#10003;</button>'
        : '<button class="btn btn-sm btn-primary" onclick="switchOutbound(' + o.id + ',' + p.node_id + ',\'' + escapeHtml(p.name) + '\')" title="Switch all services on this outbound">&#8644;</button>';
    var btns = switchBtn +
        '<button class="btn btn-sm btn-ok" onclick="checkNode(' + p.node_id + ')" title="Test">&#8635;</button>' +
        '<button class="btn btn-sm btn-ghost" onclick="movePool(' + o.id + ',' + idx + ',-1)"' + (idx === 0 ? ' disabled' : '') + '>&#9650;</button>' +
        '<button class="btn btn-sm btn-ghost" onclick="movePool(' + o.id + ',' + idx + ',1)"' + (idx === o.pool.length - 1 ? ' disabled' : '') + '>&#9660;</button>' +
        '<button class="btn btn-sm btn-ghost btn-danger" onclick="removePoolNode(' + o.id + ',' + p.pool_id + ')">&#10005;</button>';
    return '<div class="row-flex' + (isCur ? ' row-active' : '') + '">' +
        '<span style="flex:2;padding-left:8px;">' + escapeHtml(p.name) +
            (idx === 0 ? ' <span class="tag" style="font-size:10px;">默认</span>' : '') + '</span>' +
        '<span style="flex:1;">' + escapeHtml(p.protocol) + '</span>' +
        '<span style="flex:2;" class="muted">' + escapeHtml(p.address) + ':' + p.port + '</span>' +
        '<span style="flex:1;">' + latHtml(lat.tcp_latency_ms, false) + '</span>' +
        '<span style="flex:1;">' + latHtml(lat.url_latency_ms, true) + '</span>' +
        '<span style="width:150px;display:flex;gap:2px;">' + btns + '</span></div>';
}

function renderOutbounds() {
    var list = document.getElementById('obList');
    if (!_outbounds.length) {
        list.innerHTML = '';
        document.getElementById('obEmpty').style.display = 'block';
        return;
    }
    document.getElementById('obEmpty').style.display = 'none';
    list.innerHTML = _outbounds.map(function(o) {
        var pool = o.pool || [];
        var collapsed = isCollapsed(o.id);
        var rows = pool.map(function(p, i) { return poolRowHtml(o, p, i); }).join('');
        return '<div class="section">' +
            '<div class="collapse-header section-title' + (collapsed ? ' collapsed' : '') + '" onclick="toggleCollapse(this,' + o.id + ')">' +
                '<strong>' + escapeHtml(o.name) + '</strong> &middot; ' + pool.length + ' nodes' +
                '<span style="float:right;display:flex;gap:4px;">' +
                    '<button class="btn btn-sm" onclick="event.stopPropagation();openObModal(' + o.id + ')">&#9998;</button>' +
                    '<button class="btn btn-sm btn-danger" onclick="event.stopPropagation();delOb(' + o.id + ',\'' + escapeHtml(o.name) + '\')">&#10005;</button>' +
                '</span>' +
            '</div>' +
            '<div class="collapse-body' + (collapsed ? '' : ' show') + '">' +
                '<div class="row-flex" style="font-size:11px;color:var(--text-secondary);border:none;padding:4px 0;">' +
                    '<span style="flex:2;padding-left:8px;">Name</span><span style="flex:1;">Protocol</span>' +
                    '<span style="flex:2;">Address</span><span style="flex:1;">TCP</span><span style="flex:1;">URL</span>' +
                    '<span style="width:150px;"></span></div>' +
                rows +
                '<div style="padding:8px;"><button class="btn btn-sm" onclick="openPoolAdd(' + o.id + ')">+ add node</button></div>' +
            '</div></div>';
    }).join('');
}

/* ---- 新建/编辑出站 ---- */
function openObModal(editId) {
    document.getElementById('obEditId').value = editId || '';
    document.getElementById('obModalTitle').textContent = editId ? 'Edit Outbound' : 'New Outbound';
    document.getElementById('obName').value = '';
    document.getElementById('obNodeFilter').value = '';
    _selectedNodes = [];
    if (editId) {
        var o = _outbounds.find(function(x) { return x.id === editId; });
        if (o) {
            document.getElementById('obName').value = o.name;
            _selectedNodes = (o.pool || []).map(function(p) { return p.node_id; });
        }
    }
    renderObNodePicker();
    renderObSelected();
    openModal('obModal');
}

function renderObNodePicker() {
    var kw = document.getElementById('obNodeFilter').value.toLowerCase();
    document.getElementById('obNodePicker').innerHTML = _nodes.filter(function(n) {
        return !kw || n.name.toLowerCase().indexOf(kw) !== -1;
    }).map(function(n) {
        var idx = _selectedNodes.indexOf(n.id);
        var mark = idx >= 0 ? ' <span class="lat-ok">✓ ' + (idx + 1) + '</span>' : '';
        return '<div style="padding:6px 10px;border-bottom:1px solid var(--border);cursor:pointer;" onclick="toggleObNode(' + n.id + ')">' +
            escapeHtml(n.name) + ' <span class="muted">' + escapeHtml(n.protocol) + '</span>' + mark + '</div>';
    }).join('') || '<div class="empty-state">No nodes</div>';
}

function renderObSelected() {
    document.getElementById('obSelected').innerHTML = _selectedNodes.map(function(id, i) {
        var n = _nodes.find(function(x) { return x.id === id; });
        return (i + 1) + '. ' + escapeHtml(n ? n.name : '#' + id);
    }).join('<br>') || 'none';
}

function toggleObNode(id) {
    var idx = _selectedNodes.indexOf(id);
    if (idx >= 0) _selectedNodes.splice(idx, 1); else _selectedNodes.push(id);
    renderObNodePicker();
    renderObSelected();
}

async function saveOb() {
    var editId = document.getElementById('obEditId').value;
    var name = document.getElementById('obName').value.trim();
    if (!name) { showMessage('Name is required'); return; }
    try {
        var obId = editId;
        if (editId) {
            await api('/api/outbounds/' + editId, 'PUT', { name: name });
        } else {
            var r = await api('/api/outbounds', 'POST', { name: name });
            obId = r.id;
        }
        await api('/api/outbounds/' + obId + '/nodes/reorder', 'POST', { node_ids: _selectedNodes });
        closeModal('obModal');
        fetchOutbounds();
        showMessage('Saved. Restart sing-box on the route page to apply.');
    } catch (e) { showMessage('Save failed: ' + e); }
}

function delOb(id, name) {
    showConfirm('Delete Outbound', 'Delete outbound "' + name + '"?', async function() {
        try { await api('/api/outbounds/' + id, 'DELETE'); fetchOutbounds(); }
        catch (e) { showMessage('Delete failed: ' + e); }
    }, 'Delete', true);
}

/* ---- 池操作 ---- */
async function movePool(obId, idx, dir) {
    var o = _outbounds.find(function(x) { return x.id === obId; });
    if (!o) return;
    var order = (o.pool || []).map(function(p) { return p.node_id; });
    var ni = idx + dir;
    if (ni < 0 || ni >= order.length) return;
    order.splice(idx, 1);
    order.splice(ni, 0, (o.pool || [])[idx].node_id);
    try { await api('/api/outbounds/' + obId + '/nodes/reorder', 'POST', { node_ids: order }); fetchOutbounds(); }
    catch (e) { showMessage('Reorder failed: ' + e); }
}

async function removePoolNode(obId, poolId) {
    try { await api('/api/outbounds/' + obId + '/nodes/' + poolId, 'DELETE'); fetchOutbounds(); }
    catch (e) { showMessage('Remove failed: ' + e); }
}

function openPoolAdd(obId) {
    _poolAddObId = obId;
    document.getElementById('poolAddFilter').value = '';
    renderPoolAddPicker();
    openModal('poolAddModal');
}

function renderPoolAddPicker() {
    var o = _outbounds.find(function(x) { return x.id === _poolAddObId; });
    if (!o) return;
    var inPool = (o.pool || []).map(function(p) { return p.node_id; });
    var kw = document.getElementById('poolAddFilter').value.toLowerCase();
    document.getElementById('poolAddPicker').innerHTML = _nodes.filter(function(n) {
        return !kw || n.name.toLowerCase().indexOf(kw) !== -1;
    }).map(function(n) {
        var added = inPool.indexOf(n.id) >= 0;
        var style = added ? 'opacity:0.4;' : 'cursor:pointer;';
        var onclick = added ? '' : ' onclick="addPoolNode(' + n.id + ')"';
        return '<div class="row-flex" style="' + style + '"' + onclick + '>' +
            '<span style="flex:2;padding-left:8px;">' + escapeHtml(n.name) + '</span>' +
            '<span style="flex:1;">' + escapeHtml(n.protocol) + '</span>' +
            (added ? '<span class="muted">in pool</span>' : '') + '</div>';
    }).join('') || '<div class="empty-state">No nodes</div>';
}

async function addPoolNode(nodeId) {
    try {
        await api('/api/outbounds/' + _poolAddObId + '/nodes', 'POST', { node_id: nodeId });
        closeModal('poolAddModal');
        fetchOutbounds();
    } catch (e) { showMessage('Add failed: ' + e); }
}

/* ---- 切节点: 对该出站的所有绑定服务 ---- */
function switchOutbound(obId, nodeId, nodeName) {
    var svcs = servicesOfOutbound(obId);
    if (!svcs.length) { showMessage('No service is bound to this outbound'); return; }
    showConfirm('Switch Node', 'Switch ' + svcs.length + ' service(s) on this outbound to "' + nodeName + '"?', async function() {
        var fails = 0;
        for (var i = 0; i < svcs.length; i++) {
            try {
                var r = await api('/api/services/' + svcs[i].id + '/switch', 'POST', { node_id: nodeId });
                if (!r.success) fails++;
            } catch (e) { fails++; }
        }
        if (fails) showMessage(fails + ' service(s) failed to switch');
        fetchOutbounds();
    }, 'Switch');
}

/* ---- 单节点测速 ---- */
async function checkNode(nodeId) {
    try {
        var r = await api('/api/nodes/check', 'POST', { node_id: nodeId });
        if (r.result) {
            _latencies[nodeId] = r.result;
            renderOutbounds();
        }
    } catch (e) { showMessage('Check failed: ' + e); }
}

/* ---- 缓存秒开 + 进入页面时查询一次 ---- */
(function init() {
    var cached = loadCache('outbounds');
    if (cached) {
        _outbounds = cached.outbounds || [];
        _currentNodes = cached.current || [];
    }
    _latencies = loadCache('outbounds_lat') || {};
    if (_outbounds.length) renderOutbounds();
    fetchOutbounds().catch(function() {});
})();
