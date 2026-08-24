var _inbounds = [];

var SS_METHODS = ['aes-256-gcm', 'aes-128-gcm', 'chacha20-ietf-poly1305', '2022-blake3-aes-256-gcm'];

function paramSummary(ib) {
    try {
        var p = typeof ib.params_json === 'string' ? JSON.parse(ib.params_json) : (ib.params_json || {});
        if (ib.protocol === 'http' || ib.protocol === 'socks') {
            return p.username ? 'user: ' + p.username : 'no auth';
        }
        if (ib.protocol === 'ss') return p.method || '';
        if (ib.protocol === 'vmess') {
            var s = (p.uuid || '').slice(0, 8);
            if (p.network && p.network !== 'tcp') s += ' ' + p.network;
            return s;
        }
    } catch (e) {}
    return '';
}

function renderInbounds() {
    var list = document.getElementById('ibList');
    if (!_inbounds.length) {
        list.innerHTML = '';
        document.getElementById('ibEmpty').style.display = 'block';
        return;
    }
    document.getElementById('ibEmpty').style.display = 'none';
    var html = '<div class="row-flex" style="font-size:11px;color:var(--text-secondary);border:none;">' +
        '<span style="flex:2;">Name</span><span style="flex:1;">Protocol</span>' +
        '<span style="flex:2;">Listen</span><span style="flex:2;">Params</span><span style="width:70px;"></span></div>';
    html += _inbounds.map(function(ib) {
        return '<div class="row-flex">' +
            '<span style="flex:2;">' + escapeHtml(ib.name) + '</span>' +
            '<span style="flex:1;"><span class="tag">' + escapeHtml(ib.protocol) + '</span></span>' +
            '<span style="flex:2;">' + escapeHtml(ib.listen_addr) + ':' + ib.port + '</span>' +
            '<span style="flex:2;" class="muted">' + escapeHtml(paramSummary(ib)) + '</span>' +
            '<span style="width:70px;display:flex;gap:2px;">' +
                '<button class="btn btn-sm" onclick="openIbModal(' + ib.id + ')">&#9998;</button>' +
                '<button class="btn btn-sm btn-danger" onclick="delIb(' + ib.id + ',\'' + escapeHtml(ib.name) + '\')">&#10005;</button>' +
            '</span></div>';
    }).join('');
    list.innerHTML = html;
}

async function fetchInbounds() {
    var d = await api('/api/inbounds');
    _inbounds = d.inbounds || [];
    saveCache('inbounds', { inbounds: _inbounds });
    renderInbounds();
}

/* ---- 模态框: 协议自适应 ---- */
function onIbProtoChange() {
    var proto = document.getElementById('ibProtocol').value;
    var box = document.getElementById('ibParams');
    if (proto === 'http' || proto === 'socks') {
        box.innerHTML =
            '<div class="field-row">' +
            '<div class="field"><label>Username (optional)</label><input class="input" id="ibUsername"></div>' +
            '<div class="field"><label>Password (optional)</label><input class="input" id="ibPassword"></div>' +
            '</div>';
    } else if (proto === 'ss') {
        box.innerHTML =
            '<div class="field"><label>Method</label><select class="input" id="ibMethod">' +
            SS_METHODS.map(function(m) { return '<option value="' + m + '">' + m + '</option>'; }).join('') +
            '</select></div>' +
            '<div class="field"><label>Password</label><input class="input" id="ibPassword"></div>';
    } else if (proto === 'vmess') {
        box.innerHTML =
            '<div class="field"><label>UUID</label><input class="input" id="ibUuid"></div>' +
            '<div class="field-row">' +
            '<div class="field"><label>AlterId</label><input class="input" id="ibAlterId" type="number" value="0"></div>' +
            '<div class="field"><label>Transport</label><select class="input" id="ibNetwork" onchange="onIbNetChange()">' +
                '<option value="tcp">tcp</option><option value="ws">ws</option>' +
                '<option value="h2">h2</option><option value="grpc">grpc</option>' +
            '</select></div>' +
            '</div><div id="ibNetParams"></div>';
        onIbNetChange();
    }
}

function onIbNetChange() {
    var net = document.getElementById('ibNetwork').value;
    var box = document.getElementById('ibNetParams');
    if (net === 'ws') {
        box.innerHTML = '<div class="field-row">' +
            '<div class="field"><label>WS Path</label><input class="input" id="ibWsPath" value="/"></div>' +
            '<div class="field"><label>WS Host</label><input class="input" id="ibWsHost"></div></div>';
    } else if (net === 'h2') {
        box.innerHTML = '<div class="field-row">' +
            '<div class="field"><label>H2 Host</label><input class="input" id="ibH2Host"></div>' +
            '<div class="field"><label>H2 Path</label><input class="input" id="ibH2Path" value="/"></div></div>';
    } else if (net === 'grpc') {
        box.innerHTML = '<div class="field"><label>gRPC Service Name</label><input class="input" id="ibGrpcName"></div>';
    } else {
        box.innerHTML = '';
    }
}

