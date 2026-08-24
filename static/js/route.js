var _services = [], _inbounds = [], _outbounds = [], _nodes = [], _currentNodes = {};

function nodeNameByTag(tag) {
    if (!tag) return '—';
    if (tag === 'direct') return 'direct';
    var m = /^n(\d+)$/.exec(tag);
    if (m) {
        var n = _nodes.find(function(x) { return x.id == m[1]; });
        return n ? n.name : tag;
    }
    return tag;
}

async function fetchRouteData() {
    var results = await Promise.all([
        api('/api/services'),
        api('/api/inbounds'),
        api('/api/outbounds'),
        api('/api/nodes'),
        api('/api/services/current-nodes'),
    ]);
    _services = results[0].services || [];
    _inbounds = results[1].inbounds || [];
    _outbounds = results[2].outbounds || [];
    _nodes = results[3].nodes || [];
    _currentNodes = {};
    (results[4].services || []).forEach(function(s) { _currentNodes[s.id] = s; });
    renderServices();
}

function renderServices() {
    var list = document.getElementById('svcList');
    if (!_services.length) {
        list.innerHTML = '';
        document.getElementById('svcEmpty').style.display = 'block';
        return;
    }
    document.getElementById('svcEmpty').style.display = 'none';
    list.innerHTML = _services.map(function(s) {
        var ib = _inbounds.find(function(x) { return x.id === s.inbound_id; });
        var ob = _outbounds.find(function(x) { return x.id === s.outbound_id; });
        var cur = _currentNodes[s.id] || {};
        var running = cur.status === 'running';
        var dot = '<span class="status-dot ' + (running ? 'ok' : 'idle') + '"></span>';
        var ibDesc = ib ? (ib.protocol + ' :' + ib.port) : '#' + s.inbound_id;
        var obDesc = s.outbound_id === 0 ? 'direct' : (ob ? ob.name : '#' + s.outbound_id);
        var canSwitch = s.outbound_id !== 0 && ob && (ob.pool || []).length > 0;
        return '<div class="section" style="margin-bottom:8px;">' +
            '<div class="section-body">' +
            '<div class="row-flex" style="border:none;">' + dot +
                '<strong style="flex:1;">' + escapeHtml(s.name) + '</strong>' +
                '<span class="muted">' + escapeHtml(ibDesc) + '</span>' +
                '<button class="btn btn-sm" onclick="openSvcModal(' + s.id + ')">&#9998;</button>' +
                '<button class="btn btn-sm btn-danger" onclick="delSvc(' + s.id + ',\'' + escapeHtml(s.name) + '\')">&#10005;</button>' +
            '</div>' +
            '<div class="row-flex">' +
                '<span class="muted" style="flex:1;">inbound: ' + escapeHtml(ib ? ib.name : '?') +
                ' &middot; outbound: ' + escapeHtml(obDesc) +
                (s.auto_start ? ' &middot; auto' : '') + '</span>' +
            '</div>' +
            '<div class="row-flex">' +
                '<span style="flex:1;">current node: <strong>' + escapeHtml(nodeNameByTag(cur.current_node)) + '</strong></span>' +
                (canSwitch ? '<button class="btn btn-sm" onclick="openSwitch(' + s.id + ')">switch node</button>' : '') +
                (running
                    ? '<button class="btn btn-sm btn-danger" onclick="svcControl(' + s.id + ',\'stop\')">stop</button>'
                    : (s.outbound_id !== 0 ? '<button class="btn btn-sm btn-ok" onclick="svcControl(' + s.id + ',\'start\')">start</button>' : '')) +
            '</div>' +
            '</div></div>';
    }).join('');
}

/* ---- sing-box 进程控制 ---- */
function renderRouteStatus(d) {
    if (!d) return;
    document.getElementById('rtSbDot').className = 'status-dot ' + (d.running ? 'ok' : 'idle');
    document.getElementById('rtSbStatus').textContent = d.running ? 'running' : 'stopped';
    document.getElementById('rtSbVersion').textContent = d.version && d.version !== 'N/A' ? formatVersion(d.version) : '';
}

async function refreshSbStatus() {
    try {
        var d = await api('/api/status');
        renderRouteStatus(d);
    } catch (e) {}
}

