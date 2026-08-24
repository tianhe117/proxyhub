var _subs = [];

function formatBytes(b) {
    b = parseInt(b) || 0;
    if (b < 1024) return b + ' B';
    var units = ['KB', 'MB', 'GB', 'TB'];
    for (var i = 0; i < units.length; i++) {
        b /= 1024;
        if (b < 1024) return b.toFixed(1) + ' ' + units[i];
    }
    return b.toFixed(1) + ' PB';
}

function expireText(ts) {
    ts = parseInt(ts) || 0;
    if (!ts) return '';
    var d = new Date(ts * 1000);
    var days = Math.ceil((ts * 1000 - Date.now()) / 86400000);
    return d.toISOString().slice(0, 10) + ' (' + days + ' days)';
}

function kwPreview(text) {
    if (!text || !text.trim()) return '<span class="muted">click to set</span>';
    return text.split(/[\n,]+/).map(function(k) { return k.trim(); }).filter(Boolean)
        .map(function(k) { return '<span class="tag">' + escapeHtml(k) + '</span>'; }).join(' ');
}

function renderSubs() {
    var list = document.getElementById('subList');
    if (!_subs.length) {
        list.innerHTML = '';
        document.getElementById('subEmpty').style.display = 'block';
        return;
    }
    document.getElementById('subEmpty').style.display = 'none';
    list.innerHTML = _subs.map(function(s) {
        var traffic = '';
        if (s.total_bytes) {
            var used = (parseInt(s.upload_bytes) || 0) + (parseInt(s.download_bytes) || 0);
            traffic = '<div class="row-flex"><span style="flex:1;">Traffic: ' + formatBytes(used) + ' / ' + formatBytes(s.total_bytes) +
                ' — ' + formatBytes(s.total_bytes - used) + ' remaining</span></div>';
        }
        var expire = s.expire_at ? '<div class="row-flex"><span style="flex:1;">Expires: ' + expireText(s.expire_at) + '</span></div>' : '';
        var updated = s.updated_at ? s.updated_at.slice(0, 16).replace('T', ' ') : 'never';
        return '<div class="section"><div class="section-body">' +
            '<div class="row-flex" style="border:none;">' +
                '<strong style="flex:1;">' + escapeHtml(s.name) + ' &middot; ' + (s.node_count || 0) + ' nodes</strong>' +
                '<span class="muted">updated: ' + updated + '</span>' +
                '<button class="btn btn-sm btn-ok" onclick="refreshSub(' + s.id + ',this)" title="Refresh">&#8635;</button>' +
                '<button class="btn btn-sm" onclick="openSubModal(' + s.id + ')">&#9998;</button>' +
                '<button class="btn btn-sm btn-danger" onclick="delSub(' + s.id + ',\'' + escapeHtml(s.name) + '\')">&#10005;</button>' +
            '</div>' +
            traffic + expire +
            '<div class="row-flex"><span class="muted" style="width:60px;">filter</span>' +
                '<span style="flex:1;cursor:pointer;" onclick="openKw(' + s.id + ',\'filter_keywords\')">' + kwPreview(s.filter_keywords) + '</span></div>' +
            '<div class="row-flex"><span class="muted" style="width:60px;">exclude</span>' +
                '<span style="flex:1;cursor:pointer;" onclick="openKw(' + s.id + ',\'exclude_keywords\')">' + kwPreview(s.exclude_keywords) + '</span></div>' +
            '</div></div>';
    }).join('');
}

async function fetchSubs() {
    var results = await Promise.all([api('/api/subscriptions'), api('/api/nodes/grouped')]);
    _subs = results[0].subscriptions || [];
    var counts = {};
    (results[1].groups || []).forEach(function(g) {
        if (g.sub) counts[g.sub.id] = g.nodes.length;
    });
    _subs.forEach(function(s) { s.node_count = counts[s.id] || 0; });
    saveCache('subscriptions', { subs: _subs });
    renderSubs();
}

function openSubModal(editId) {
    document.getElementById('subEditId').value = editId || '';
    document.getElementById('subModalTitle').textContent = editId ? 'Edit Subscription' : 'New Subscription';
    document.getElementById('subName').value = '';
    document.getElementById('subUrl').value = '';
    if (editId) {
        var s = _subs.find(function(x) { return x.id === editId; });
        if (s) {
            document.getElementById('subName').value = s.name;
            document.getElementById('subUrl').value = s.url;
        }
    }
    openModal('subModal');
}

async function saveSub() {
    var editId = document.getElementById('subEditId').value;
    var payload = {
        name: document.getElementById('subName').value.trim(),
        url: document.getElementById('subUrl').value.trim(),
    };
    if (!payload.name || !payload.url) { showMessage('Name and URL are required'); return; }
    try {
        await api('/api/subscriptions' + (editId ? '/' + editId : ''), editId ? 'PUT' : 'POST', payload);
        closeModal('subModal');
        fetchSubs();
    } catch (e) { showMessage('Save failed: ' + e); }
}

function delSub(id, name) {
    showConfirm('Delete Subscription', 'Delete subscription "' + name + '" and its nodes?', async function() {
        try { await api('/api/subscriptions/' + id, 'DELETE'); fetchSubs(); }
        catch (e) { showMessage('Delete failed: ' + e); }
    }, 'Delete', true);
}

async function refreshSub(id, btn) {
    btn.disabled = true;
    try {
        var r = await api('/api/subscriptions/' + id + '/refresh', 'POST');
        showMessage(r.message || (r.success ? 'Refreshed' : 'Refresh failed'));
        fetchSubs();
    } catch (e) { showMessage('Refresh failed: ' + e); }
    btn.disabled = false;
}

/* ---- 关键字编辑 ---- */
function openKw(subId, field) {
    var s = _subs.find(function(x) { return x.id === subId; });
    if (!s) return;
    document.getElementById('kwSubId').value = subId;
    document.getElementById('kwField').value = field;
    document.getElementById('kwModalTitle').textContent = field === 'filter_keywords' ? 'Filter Keywords' : 'Exclude Keywords';
    document.getElementById('kwText').value = (s[field] || '').replace(/,/g, '\n');
    openModal('kwModal');
}

async function saveKw() {
    var subId = document.getElementById('kwSubId').value;
    var field = document.getElementById('kwField').value;
    var payload = {};
    payload[field] = document.getElementById('kwText').value;
    try {
        await api('/api/subscriptions/' + subId, 'PUT', payload);
        closeModal('kwModal');
        fetchSubs();
        showMessage('Saved. Click refresh to apply keywords.');
    } catch (e) { showMessage('Save failed: ' + e); }
}

/* ---- 缓存秒开 ---- */
(function init() {
    var cached = loadCache('subscriptions');
    if (cached && cached.subs) { _subs = cached.subs; renderSubs(); }
    startPolling(fetchSubs, 10000);
})();
