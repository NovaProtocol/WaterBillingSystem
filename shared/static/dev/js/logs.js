(function () {
  'use strict';

  var refreshTimer = null;

  function esc(s) { return $('<span>').text(s).html(); }

  function loadLogs() {
    var service = $('#filter-service').val();
    var level = $('#filter-level').val();
    var q = $('#filter-q').val();
    $.getJSON('/developer/api/logs', { service: service, level: level, q: q, limit: 500 }, function (res) {
      renderLogs(res.data || []);
    });
  }

  function renderLogs(rows) {
    var tbody = $('#logBody').empty();
    if (!rows.length) {
      tbody.append('<tr><td colspan="4" class="text-center text-muted py-4">No logs match your filters.</td></tr>');
      return;
    }
    rows.forEach(function (r) {
      var levelClass = 'log-level-' + r.level;
      var svcClass = 'log-svc-' + (r.service || '');
      tbody.append(
        '<tr class="' + levelClass + '">' +
          '<td class="log-ts">' + esc(r.timestamp) + '</td>' +
          '<td class="log-lvl font-weight-bold">' + esc(r.level) + '</td>' +
          '<td class="' + svcClass + '">' + esc(r.service || '') + '</td>' +
          '<td class="monospace log-msg">' + esc(r.message || '') + '</td>' +
        '</tr>'
      );
    });
  }

  function clearLogs() {
    if (!confirm('Clear all log entries from all services?')) return;
    $.post('/developer/api/logs/clear', function () { loadLogs(); });
  }

  window.loadLogs = loadLogs;
  window.clearLogs = clearLogs;

  $('#filter-service, #filter-level, #filter-q').on('change', function () { loadLogs(); });
  $('#filter-q').on('input', function () { loadLogs(); });

  $(function () {
    loadLogs();
    refreshTimer = setInterval(function () {
      if ($('#autorefresh').is(':checked')) loadLogs();
    }, 5000);
  });
})();