function openIbModal(editId) {
    document.getElementById('ibEditId').value = editId || '';
    document.getElementById('ibModalTitle').textContent = editId ? 'Edit Inbound' : 'New Inbound';
    document.getElementById('ibName').value = '';
    document.getElementById('ibProtocol').value = 'http';
    document.getElementById('ibPort').value = '';
    document.getElementById('ibListen').value = '0.0.0.0';
    onIbProtoChange();
    if (editId) {
        var ib = _inbounds.find(function(x) { return x.id === editId; });
        if (ib) {
            document.getElementById('ibName').value = ib.name;
            document.getElementById('ibProtocol').value = ib.protocol;
            document.getElementById('ibPort').value = ib.port;
            document.getElementById('ibListen').value = ib.listen_addr;
            onIbProtoChange();
            var p = {};
            try { p = JSON.parse(ib.params_json || '{}'); } catch (e) {}
            fillParams(ib.protocol, p);
        }
    }
    openModal('ibModal');
}

function fillParams(proto, p) {
    function set(id, v) { var el = document.getElementById(id); if (el) el.value = v; }
    if (proto === 'http' || proto === 'socks') {
        set('ibUsername', p.username || ''); set('ibPassword', p.password || '');
    } else if (proto === 'ss') {
        set('ibMethod', p.method || SS_METHODS[0]); set('ibPassword', p.password || '');
    } else if (proto === 'vmess') {
        set('ibUuid', p.uuid || ''); set('ibAlterId', p.alterId || 0);
        set('ibNetwork', p.network || 'tcp'); onIbNetChange();
        set('ibWsPath', p.ws_path || '/'); set('ibWsHost', p.ws_host || '');
        set('ibH2Host', p.h2_host || ''); set('ibH2Path', p.h2_path || '/');
        set('ibGrpcName', p.grpc_service_name || '');
    }
}

function collectParams(proto) {
    function val(id) { var el = document.getElementById(id); return el ? el.value.trim() : ''; }
    var p = {};
    if (proto === 'http' || proto === 'socks') {
        if (val('ibUsername')) { p.username = val('ibUsername'); p.password = val('ibPassword'); }
    } else if (proto === 'ss') {
        p.method = val('ibMethod'); p.password = val('ibPassword');
    } else if (proto === 'vmess') {
        p.uuid = val('ibUuid');
        p.alterId = parseInt(val('ibAlterId')) || 0;
        var net = val('ibNetwork');
        if (net !== 'tcp') {
            p.network = net;
            if (net === 'ws') { p.ws_path = val('ibWsPath'); if (val('ibWsHost')) p.ws_host = val('ibWsHost'); }
            if (net === 'h2') { if (val('ibH2Host')) p.h2_host = val('ibH2Host'); p.h2_path = val('ibH2Path'); }
            if (net === 'grpc') { p.grpc_service_name = val('ibGrpcName'); }
        }
    }
    return p;
}

async function saveIb() {
    var editId = document.getElementById('ibEditId').value;
    var proto = document.getElementById('ibProtocol').value;
    var payload = {
        name: document.getElementById('ibName').value.trim(),
        protocol: proto,
        listen_addr: document.getElementById('ibListen').value.trim() || '0.0.0.0',
        port: parseInt(document.getElementById('ibPort').value),
        params_json: JSON.stringify(collectParams(proto)),
    };
    if (!payload.name || !payload.port) { showMessage('Name and port are required'); return; }
    try {
        await api('/api/inbounds' + (editId ? '/' + editId : ''), editId ? 'PUT' : 'POST', payload);
        closeModal('ibModal');
        fetchInbounds();
        showMessage('Saved. Restart sing-box on the route page to apply.');
    } catch (e) { showMessage('Save failed: ' + e); }
}

function delIb(id, name) {
    showConfirm('Delete Inbound', 'Delete inbound "' + name + '"?', async function() {
        try { await api('/api/inbounds/' + id, 'DELETE'); fetchInbounds(); }
        catch (e) { showMessage('Delete failed: ' + e); }
    }, 'Delete', true);
}

/* ---- 缓存秒开 ---- */
(function init() {
    var cached = loadCache('inbounds');
    if (cached && cached.inbounds) { _inbounds = cached.inbounds; renderInbounds(); }
    startPolling(fetchInbounds, 10000);
})();
