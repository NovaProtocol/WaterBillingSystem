(function () {
  'use strict';

  function updateTotal() {
    var c = parseInt(document.getElementById('seed-customers').value) || 0;
    var m = parseInt(document.getElementById('seed-months').value) || 0;
    var t = c * m;
    document.getElementById('seed-total').value = t.toLocaleString() + ' entries';
    document.getElementById('seed-total').style.color = t > 10000000 ? '#dc3545' : '#1a1a2e';
  }

  document.getElementById('seed-customers').addEventListener('input', updateTotal);
  document.getElementById('seed-months').addEventListener('input', updateTotal);
  updateTotal();

  window.execSeed = function () {
    confirmAndExec('seed', {
      customers: document.getElementById('seed-customers').value,
      months: document.getElementById('seed-months').value,
      cashiers: document.getElementById('seed-cashiers').value,
      readers: document.getElementById('seed-readers').value,
      randomize_months: document.getElementById('seed-randomize').value,
      read_current: document.getElementById('seed-read-current').value,
      pay_last: document.getElementById('seed-pay-last').value,
      allow_deactivation: document.getElementById('seed-deactivate').value,
    }, 'This will clear all data and generate new test data with the configured options.');
  };
})();
