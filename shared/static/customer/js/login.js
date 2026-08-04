(function () {
  'use strict';

  var form = document.getElementById('login-form');
  var btn = document.getElementById('login-btn');
  var alertBox = document.getElementById('login-alert');
  var alertMsg = document.getElementById('login-alert-msg');

  var prefill = new URLSearchParams(window.location.search).get('account_number');
  if (prefill) {
    var numInput = document.getElementById('account_number');
    if (numInput) numInput.value = prefill;
  }

  function showError(msg) {
    alertMsg.textContent = msg;
    alertBox.classList.remove('d-none');
  }

  function hideError() {
    alertBox.classList.add('d-none');
  }

  if (!form) return;

  form.addEventListener('submit', function (e) {
    e.preventDefault();
    hideError();

    var account_number = document.getElementById('account_number').value.trim();
    if (!account_number) {
      showError('Account number is required.');
      return;
    }

    btn.disabled = true;
    btn.innerHTML = '<i class="fas fa-spinner fa-spin mr-2"></i>Verifying...';

    fetch('/customer/api/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'same-origin',
      body: JSON.stringify({
        account_number: account_number,
        name: document.getElementById('name_field').value,
        last_receipt: document.getElementById('receipt_field').value.trim(),
      }),
    })
      .then(function (resp) {
        return resp.json().then(function (data) {
          return { ok: resp.ok, data: data };
        });
      })
      .then(function (result) {
        if (result.ok && result.data.redirect) {
          window.location.href = result.data.redirect;
          return;
        }
        showError((result.data && result.data.error) || 'Verification failed. Please try again.');
        btn.disabled = false;
        btn.innerHTML = '<i class="fas fa-search mr-2"></i>View My Bill';
      })
      .catch(function () {
        showError('Unable to reach the server. Please try again.');
        btn.disabled = false;
        btn.innerHTML = '<i class="fas fa-search mr-2"></i>View My Bill';
      });
  });
})();
