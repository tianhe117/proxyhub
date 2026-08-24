var _groups = [], _latencies = {};

/* ---- 延迟着色 ---- */
function latHtml(ms, isUrl) {
    if (ms === null || ms === undefined) return '<span class="lat-pending">—</span>';
    if (ms < 0) return '<span class="lat-bad">fail</span>';
    var ok = isUrl ? 1000 : 150, warn = isUrl ? 2000 : 300;
    var cls = ms <= ok ? 'lat-ok' : (ms <= warn ? 'lat-warn' : 'lat-bad');
    return '<span class="' + cls + '">' + ms + 'ms</span>';
}

function isGroupCollapsed(key) {
    var saved = loadUiState('nodes_collapsed', {});
    return !!saved[key];
}
function toggleGroup(hdr, key) {
    var body = hdr.nextElementSibling;
    var shown = body.classList.toggle('show');
    hdr.classList.toggle('collapsed', !shown);
    var saved = loadUiState('nodes_collapsed', {});
    saved[key] = !shown;
    saveUiState('nodes_collapsed', saved);
}

function nodeRowHtml(n) {
    var lat = _latencies[n.id] || {};
    return '<div class="row-flex">' +
        '<span style="flex:2;padding-left:8px;">' + escapeHtml(n.name) + '</span>' +
        '<span style="flex:1;"><span class="tag">' + escapeHtml(n.protocol) + '</span></span>' +
        '<span style="flex:2;" class="muted">' + escapeHtml(n.address) + ':' + n.port + '</span>' +
        '<span style="flex:1;" id="tcp-' + n.id + '">' + latHtml(lat.tcp_latency_ms, false) + '</span>' +
        '<span style="flex:1;" id="url-' + n.id + '">' + latHtml(lat.url_latency_ms, true) + '</span>' +
        '<span style="width:100px;display:flex;gap:2px;">' +
            '<button class="btn btn-sm btn-ok" onclick="checkNode(' + n.id + ')" title="Test">&#8635;</button>' +
            '<button class="btn btn-sm" onclick="openNodeModal(' + n.id + ')">&#9998;</button>' +
            '<button class="btn btn-sm btn-danger" onclick="delNode(' + n.id + ',\'' + escapeHtml(n.name) + '\')">&#10005;</button>' +
        '</span></div>';
}

function renderGroups() {
    var box = document.getElementById('nodeGroups');
    var hasNodes = _groups.some(function(g) { return g.nodes.length; });
    document.getElementById('nodesEmpty').style.display = hasNodes ? 'none' : 'block';
    box.innerHTML = _groups.map(function(g) {
        if (!g.nodes.length) return '';
        var key = g.sub ? 'sub_' + g.sub.id : 'custom';
        var title = g.sub ? g.sub.name : 'Custom Nodes';
        var collapsed = isGroupCollapsed(key);
        return '<div class="section">' +
            '<div class="collapse-header section-title' + (collapsed ? ' collapsed' : '') + '" onclick="toggleGroup(this,\'' + key + '\')">' +
                '<strong>' + escapeHtml(title) + '</strong> &middot; ' + g.nodes.length + ' nodes' +
                '<span style="float:right;"><button class="btn btn-sm" onclick="event.stopPropagation();checkGroup(' + (g.sub ? g.sub.id : 0) + ')">check all</button></span>' +
            '</div>' +
            '<div class="collapse-body' + (collapsed ? '' : ' show') + '">' +
                '<div class="row-flex" style="font-size:11px;color:var(--text-secondary);border:none;padding:4px 0;">' +
                    '<span style="flex:2;padding-left:8px;">Name</span><span style="flex:1;">Protocol</span>' +
                    '<span style="flex:2;">Address</span><span style="flex:1;">TCP</span><span style="flex:1;">URL</span>' +
                    '<span style="width:100px;"></span></div>' +
                g.nodes.map(nodeRowHtml).join('') +
            '</div></div>';
    }).join('');
}

async function fetchNodes() {
    var d = await api('/api/nodes/grouped');
    _groups = d.groups || [];
    var ids = [];
    _groups.forEach(function(g) { g.nodes.forEach(function(n) { ids.push(n.id); }); });
    await Promise.all(ids.map(function(id) {
        return api('/api/nodes/' + id + '/latency').then(function(r) {
            if (r.latency) _latencies[id] = r.latency;
        }).catch(function() {});
    }));
    saveCache('nodes', { groups: _groups });
    saveCache('nodes_lat', _latencies);
    renderGroups();
}