async function sbControl(action) {
    try {
        var r = await api('/api/' + action, 'POST');
        showMessage(r.message || (r.success ? 'OK' : 'Failed'));
        refreshSbStatus();
    } catch (e) { showMessage('Failed: ' + e); }
}

async function svcControl(id, action) {
    try {
        var r = await api('/api/services/' + id + '/' + action, 'POST');
        if (!r.success) showMessage(r.message || 'Failed');
        fetchRouteData();
    } catch (e) { showMessage('Failed: ' + e); }
}

/* ---- 新建/编辑服务 ---- */
function openSvcModal(editId) {
    document.getElementById('svcEditId').value = editId || '';
    document.getElementById('svcModalTitle').textContent = editId ? 'Edit Service' : 'New Service';
    document.getElementById('svcName').value = '';
    document.getElementById('svcAutoStart').checked = false;
    document.getElementById('svcInbound').innerHTML = _inbounds.map(function(i) {
        return '<option value="' + i.id + '">' + escapeHtml(i.name) + ' (' + i.protocol + ':' + i.port + ')</option>';
    }).join('');
    document.getElementById('svcOutbound').innerHTML =
        '<option value="0">direct</option>' +
        _outbounds.map(function(o) {
            return '<option value="' + o.id + '">' + escapeHtml(o.name) + '</option>';
        }).join('');
    if (editId) {
        var s = _services.find(function(x) { return x.id === editId; });
        if (s) {
            document.getElementById('svcName').value = s.name;
            document.getElementById('svcInbound').value = s.inbound_id;
            document.getElementById('svcOutbound').value = s.outbound_id;
            document.getElementById('svcAutoStart').checked = !!s.auto_start;
        }
    }
    openModal('svcModal');
}

async function saveSvc() {
    var editId = document.getElementById('svcEditId').value;
    var payload = {
        name: document.getElementById('svcName').value.trim(),
        inbound_id: parseInt(document.getElementById('svcInbound').value),
        outbound_id: parseInt(document.getElementById('svcOutbound').value),
        auto_start: document.getElementById('svcAutoStart').checked ? 1 : 0,
    };
    if (!payload.name || !payload.inbound_id) { showMessage('Name and inbound are required'); return; }
    try {
        await api('/api/services' + (editId ? '/' + editId : ''), editId ? 'PUT' : 'POST', payload);
        closeModal('svcModal');
        fetchRouteData();
    } catch (e) { showMessage('Save failed: ' + e); }
}

function delSvc(id, name) {
    showConfirm('Delete Service', 'Delete service "' + name + '"?', async function() {
        try { await api('/api/services/' + id, 'DELETE'); fetchRouteData(); }
        catch (e) { showMessage('Delete failed: ' + e); }
    }, 'Delete', true);
}

/* ---- 切节点 ---- */
function openSwitch(svcId) {
    var s = _services.find(function(x) { return x.id === svcId; });
    if (!s) return;
    var ob = _outbounds.find(function(x) { return x.id === s.outbound_id; });
    if (!ob) return;
    var cur = (_currentNodes[svcId] || {}).current_node;
    document.getElementById('switchBody').innerHTML = (ob.pool || []).map(function(p) {
        var tag = 'n' + p.node_id;
        var active = tag === cur;
        return '<div class="row-flex' + (active ? ' row-active' : '') + '" style="cursor:pointer;" ' +
            'onclick="doSwitch(' + svcId + ',' + p.node_id + ')">' +
            '<span style="flex:2;padding-left:8px;">' + escapeHtml(p.name) + (active ? ' ✓' : '') + '</span>' +
            '<span style="flex:1;">' + escapeHtml(p.protocol) + '</span>' +
            '<span style="flex:2;" class="muted">' + escapeHtml(p.address) + ':' + p.port + '</span>' +
            '</div>';
    }).join('') || '<div class="empty-state">Pool is empty</div>';
    openModal('switchModal');
}

async function doSwitch(svcId, nodeId) {
    closeModal('switchModal');
    try {
        var r = await api('/api/services/' + svcId + '/switch', 'POST', { node_id: nodeId });
        if (!r.success) showMessage(r.message || 'Switch failed');
        fetchRouteData();
    } catch (e) { showMessage('Switch failed: ' + e); }
}

/* ---- 进入页面时查询一次 ---- */
(function init() {
    refreshSbStatus();
    fetchRouteData().catch(function() {});
})();
