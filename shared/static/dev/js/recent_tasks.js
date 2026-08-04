(function () {
  'use strict';

  var sc = { queued: '#6c757d', running: '#007bff', completed: '#28a745', error: '#dc3545', interrupted: '#fd7e14' };
  var last = '';

  function poll() {
    fetch(window.DEV_URLS.list_tasks)
      .then(function (r) { if (!r.ok) throw new Error(r.status); return r.json(); })
      .then(function (r) {
        var s = JSON.stringify(r);
        if (s === last) return;
        last = s;
        var el = document.getElementById('recent-tasks');
        if (!el) return;
        var cur = r.current, hist = (r.history || []).slice(0, 6);
        var all = cur ? [cur].concat(hist) : hist;
        if (!all.length) { el.innerHTML = '<div class="text-center text-muted py-4 text-sm">No tasks</div>'; return; }
        var h = '';
        all.forEach(function (t) {
          var icon = t.status === 'running' ? 'fa-spinner fa-pulse'
            : t.status === 'completed' ? 'fa-check-circle'
            : t.status === 'error' ? 'fa-times-circle'
            : 'fa-clock';
          var c = sc[t.status] || '#6c757d';
          h += '<div class="d-flex justify-content-between align-items-center px-3 py-1" style="border-bottom:1px solid #f0f0f0;font-size:0.78rem;">' +
            '<span><i class="fas ' + icon + '" style="color:' + c + ';width:14px;"></i> ' + t.title + '</span>' +
            '<span style="color:' + c + ';font-weight:600;">' + t.status + '</span>' +
          '</div>';
        });
        el.innerHTML = h;
      });
  }

  poll();
  setInterval(poll, 5000);
})();