function updateRowLatency(nodeId, result) {
    _latencies[nodeId] = result;
    saveCache('nodes_lat', _latencies);
    var tcp = document.getElementById('tcp-' + nodeId);
    var url = document.getElementById('url-' + nodeId);
    if (tcp) tcp.innerHTML = latHtml(result.tcp_latency_ms, false);
    if (url) url.innerHTML = latHtml(result.url_latency_ms, true);
}

/* ---- 检测 ---- */
async function checkNode(nodeId) {
    updateRowLatency(nodeId, { tcp_latency_ms: null, url_latency_ms: null });
    try {
        var r = await api('/api/nodes/check', 'POST', { node_id: nodeId });
        if (r.result) updateRowLatency(nodeId, r.result);
    } catch (e) { showMessage('Check failed: ' + e); }
}

async function checkGroup(subId) {
    try {
        var r = await api('/api/nodes/check', 'POST', { sub_id: subId });
        if (r.task_id) showMessage('Check started. Reopen this page later to load the results.');
        else if (r.result) updateRowLatency(r.node_id, r.result);
    } catch (e) { showMessage('Check failed: ' + e); }
}

async function checkAll() {
    try {
        var r = await api('/api/nodes/check', 'POST', {});
        if (r.task_id) showMessage('Check started. Reopen this page later to load the results.');
    } catch (e) { showMessage('Check failed: ' + e); }
}

/* ---- URL 导入 ---- */
function b64decode(s) {
    s = s.replace(/-/g, '+').replace(/_/g, '/');
    while (s.length % 4) s += '=';
    try { return decodeURIComponent(escape(atob(s))); } catch (e) { return atob(s); }
}

function parseQuery(qs) {
    var out = {};
    (qs || '').split('&').forEach(function(kv) {
        if (!kv) return;
        var i = kv.indexOf('=');
        var k = i >= 0 ? kv.slice(0, i) : kv;
        var v = i >= 0 ? kv.slice(i + 1) : '';
        out[decodeURIComponent(k)] = decodeURIComponent(v);
    });
    return out;
}

function importUrl() {
    var url = document.getElementById('ndImportUrl').value.trim();
    if (!url) return;
    var parsed = null;
    try {
        if (url.indexOf('vmess://') === 0) parsed = parseVmess(url);
        else if (url.indexOf('ss://') === 0) parsed = parseSs(url);
        else parsed = parseGeneric(url);
    } catch (e) { parsed = null; }
    if (!parsed) { showMessage('Parse failed — unsupported or invalid URL'); return; }
    fillNodeForm(parsed);
}

function parseVmess(url) {
    var data = JSON.parse(b64decode(url.slice(8)));
    var cfg = {
        uuid: data.id || '',
        alterId: parseInt(data.aid) || 0,
        security: (data.type && data.type !== 'none') ? data.type : 'auto',
        network: data.net || 'tcp',
        tls: data.tls === 'tls' || data.tls === '1' || data.tls === true,
        allowInsecure: data.tls === 'allowInsecure',
    };
    if (cfg.network === 'ws') { if (data.host) cfg.ws_host = data.host; if (data.path) cfg.ws_path = data.path; }
    if (cfg.network === 'h2') { if (data.host) cfg.h2_host = data.host; if (data.path) cfg.h2_path = data.path; }
    if (cfg.network === 'grpc') { if (data.path) cfg.grpc_service_name = data.path; }
    return { name: data.ps || 'Unnamed', protocol: 'vmess', address: data.add || '', port: parseInt(data.port) || 0, config: cfg };
}

