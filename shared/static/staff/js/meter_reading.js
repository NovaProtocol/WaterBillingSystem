(function () {
  'use strict';

  function openModal(id) { window.openModal(document.getElementById(id)); }
  function closeModal(id) { window.closeModal(document.getElementById(id)); }

  document.getElementById('generateKeyForm').addEventListener('submit', function (e) {
    e.preventDefault();
    var form = this;
    var btn = form.querySelector('button[type=submit]');
    btn.disabled = true;
    btn.innerHTML = '<i class="fas fa-spinner fa-spin me-1"></i>Generating...';
    var labelEl = document.getElementById('keyLabel');
    postJSON(GENERATE_KEY_URL, { label: labelEl ? labelEl.value.trim() : '' })
      .then(function (resp) {
        closeModal('generateKeyModal');
        document.getElementById('generatedKey').value = resp.key;
        var qr = document.getElementById('qrcode');
        qr.innerHTML = '';
        new QRCode(qr, { text: resp.key, width: 180, height: 180 });
        openModal('keyResultModal');
        form.reset();
        btn.disabled = false;
        btn.textContent = 'Generate';

        var now = new Date();
        var dateStr = now.getFullYear() + '-' + String(now.getMonth() + 1).padStart(2, '0') + '-' + String(now.getDate()).padStart(2, '0') + 'T' + String(now.getHours()).padStart(2, '0') + ':' + String(now.getMinutes()).padStart(2, '0');
        var row = '<tr>' +
          '<td><div class="input-group input-group-sm input-group-sm-nofold mw-260px">' +
          '<input type="password" class="form-control form-control-sm-app key-input form-control-monospace" value="' + resp.key + '" readonly data-full="' + resp.key + '">' +
          '<button class="btn btn-outline-sm toggle-key" type="button" title="Toggle visibility"><i class="fas fa-eye"></i></button>' +
          '<button class="btn btn-outline-sm qr-key" type="button" data-key="' + resp.key + '" title="Show QR"><i class="fas fa-qrcode"></i></button>' +
          '</div></td>' +
          '<td>' + (resp.label || '\u2014') + '</td>' +
          '<td><span class="badge badge-success">Active</span></td>' +
          '<td>' + dateStr + '</td>' +
          '<td><button class="btn btn-outline-sm revoke-key" data-id="' + resp.id + '" title="Revoke"><i class="fas fa-trash"></i></button></td>' +
          '</tr>';
        var tbody = document.querySelector('#keysTable tbody');
        if (tbody.querySelectorAll('tr').length === 0) {
          tbody.insertAdjacentHTML('beforeend', row);
          var noKeys = document.getElementById('noKeysMessage');
          if (noKeys) noKeys.style.display = 'none';
          document.getElementById('keysTable').style.display = '';
        } else {
          tbody.insertAdjacentHTML('afterbegin', row);
        }
      })
      .catch(function (err) {
        btn.disabled = false;
        btn.textContent = 'Generate';
        alert('Failed to generate key: ' + (err && err.message ? err.message : 'unknown'));
      });
  });

  document.addEventListener('click', function (e) {
    var toggleBtn = e.target.closest('.toggle-key');
    if (toggleBtn) {
      var input = toggleBtn.closest('.input-group').querySelector('.key-input');
      var icon = toggleBtn.querySelector('i');
      if (input.getAttribute('type') === 'password') {
        input.setAttribute('type', 'text');
        icon.classList.remove('fa-eye');
        icon.classList.add('fa-eye-slash');
      } else {
        input.setAttribute('type', 'password');
        icon.classList.remove('fa-eye-slash');
        icon.classList.add('fa-eye');
      }
      return;
    }

    var copyBtn = e.target.closest('#copyKeyBtn');
    if (copyBtn) {
      var key = document.getElementById('generatedKey').value;
      navigator.clipboard.writeText(key).then(function () {
        var icon = copyBtn.querySelector('i');
        icon.classList.remove('fa-copy');
        icon.classList.add('fa-check');
        setTimeout(function () { icon.classList.remove('fa-check'); icon.classList.add('fa-copy'); }, 2000);
      });
      return;
    }

    var qrBtn = e.target.closest('.qr-key');
    if (qrBtn) {
      document.getElementById('generatedKey').value = qrBtn.dataset.key;
      var qr = document.getElementById('qrcode');
      qr.innerHTML = '';
      new QRCode(qr, { text: qrBtn.dataset.key, width: 180, height: 180 });
      openModal('keyResultModal');
      return;
    }

    var revokeBtn = e.target.closest('.revoke-key');
    if (revokeBtn) {
      if (!confirm('Revoke this API key? This cannot be undone.')) return;
      var id = revokeBtn.dataset.id;
      var row = revokeBtn.closest('tr');
      postJSON(REVOKE_KEY_URL_BASE.replace('0', id), {})
        .then(function () {
          var badge = row.querySelector('.badge');
          badge.classList.remove('badge-success');
          badge.classList.add('badge-secondary');
          badge.textContent = 'Revoked';
          revokeBtn.remove();
          row.classList.add('revoked-row');
          var hideRevoked = document.getElementById('hideRevoked');
          if (hideRevoked && hideRevoked.checked) row.style.display = 'none';
        })
        .catch(function (err) { alert('Failed to revoke key: ' + (err && err.message ? err.message : 'unknown')); });
    }
  });

  var hideRevoked = document.getElementById('hideRevoked');
  if (hideRevoked) {
    hideRevoked.addEventListener('change', function () {
      Array.prototype.forEach.call(document.querySelectorAll('.revoked-row'), function (r) {
        r.style.display = hideRevoked.checked ? 'none' : '';
      });
    });
    if (hideRevoked.checked) {
      Array.prototype.forEach.call(document.querySelectorAll('.revoked-row'), function (r) { r.style.display = 'none'; });
    }
  }
})();
