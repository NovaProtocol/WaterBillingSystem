(function () {
  'use strict';

  var pendingAction = null;
  var pendingData = null;

  window.confirmAndExec = function (action, data, message) {
    pendingAction = action;
    pendingData = data || {};
    document.getElementById('confirm-message').textContent = message || '';
    document.getElementById('confirm-input').value = '';
    document.getElementById('confirm-execute').disabled = true;
    fetch(window.DEV_URLS.confirm, { method: 'POST' })
      .then(function (r) { return r.json(); })
      .then(function (r) {
        document.getElementById('confirm-code').textContent = r.code;
        $('#confirm-modal').modal('show');
      });
  };

  document.getElementById('confirm-input').addEventListener('input', function () {
    var code = document.getElementById('confirm-code').textContent;
    document.getElementById('confirm-execute').disabled = this.value !== code;
  });

  document.getElementById('confirm-execute').addEventListener('click', function () {
    var url = window.DEV_URLS[pendingAction];
    if (!url) return;

    var body = new FormData();
    body.append('confirm_code', document.getElementById('confirm-input').value);
    Object.keys(pendingData || {}).forEach(function (k) { body.append(k, pendingData[k]); });

    $('#confirm-modal').modal('hide');
    fetch(url, { method: 'POST', body: body })
      .then(function (r) { return r.json().catch(function () { return { error: 'Request failed' }; }); })
      .then(function (r) {
        var hdr = document.getElementById('result-header');
        var bdy = document.getElementById('result-body');
        if (r.error) {
          hdr.className = 'modal-header bg-danger text-white';
          hdr.innerHTML = '<h5 class="modal-title">Error</h5>';
          bdy.innerHTML = '<div class="alert alert-danger mb-0">' + r.error + '</div>';
        } else {
          hdr.className = 'modal-header bg-success text-white';
          hdr.innerHTML = '<h5 class="modal-title">Success</h5>';
          bdy.innerHTML = '<div class="alert alert-success mb-0">' + (r.message || 'Done') + '</div>';
        }
        $('#result-modal').modal('show');
        if (pendingAction === 'backup') refreshBackups();
        if (pendingAction === 'clear' || pendingAction === 'seed') setTimeout(function () { location.reload(); }, 2000);
      });
  });

  window.refreshBackups = function () {
    fetch(window.DEV_URLS.list_backups)
      .then(function (r) { return r.json(); })
      .then(function (r) {
        var sel = document.getElementById('restore-file');
        if (!sel) return;
        sel.innerHTML = '<option value="">-- Select backup --</option>';
        (r.backups || []).forEach(function (b) {
          sel.innerHTML += '<option value="' + b.name + '">' + b.name + '</option>';
        });
      });
  };
})();