function parseSs(url) {
    var body = url.slice(5);
    var name = 'Unnamed';
    var h = body.indexOf('#');
    if (h >= 0) { name = decodeURIComponent(body.slice(h + 1)) || name; body = body.slice(0, h); }
    var params = {};
    var q = body.indexOf('?');
    if (q >= 0) { params = parseQuery(body.slice(q + 1)); body = body.slice(0, q); }
    var method = '', password = '', address = '', port = 0;
    if (body.indexOf('@') >= 0) {
        var at = body.lastIndexOf('@');
        var userinfo = b64decode(body.slice(0, at));
        var hp = body.slice(at + 1).replace(/\/$/, '');
        var ci = userinfo.indexOf(':');
        method = userinfo.slice(0, ci); password = userinfo.slice(ci + 1);
        var pi = hp.lastIndexOf(':');
        address = hp.slice(0, pi); port = parseInt(hp.slice(pi + 1)) || 0;
    } else {
        var decoded = b64decode(body);
        var at2 = decoded.lastIndexOf('@');
        var ci2 = decoded.indexOf(':');
        method = decoded.slice(0, ci2);
        var rest = decoded.slice(ci2 + 1);
        var at3 = rest.lastIndexOf('@');
        password = rest.slice(0, at3);
        var hp2 = rest.slice(at3 + 1);
        var pi2 = hp2.lastIndexOf(':');
        address = hp2.slice(0, pi2); port = parseInt(hp2.slice(pi2 + 1)) || 0;
    }
    var cfg = { method: method, password: password };
    if (params.plugin && params.plugin.indexOf('obfs') >= 0) {
        cfg.plugin = 'obfs-local';
        var po = params.plugin.split(';').slice(1).join(';');
        if (po) cfg.plugin_opts = po;
    }
    return { name: name, protocol: 'ss', address: address, port: port, config: cfg };
}

function parseGeneric(url) {
    var m = /^(\w+):\/\/(.*)$/.exec(url);
    if (!m) return null;
    var scheme = m[1].toLowerCase();
    var protoMap = { vless: 'vless', trojan: 'trojan', hy2: 'hysteria2', hysteria2: 'hysteria2', tuic: 'tuic' };
    var protocol = protoMap[scheme];
    if (!protocol) return null;
    var rest = m[2];
    var name = 'Unnamed';
    var h = rest.indexOf('#');
    if (h >= 0) { name = decodeURIComponent(rest.slice(h + 1)) || name; rest = rest.slice(0, h); }
    var params = {};
    var q = rest.indexOf('?');
    if (q >= 0) { params = parseQuery(rest.slice(q + 1)); rest = rest.slice(0, q); }
    var at = rest.lastIndexOf('@');
    if (at < 0) return null;
    var userinfo = rest.slice(0, at);
    var hp = rest.slice(at + 1);
    var pi = hp.lastIndexOf(':');
    var address = hp.slice(0, pi), port = parseInt(hp.slice(pi + 1)) || 0;
    var ui = userinfo.split(':');
    var cfg;
    if (protocol === 'vless') {
        cfg = { uuid: decodeURIComponent(ui[0]), flow: params.flow || '', encryption: params.encryption || 'none',
                network: params.type || 'tcp', tls: params.security === 'tls' || params.security === 'reality',
                sni: params.sni || params.servername || '', allowInsecure: params.allowInsecure === '1' || params.allowInsecure === 'true',
                fingerprint: params.fp || '' };
        if (params.alpn) cfg.alpn = params.alpn;
        if (cfg.network === 'ws') { if (params.host) cfg.ws_host = params.host; if (params.path) cfg.ws_path = params.path; }
        if (cfg.network === 'grpc') { if (params.serviceName) cfg.grpc_service_name = params.serviceName; }
    } else if (protocol === 'trojan') {
        cfg = { password: decodeURIComponent(ui[0]), network: params.type || 'tcp',
                sni: params.sni || params.servername || '', allowInsecure: params.allowInsecure === '1' || params.allowInsecure === 'true',
                fingerprint: params.fp || '', tls: true };
        if (params.alpn) cfg.alpn = params.alpn;
        if (cfg.network === 'ws') { if (params.host) cfg.ws_host = params.host; if (params.path) cfg.ws_path = params.path; }
    } else if (protocol === 'hysteria2') {
        cfg = { password: decodeURIComponent(ui[0]), sni: params.sni || params.peer || '',
                allowInsecure: params.insecure === '1' || params.insecure === 'true' };
        if (params.alpn) cfg.alpn = params.alpn;
        if (params.up) cfg.up_mbps = parseInt(params.up) || 0;
        if (params.down) cfg.down_mbps = parseInt(params.down) || 0;
        if (params.obfs) { cfg.obfs = params.obfs; if (params['obfs-password']) cfg.obfs_password = params['obfs-password']; }
    } else if (protocol === 'tuic') {
        cfg = { uuid: decodeURIComponent(ui[0]), password: decodeURIComponent(ui.slice(1).join(':') || ''),
                sni: params.sni || params.peer || '', allowInsecure: params.insecure === '1' || params.insecure === 'true',
                congestion_control: params.congestion_control || 'cubic', udp_relay_mode: params.udp_relay_mode || 'native' };
        if (params.alpn) cfg.alpn = params.alpn;
    }
    return { name: name, protocol: protocol, address: address, port: port, config: cfg };
}

