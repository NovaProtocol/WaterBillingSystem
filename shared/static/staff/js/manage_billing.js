(function () {
  'use strict';

  var billingItems = [], billingPage = 1, perPage = 10;

  function setText(id, value) {
    var el = document.getElementById(id);
    if (el) el.textContent = value;
  }

  customerAutocomplete('#customerSearch', '#customerDropdown', function (num) {
    document.getElementById('customerSearch').value = num;
    loadCustomer(num);
  });

  function loadCustomer(custNum) {
    fetch(API_CUSTOMER_URL.replace('0', encodeURIComponent(custNum)))
      .then(function (r) { return r.json(); })
      .then(function (data) {
        if (data.error) { alert(data.error); return; }

        setText('custNumLabel', '#' + custNum);
        setText('infoCustNum', data.customer_number);
        setText('infoName', data.name || ' - ');
        setText('infoAddress', data.address || ' - ');
        setText('infoContact', data.contact_number || ' - ');
        setText('infoEmail', data.email || ' - ');

        if (data.latest_reading) {
          setText('currentReading', data.latest_reading.reading_value + ' m\u00B3');
          setText('currentReader', data.latest_reading.reader || ' - ');
          var cd = new Date(data.latest_reading.timestamp * 1000);
          setText('currentDate', cd.toLocaleDateString() + ' ' + cd.toLocaleTimeString());
        } else {
          setText('currentReading', ' - ');
          setText('currentReader', '');
          setText('currentDate', '');
        }
        if (data.last_reading) {
          setText('prevReading', data.last_reading.reading_value + ' m\u00B3');
          setText('prevReader', 'Recorded by: ' + (data.last_reading.reader || 'Unknown'));
          var pd = new Date(data.last_reading.timestamp * 1000);
          setText('prevDate', pd.toLocaleDateString() + ' ' + pd.toLocaleTimeString());
        } else {
          setText('prevReading', ' - ');
          setText('prevReader', 'No previous reading');
          setText('prevDate', '');
        }

        var cons = (data.consumption != null && isFinite(data.consumption)) ? Number(data.consumption) : 0;
        setText('consumptionLabel', cons.toFixed(1) + ' m\u00B3');
        var tierBody = document.querySelector('#tierTable tbody');
        var th = '';
        (data.bill_breakdown || []).forEach(function (tier) {
          var u = (tier.units != null && isFinite(tier.units)) ? Number(tier.units) : 0;
          var c = (tier.charge != null && isFinite(tier.charge)) ? Number(tier.charge) : 0;
          th += '<tr><td>' + (tier.label || '') + '</td><td>' + u.toFixed(2) + '</td><td>\u20B1' + c.toFixed(2) + '</td></tr>';
        });
        tierBody.innerHTML = th;

        var uh = '', hasUnpaid = false;
        (data.unpaid_bills || []).forEach(function (b) {
          hasUnpaid = true;
          uh += '<div class="d-flex justify-content-between mb-1">'
            + '<span class="text-muted" style="font-size: 0.85rem;">' + b.month + '</span>'
            + '<span class="font-weight-bold" style="font-size: 0.85rem;">\u20B1' + ((b.amount != null && isFinite(b.amount)) ? Number(b.amount) : 0).toFixed(2) + '</span>'
            + '</div>';
          if (b.penalty > 0) {
            uh += '<div class="d-flex justify-content-between mb-2">'
              + '<span class="text-muted" style="font-size: 0.85rem; padding-left: 1.2rem;">+ Late Penalty</span>'
              + '<span class="font-weight-bold" style="font-size: 0.85rem; color: #dc3545;">+ \u20B1' + ((b.penalty != null && isFinite(b.penalty)) ? Number(b.penalty) : 0).toFixed(2) + '</span>'
              + '</div>';
          }
        });
        if (!hasUnpaid) uh = '<p class="text-muted mb-1" style="font-size:0.85rem;">No unpaid bills</p>';
        document.getElementById('unpaidBillsList').innerHTML = uh;

        if (data.carryover > 0) {
          document.getElementById('carryoverRow').style.display = '';
          var co = (data.carryover != null && isFinite(data.carryover)) ? Number(data.carryover) : 0;
          setText('summaryCarryover', '\u20B1' + co.toFixed(2));
        } else {
          document.getElementById('carryoverRow').style.display = 'none';
        }
        var td = (data.total_due != null && isFinite(data.total_due)) ? Number(data.total_due) : 0;
        setText('summaryTotalDue', '\u20B1' + td.toFixed(2));
        var dueRow = document.getElementById('dueDateRow');
        if (data.due_date) {
          dueRow.style.display = '';
          dueRow.textContent = 'Due in ' + data.days_remaining + ' days (' + data.due_date + ')';
        } else {
          dueRow.style.display = 'none';
        }

        billingItems = data.billing_items || [];
        billingPage = 1;
        renderBillingPage();

        var ph = '';
        (data.recent_payments || []).forEach(function (p) {
          var pd = new Date(p.timestamp * 1000);
          var pa = (p.paid_amount != null && isFinite(p.paid_amount)) ? Number(p.paid_amount) : 0;
          ph += '<tr><td>' + (p.receipt_number || 'N/A') + '</td><td>\u20B1' + pa.toFixed(2) + '</td><td>' + pd.toLocaleDateString() + '</td><td>' + (p.cashier || ' - ') + '</td></tr>';
        });
        document.getElementById('paymentHistoryBody').innerHTML = ph;

        document.getElementById('billingInfo').style.display = '';
      })
      .catch(function (err) { alert('Failed to load customer: ' + (err && err.message ? err.message : 'Unknown')); });
  }

  function renderBillingPage() {
    var tbody = document.getElementById('billingTableBody');
    var start = (billingPage - 1) * perPage;
    var page = billingItems.slice(start, start + perPage);
    var h = '';
    page.forEach(function (item) {
      var dt = new Date(item.timestamp * 1000);
      var period = dt.toLocaleDateString('en-US', { month: 'long', year: 'numeric' });
      var reading = (item.reading_value != null && isFinite(item.reading_value)) ? Number(item.reading_value) : 0;
      var consumption = (item.consumption != null && isFinite(item.consumption)) ? Number(item.consumption) : 0;
      var wb = (item.water_bill != null && isFinite(item.water_bill)) ? Number(item.water_bill) : 0;
      var penalty = (item.penalty != null && isFinite(item.penalty)) ? Number(item.penalty) : 0;
      var paid = (item.paid_amount != null && isFinite(item.paid_amount)) ? Number(item.paid_amount) : 0;
      var co2 = (item.carryover_offset != null && isFinite(item.carryover_offset)) ? Number(item.carryover_offset) : 0;
      var status = item.status || 'Unpaid';

      var statusBadge = '<span class="badge badge-secondary">' + status + '</span>';
      var actions = '';
      if (status === 'Paid') {
        statusBadge = '<span class="badge badge-success">Paid</span>';
        actions = '<button class="btn btn-outline-sm undo-payment" data-id="' + item.billing_id + '" data-amount="' + paid + '" data-receipt="' + (item.receipt_number || '') + '" title="Undo payment"><i class="fas fa-undo"></i></button>';
      } else if (status === 'Unpaid') {
        statusBadge = '<span class="badge badge-warning">Unpaid</span>';
      }

      var carry = ' - ';
      if (co2 !== 0) {
        carry = co2 < 0
          ? '<span style="color:#dc3545;">\u2212\u20B1' + Math.abs(co2).toFixed(2) + '</span>'
          : '\u20B1' + co2.toFixed(2);
      }

      h += '<tr>' +
        '<td>' + period + '</td>' +
        '<td>' + reading.toFixed(1) + '</td>' +
        '<td>' + consumption.toFixed(1) + ' m\u00B3</td>' +
        '<td>\u20B1' + wb.toFixed(2) + '</td>' +
        '<td>\u20B1' + penalty.toFixed(2) + '</td>' +
        '<td>\u20B1' + paid.toFixed(2) + '</td>' +
        '<td>' + carry + '</td>' +
        '<td>' + statusBadge + '</td>' +
        '<td>' + actions + '</td>' +
        '</tr>';
    });
    tbody.innerHTML = h;

    var totalPages = Math.ceil(billingItems.length / perPage) || 1;
    setText('billingPageInfo', 'Page ' + billingPage + ' of ' + totalPages + ' (' + billingItems.length + ' total)');
    renderPagination('#billingPagination', billingPage, totalPages, function (p) { billingPage = p; renderBillingPage(); });
  }

  document.addEventListener('click', function (e) {
    var btn = e.target.closest('.undo-payment');
    if (!btn) return;
    var id = btn.dataset.id;
    if (!id) { alert('No billing ID'); return; }
    document.getElementById('undoPaymentId').value = id;
    document.getElementById('undoReason').value = '';
    bootstrap.Modal.getOrCreateInstance(document.getElementById('undoPaymentModal')).show();
  });

  document.getElementById('undoPaymentForm').addEventListener('submit', function (e) {
    e.preventDefault();
    var id = document.getElementById('undoPaymentId').value;
    var reason = document.getElementById('undoReason').value;
    if (!reason) { alert('Reason is required'); return; }
    if (!confirm('Undo this payment? The bill will be reverted to unpaid.')) return;
    postJSON(UNDO_PAYMENT_URL_BASE.replace('0', id), { reason: reason })
      .then(function () {
        bootstrap.Modal.getOrCreateInstance(document.getElementById('undoPaymentModal')).hide();
        location.reload();
      })
      .catch(handleError);
  });
})();
