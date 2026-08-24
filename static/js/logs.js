function renderLogs(data) {
    if (!data) return;
    document.getElementById('logFileName').textContent = data.file || '(no log file)';
    var view = document.getElementById('logView');
    view.innerHTML = (data.lines || []).map(escapeHtml).join('\n');
    view.scrollTop = view.scrollHeight;
}

async function loadLogs() {
    try {
        var data = await api('/api/logs?tail=200');
        renderLogs(data);
    } catch (e) {
        showMessage('Load logs failed: ' + e);
    }
}

(function init() {
    loadLogs();
})();