/* ---- 协议字段渲染 ---- */
function fieldInput(id, label, val, type) {
    return '<div class="field"><label>' + label + '</label><input class="input" id="' + id + '" type="' + (type || 'text') + '" value="' + escapeHtml(val === undefined ? '' : val) + '"></div>';
}
function fieldCheck(id, label, checked) {
    return '<div class="field"><label style="cursor:pointer;"><input type="checkbox" id="' + id + '"' + (checked ? ' checked' : '') + '> ' + label + '</label></div>';
}

function transportFields(prefix, cfg) {
    cfg = cfg || {};
    var net = cfg.network || 'tcp';
    var html = '<div class="field"><label>Network</label><select class="input" id="' + prefix + 'Network" onchange="onNdNetChange(\'' + prefix + '\')">' +
        ['tcp', 'ws', 'h2', 'grpc'].map(function(n) { return '<option value="' + n + '"' + (net === n ? ' selected' : '') + '>' + n + '</option>'; }).join('') +
        '</select></div><div id="' + prefix + 'NetFields"></div>';
    return html;
}
function renderNetFields(prefix, cfg) {
    cfg = cfg || {};
    var netEl = document.getElementById(prefix + 'Network');
    if (!netEl) return;
    var net = netEl.value;
    var box = document.getElementById(prefix + 'NetFields');
    if (net === 'ws') box.innerHTML = '<div class="field-row">' + fieldInput(prefix + 'WsPath', 'WS Path', cfg.ws_path || '/') + fieldInput(prefix + 'WsHost', 'WS Host', cfg.ws_host) + '</div>';
    else if (net === 'h2') box.innerHTML = '<div class="field-row">' + fieldInput(prefix + 'H2Host', 'H2 Host', cfg.h2_host) + fieldInput(prefix + 'H2Path', 'H2 Path', cfg.h2_path || '/') + '</div>';
    else if (net === 'grpc') box.innerHTML = fieldInput(prefix + 'GrpcName', 'gRPC Service Name', cfg.grpc_service_name);
    else box.innerHTML = '';
}
function onNdNetChange(prefix) { renderNetFields(prefix); }

function tlsFields(cfg) {
    cfg = cfg || {};
    return fieldCheck('ndTls', 'TLS enabled', !!cfg.tls) +
        '<div class="field-row">' + fieldInput('ndSni', 'SNI', cfg.sni) + fieldInput('ndAlpn', 'ALPN (comma)', cfg.alpn) + '</div>' +
        '<div class="field-row">' + fieldCheck('ndAllowInsecure', 'allowInsecure', !!cfg.allowInsecure) + fieldInput('ndFingerprint', 'Fingerprint', cfg.fingerprint) + '</div>';
}

