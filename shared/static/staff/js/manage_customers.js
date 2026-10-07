(function () {
  'use strict';

  var currentClearNfcId = null;

  document.addEventListener('click', function (e) {
    var btn = e.target.closest('.edit-customer');
    if (!btn) return;
    var ds = btn.dataset;

    var set = function (id, value) {
      var el = document.getElementById(id);
      if (el) el.value = value == null ? '' : value;
    };
    set('editCustId', ds.id);
    set('editCustNumber', ds.number);
    set('editCustName', ds.name);
    set('editCustContact', ds.contact);
    set('editCustAddress', ds.address);
    set('editCustEmail', ds.email);
    set('editCustPhase', ds.phase);
    set('editCustBlock', ds.block);
    set('editCustStreet', ds.street);
    set('editCustX', ds.x);
    set('editCustY', ds.y);
    set('editCustMeterSn', ds.meterSn || '');

    var nfcTagId = ds.nfcTagId || '';
    var hasNfc = nfcTagId.length > 0;
    var clearBtn = document.getElementById('clearNfcBtn');
    var label = document.getElementById('clearNfcLabel');
    if (hasNfc) {
      clearBtn.disabled = false;
      clearBtn.style.opacity = '1';
      clearBtn.style.background = '#dc3545';
      clearBtn.style.color = '#fff';
      clearBtn.style.border = '1px solid #dc3545';
      clearBtn.style.cursor = 'pointer';
      label.textContent = 'Clear NFC Mapping (' + nfcTagId.substring(0, 12) + '...)';
    } else {
      clearBtn.disabled = true;
      clearBtn.style.opacity = '0.4';
      clearBtn.style.background = '#e9ecef';
      clearBtn.style.color = '#6c757d';
      clearBtn.style.border = '1px solid #dee2e6';
      clearBtn.style.cursor = 'not-allowed';
      label.textContent = 'No NFC Mapping';
    }

    currentClearNfcId = ds.id;
    bootstrap.Modal.getOrCreateInstance(document.getElementById('editCustomerModal')).show();
  });

  document.getElementById('editCustomerForm').addEventListener('submit', function (e) {
    e.preventDefault();
    var id = document.getElementById('editCustId').value;
    var val = function (fid) { return document.getElementById(fid).value.trim(); };
    var num = function (fid) { var v = parseFloat(document.getElementById(fid).value); return isNaN(v) ? null : v; };
    postJSON(EDIT_CUSTOMER_URL_BASE.replace('0', id), {
      name: val('editCustName'),
      address: val('editCustAddress'),
      contact_number: val('editCustContact'),
      email: val('editCustEmail'),
      phase: val('editCustPhase'),
      block: val('editCustBlock'),
      street: val('editCustStreet'),
      x_coordinate: num('editCustX'),
      y_coordinate: num('editCustY'),
      meter_serial_number: val('editCustMeterSn'),
    })
      .then(function () {
        bootstrap.Modal.getOrCreateInstance(document.getElementById('editCustomerModal')).hide();
        location.reload();
      })
      .catch(handleError);
  });

  document.addEventListener('click', function (e) {
    var btn = e.target.closest('.toggle-active');
    if (!btn) return;
    var id = btn.dataset.id;
    var active = btn.dataset.active === 'true';
    var action = active ? 'deactivate' : 'reactivate';
    if (!confirm('Are you sure you want to ' + action + ' this customer? This may affect billing.')) return;
    postJSON(TOGGLE_ACTIVE_URL_BASE.replace('0', id), {})
      .then(function () { location.reload(); })
      .catch(handleError);
  });

  document.getElementById('clearNfcBtn').addEventListener('click', function () {
    if (!currentClearNfcId || this.disabled) return;
    if (!confirm('Clear NFC mapping for this customer? The mobile app will detect this change and remove the tag from its local cache on next sync.')) return;
    postJSON(CLEAR_NFC_URL_BASE.replace('0', currentClearNfcId), {})
      .then(function (data) {
        alert(data.message);
        bootstrap.Modal.getOrCreateInstance(document.getElementById('editCustomerModal')).hide();
        location.reload();
      })
      .catch(handleError);
  });
})();
