(function () {
  'use strict';

  var refreshTimer = null;

  function esc(s) {
    var d = document.createElement('div');
    d.textContent = s == null ? '' : String(s);
    return d.innerHTML;
  }

  function loadLogs() {
    var service = document.getElementById('filter-service').value;
    var level = document.getElementById('filter-level').value;
    var q = document.getElementById('filter-q').value;
    var params = new URLSearchParams({ service: service, level: level, q: q, limit: 500 });
    fetch('/developer/api/logs?' + params.toString())
      .then(function (r) { return r.json(); })
      .then(function (res) { renderLogs(res.data || []); })
      .catch(function () {});
  }

  function renderLogs(rows) {
    var tbody = document.getElementById('logBody');
    if (!tbody) return;
    if (!rows.length) {
      tbody.innerHTML = '<tr><td colspan="4" class="text-center text-muted py-4">No logs match your filters.</td></tr>';
      return;
    }
    var h = '';
    rows.forEach(function (r) {
      var levelClass = 'log-level-' + r.level;
      var svcClass = 'log-svc-' + (r.service || '');
      h += '<tr class="' + levelClass + '">' +
        '<td class="log-ts">' + esc(r.timestamp) + '</td>' +
        '<td class="log-lvl font-weight-bold">' + esc(r.level) + '</td>' +
        '<td class="' + svcClass + '">' + esc(r.service || '') + '</td>' +
        '<td class="monospace log-msg">' + esc(r.message || '') + '</td>' +
        '</tr>';
    });
    tbody.innerHTML = h;
  }

  function clearLogs() {
    if (!confirm('Clear all log entries from all services?')) return;
    fetch('/developer/api/logs/clear', { method: 'POST' })
      .then(function () { loadLogs(); })
      .catch(function () {});
  }

  window.loadLogs = loadLogs;
  window.clearLogs = clearLogs;

  function boot() {
    ['filter-service', 'filter-level', 'filter-q'].forEach(function (id) {
      var el = document.getElementById(id);
      if (el) el.addEventListener('change', loadLogs);
    });
    var fq = document.getElementById('filter-q');
    if (fq) fq.addEventListener('input', loadLogs);

    loadLogs();
    refreshTimer = setInterval(function () {
      var ar = document.getElementById('autorefresh');
      if (ar && ar.checked) loadLogs();
    }, 5000);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', boot);
  } else {
    boot();
  }
})();