function onNdProtoChange(cfg) {
    cfg = cfg || {};
    var proto = document.getElementById('ndProtocol').value;
    var box = document.getElementById('ndProtoFields');
    var html = '';
    if (proto === 'vmess') {
        html = fieldInput('ndUuid', 'UUID', cfg.uuid) +
            '<div class="field-row">' + fieldInput('ndAlterId', 'AlterId', cfg.alterId || 0, 'number') +
            '<div class="field"><label>Security</label><select class="input" id="ndSecurity">' +
            ['auto', 'aes-128-gcm', 'chacha20-poly1305', 'none'].map(function(s) { return '<option' + (cfg.security === s ? ' selected' : '') + '>' + s + '</option>'; }).join('') +
            '</select></div></div>' +
            transportFields('nd', cfg) + tlsFields(cfg);
    } else if (proto === 'vless') {
        html = fieldInput('ndUuid', 'UUID', cfg.uuid) +
            '<div class="field-row">' + fieldInput('ndFlow', 'Flow', cfg.flow) + fieldInput('ndEncryption', 'Encryption', cfg.encryption || 'none') + '</div>' +
            transportFields('nd', cfg) + tlsFields(cfg);
    } else if (proto === 'trojan') {
        html = fieldInput('ndPassword', 'Password', cfg.password) +
            transportFields('nd', cfg) + tlsFields(cfg);
    } else if (proto === 'ss') {
        html = '<div class="field"><label>Method</label><select class="input" id="ndMethod">' +
            ['aes-256-gcm', 'aes-128-gcm', 'chacha20-ietf-poly1305', '2022-blake3-aes-256-gcm'].map(function(m) { return '<option' + (cfg.method === m ? ' selected' : '') + '>' + m + '</option>'; }).join('') +
            '</select></div>' + fieldInput('ndPassword', 'Password', cfg.password) +
            '<div class="field-row">' + fieldInput('ndPlugin', 'Plugin (obfs-local only)', cfg.plugin) + fieldInput('ndPluginOpts', 'Plugin Opts', cfg.plugin_opts) + '</div>';
    } else if (proto === 'hysteria2') {
        html = fieldInput('ndPassword', 'Password', cfg.password) +
            '<div class="field-row">' + fieldInput('ndSni', 'SNI', cfg.sni) + fieldInput('ndAlpn', 'ALPN', cfg.alpn) + '</div>' +
            fieldCheck('ndAllowInsecure', 'allowInsecure', !!cfg.allowInsecure) +
            '<div class="field-row">' + fieldInput('ndObfs', 'Obfs', cfg.obfs) + fieldInput('ndObfsPassword', 'Obfs Password', cfg.obfs_password) + '</div>' +
            '<div class="field-row">' + fieldInput('ndUpMbps', 'Up Mbps', cfg.up_mbps, 'number') + fieldInput('ndDownMbps', 'Down Mbps', cfg.down_mbps, 'number') + '</div>';
    } else if (proto === 'tuic') {
        html = '<div class="field-row">' + fieldInput('ndUuid', 'UUID', cfg.uuid) + fieldInput('ndPassword', 'Password', cfg.password) + '</div>' +
            '<div class="field-row">' + fieldInput('ndSni', 'SNI', cfg.sni) + fieldInput('ndAlpn', 'ALPN', cfg.alpn) + '</div>' +
            fieldCheck('ndAllowInsecure', 'allowInsecure', !!cfg.allowInsecure) +
            '<div class="field-row">' + fieldInput('ndCongestion', 'Congestion Control', cfg.congestion_control || 'cubic') + fieldInput('ndUdpRelay', 'UDP Relay Mode', cfg.udp_relay_mode || 'native') + '</div>';
    }
    box.innerHTML = html;
    renderNetFields('nd', cfg);
}

function val(id) { var el = document.getElementById(id); return el ? el.value.trim() : ''; }
function checked(id) { var el = document.getElementById(id); return el ? el.checked : false; }

