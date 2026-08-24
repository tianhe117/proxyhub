var _settings = {};

async function fetchSettings() {
    var d = await api('/api/settings');
    _settings = d.settings || {};
    saveCache('settings', { settings: _settings });
    renderSettings();
}

function renderSettings() {
    ['check_interval_normal', 'check_interval_failover', 'tcp_timeout', 'curl_timeout',
     'test_url', 'clash_api_port', 'web_port', 'web_username'].forEach(function(k) {
        var el = document.getElementById('s_' + k);
        if (el && _settings[k] !== undefined) el.value = _settings[k];
    });
    document.getElementById('pwState').textContent =
        _settings.web_password ? '(set)' : '(not set — auth disabled)';
}

async function saveSection(keys, restartHint) {
    var payload = {};
    keys.forEach(function(k) { payload[k] = document.getElementById('s_' + k).value; });
    try {
        await api('/api/settings', 'POST', payload);
        showMessage(restartHint ? 'Saved. Restart the app to apply.' : 'Saved.');
        fetchSettings();
    } catch (e) { showMessage('Save failed: ' + e); }
}

/* ---- sing-box 升级 ---- */
async function loadSbVersion() {
    try {
        var d = await api('/api/status');
        document.getElementById('sbCurrent').textContent = d.version || 'N/A';
    } catch (e) {}
}

async function checkUpgrade() {
    var btn = document.getElementById('btnCheckUpd');
    btn.disabled = true;
    try {
        var r = await api('/api/upgrade/status');
        if (!r.success) { showMessage(r.message || 'Check failed'); return; }
        document.getElementById('sbLatest').textContent = r.latest_version || 'unknown';
        document.getElementById('sbCurrent').textContent = r.current_version || 'N/A';
        document.getElementById('btnDownload').disabled = !r.is_update;
        if (!r.is_update) showMessage('Already up to date');
    } catch (e) { showMessage('Check failed: ' + e); }
    btn.disabled = false;
}

async function downloadUpgrade() {
    var btn = document.getElementById('btnDownload');
    btn.disabled = true;
    btn.textContent = 'Downloading...';
    try {
        var r = await api('/api/upgrade/download', 'POST');
        showMessage(r.message || (r.success ? 'Done' : 'Failed'));
        loadSbVersion();
    } catch (e) { showMessage('Download failed: ' + e); }
    btn.textContent = 'Download Update';
    btn.disabled = false;
}

/* ---- 密码 ---- */
function openChangePw() {
    document.getElementById('pwNew').value = '';
    document.getElementById('pwConfirm').value = '';
    openModal('pwModal');
}

async function savePw() {
    var p1 = document.getElementById('pwNew').value;
    var p2 = document.getElementById('pwConfirm').value;
    if (!p1) { showMessage('Password cannot be empty — use Clear Password instead'); return; }
    if (p1 !== p2) { showMessage('Passwords do not match'); return; }
    try {
        await api('/api/settings', 'POST', { web_password: p1 });
        closeModal('pwModal');
        showMessage('Password updated.');
        fetchSettings();
    } catch (e) { showMessage('Save failed: ' + e); }
}

function openClearPw() {
    document.getElementById('clearPwInput').value = '';
    openModal('clearPwModal');
}

async function doClearPw() {
    if (document.getElementById('clearPwInput').value !== 'CLEAR') {
        showMessage('Type CLEAR to confirm');
        return;
    }
    try {
        await api('/api/settings', 'POST', { web_password: '' });
        closeModal('clearPwModal');
        showMessage('Password cleared — authentication is now disabled.');
        fetchSettings();
    } catch (e) { showMessage('Failed: ' + e); }
}

/* ---- 日志 ---- */
async function loadLogs() {
    try {
        var d = await api('/api/logs?tail=200');
        document.getElementById('logFileName').textContent = d.file ? d.file : '(no log file)';
        document.getElementById('logView').innerHTML = (d.lines || []).map(escapeHtml).join('\n');
        var view = document.getElementById('logView');
        view.scrollTop = view.scrollHeight;
    } catch (e) { showMessage('Load logs failed: ' + e); }
}

/* ---- 危险区 ---- */
function clearNodes() {
    showConfirm('Clear All Nodes', 'Delete ALL nodes (subscriptions kept)?', async function() {
        try { await api('/api/nodes/clear', 'POST'); showMessage('All nodes cleared'); }
        catch (e) { showMessage('Failed: ' + e); }
    }, 'Clear', true);
}

/* ---- 缓存秒开 ---- */
(function init() {
    var cached = loadCache('settings');
    if (cached && cached.settings) { _settings = cached.settings; renderSettings(); }
    fetchSettings();
    loadSbVersion();
    loadLogs();
})();