function collectConfig() {
    var proto = document.getElementById('ndProtocol').value;
    var cfg = {};
    function collectNet() {
        var net = val('ndNetwork');
        if (!net || net === 'tcp') return;
        cfg.network = net;
        if (net === 'ws') { cfg.ws_path = val('ndWsPath'); if (val('ndWsHost')) cfg.ws_host = val('ndWsHost'); }
        if (net === 'h2') { if (val('ndH2Host')) cfg.h2_host = val('ndH2Host'); cfg.h2_path = val('ndH2Path'); }
        if (net === 'grpc') { cfg.grpc_service_name = val('ndGrpcName'); }
    }
    function collectTls() {
        cfg.tls = checked('ndTls');
        if (val('ndSni')) cfg.sni = val('ndSni');
        if (val('ndAlpn')) cfg.alpn = val('ndAlpn');
        if (checked('ndAllowInsecure')) cfg.allowInsecure = true;
        if (val('ndFingerprint')) cfg.fingerprint = val('ndFingerprint');
    }
    if (proto === 'vmess') {
        cfg.uuid = val('ndUuid'); cfg.alterId = parseInt(val('ndAlterId')) || 0; cfg.security = val('ndSecurity');
        collectNet(); collectTls();
    } else if (proto === 'vless') {
        cfg.uuid = val('ndUuid'); cfg.flow = val('ndFlow'); cfg.encryption = val('ndEncryption') || 'none';
        collectNet(); collectTls();
    } else if (proto === 'trojan') {
        cfg.password = val('ndPassword'); collectNet(); collectTls(); cfg.tls = true;
    } else if (proto === 'ss') {
        cfg.method = val('ndMethod'); cfg.password = val('ndPassword');
        if (val('ndPlugin')) { cfg.plugin = val('ndPlugin'); if (val('ndPluginOpts')) cfg.plugin_opts = val('ndPluginOpts'); }
    } else if (proto === 'hysteria2') {
        cfg.password = val('ndPassword');
        if (val('ndSni')) cfg.sni = val('ndSni');
        if (val('ndAlpn')) cfg.alpn = val('ndAlpn');
        if (checked('ndAllowInsecure')) cfg.allowInsecure = true;
        if (val('ndObfs')) { cfg.obfs = val('ndObfs'); if (val('ndObfsPassword')) cfg.obfs_password = val('ndObfsPassword'); }
        if (val('ndUpMbps')) cfg.up_mbps = parseInt(val('ndUpMbps'));
        if (val('ndDownMbps')) cfg.down_mbps = parseInt(val('ndDownMbps'));
    } else if (proto === 'tuic') {
        cfg.uuid = val('ndUuid'); cfg.password = val('ndPassword');
        if (val('ndSni')) cfg.sni = val('ndSni');
        if (val('ndAlpn')) cfg.alpn = val('ndAlpn');
        if (checked('ndAllowInsecure')) cfg.allowInsecure = true;
        cfg.congestion_control = val('ndCongestion') || 'cubic';
        cfg.udp_relay_mode = val('ndUdpRelay') || 'native';
    }
    return cfg;
}

function fillNodeForm(n) {
    document.getElementById('ndName').value = n.name || '';
    document.getElementById('ndProtocol').value = n.protocol;
    document.getElementById('ndAddress').value = n.address || '';
    document.getElementById('ndPort').value = n.port || '';
    onNdProtoChange(n.config || {});
}

function openNodeModal(editId) {
    document.getElementById('ndEditId').value = editId || '';
    document.getElementById('nodeModalTitle').textContent = editId ? 'Edit Node' : 'New Node';
    document.getElementById('ndImportUrl').value = '';
    if (editId) {
        var found = null;
        _groups.forEach(function(g) {
            g.nodes.forEach(function(n) { if (n.id === editId) found = n; });
        });
        if (found) {
            var cfg = {};
            try { cfg = JSON.parse(found.config_json || '{}'); } catch (e) {}
            fillNodeForm({ name: found.name, protocol: found.protocol, address: found.address, port: found.port, config: cfg });
        }
    } else {
        fillNodeForm({ protocol: 'vmess', config: {} });
    }
    openModal('nodeModal');
}

async function saveNode() {
    var editId = document.getElementById('ndEditId').value;
    var payload = {
        name: document.getElementById('ndName').value.trim(),
        protocol: document.getElementById('ndProtocol').value,
        address: document.getElementById('ndAddress').value.trim(),
        port: parseInt(document.getElementById('ndPort').value),
        config_json: JSON.stringify(collectConfig()),
    };
    if (!payload.name || !payload.address || !payload.port) { showMessage('Name, address and port are required'); return; }
    try {
        await api('/api/nodes' + (editId ? '/' + editId : ''), editId ? 'PUT' : 'POST', payload);
        closeModal('nodeModal');
        fetchNodes();
        showMessage('Saved. Restart sing-box on the route page to apply.');
    } catch (e) { showMessage('Save failed: ' + e); }
}

function delNode(id, name) {
    showConfirm('Delete Node', 'Delete node "' + name + '"?', async function() {
        try { await api('/api/nodes/' + id, 'DELETE'); fetchNodes(); }
        catch (e) { showMessage('Delete failed: ' + e); }
    }, 'Delete', true);
}

/* ---- 缓存秒开 + 进入页面时查询一次 ---- */
(function init() {
    var cached = loadCache('nodes');
    if (cached && cached.groups) _groups = cached.groups;
    _latencies = loadCache('nodes_lat') || {};
    if (_groups.length) renderGroups();
    fetchNodes().catch(function() {});
})();
