(function () {
  'use strict';

  var state = null;
  var BASE_AMOUNT = 0;
  var selectedMethod = null;

  // ---------------------------------------------------------------------
  // Helpers
  // ---------------------------------------------------------------------

  function esc(s) {
    return String(s == null ? '' : s)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  }

  function money(n) {
    return (Number(n) || 0).toFixed(2);
  }

  function pad(n) {
    return (n < 10 ? '0' : '') + n;
  }

  function fmtTs(ts) {
    if (!ts) return '';
    var d = new Date(Number(ts) * 1000);
    return d.getFullYear() + '-' + pad(d.getMonth() + 1) + '-' + pad(d.getDate()) +
      ' ' + pad(d.getHours()) + ':' + pad(d.getMinutes());
  }

  function fmtDate(ts) {
    if (!ts) return '';
    return new Date(Number(ts) * 1000).toLocaleDateString();
  }

  function text(id) {
    return document.getElementById(id);
  }

  function show(el, visible) {
    if (!el) return;
    el.classList.toggle('d-none', !visible);
  }

  function shown(id) {
    var el = text(id);
    return !!(el && !el.classList.contains('d-none'));
  }

  function getJSON(url) {
    return fetch(url, { credentials: 'same-origin' }).then(function (r) { return r.json(); });
  }

  // ---------------------------------------------------------------------
  // Rendering
  // ---------------------------------------------------------------------

  function renderCustomer(customer) {
    text('cust-number').textContent = customer.customer_number;
    text('cust-name').textContent = customer.name || '';
    text('cust-address').textContent = customer.address || '';
    text('cust-contact').textContent = customer.contact_number || '';
    text('cust-email').textContent = customer.email || '';
  }

  function renderReadings(billing) {
    var current = billing.latest_reading;
    var previous = billing.last_reading;

    if (current) {
      text('current-reading-value').textContent = current.reading_value;
      text('current-reading-reader').textContent = 'Recorded by: ' + (current.reader || 'Unknown');
      text('current-reading-date').textContent = fmtTs(current.timestamp);
    } else {
      text('current-reading-value').textContent = '';
      text('current-reading-reader').textContent = 'No readings available';
      text('current-reading-date').textContent = '';
    }

    if (previous) {
      text('previous-reading-value').textContent = previous.reading_value;
      text('previous-reading-reader').textContent = 'Recorded by: ' + (previous.reader || 'Unknown');
      text('previous-reading-date').textContent = fmtTs(previous.timestamp);
    } else {
      text('previous-reading-value').textContent = '';
      text('previous-reading-reader').textContent = 'No previous reading';
      text('previous-reading-date').textContent = '';
    }
  }

  function renderPricing(billing) {
    var canCompute = billing.latest_reading && billing.last_reading;
    var table = text('pricing-table');
    var empty = text('pricing-empty');
    var notice = text('consumption-notice');

    if (!canCompute) {
      empty.classList.remove('d-none');
      return;
    }

    notice.classList.remove('d-none');
    text('consumption-notice-text').textContent = money(billing.consumption) + ' m\u00B3';

    var tbody = text('pricing-tbody');
    var html = '';
    var tiers = billing.pricing_tiers || [];

    billing.bill_breakdown.forEach(function (item, i) {
      var rowClass = item.units === 0 ? 'breakdown-row-muted' : 'breakdown-row';
      var tier = tiers[i] || {};
      var rate;
      if (tier.unit === 'flat') rate = '&#x20B1;' + money(tier.rate) + ' flat';
      else rate = '&#x20B1;' + money(tier.rate) + '/m\u00B3';

      html += '<tr class="' + rowClass + '">' +
        '<td>' + esc(item.label) + '</td>' +
        '<td>' + money(item.units) + ' m\u00B3</td>' +
        '<td>' + rate + '</td>' +
        '<td class="text-end font-weight-bold">&#x20B1;' + money(item.charge) + '</td>' +
        '</tr>';
    });

    html += '<tr class="font-weight-bold breakdown-total">' +
      '<td colspan="3">Total Water Bill</td>' +
      '<td class="text-end">&#x20B1;' + money(billing.original_water_bill) + '</td>' +
      '</tr>';
    tbody.innerHTML = html;

    table.classList.remove('d-none');
  }

  function renderBillSummary(billing) {
    var unpaidWrap = text('unpaid-bills');
    var uh = '';
    var showPaidRow = false;
    var showPaidCheck = false;
    var showNoBills = false;

    if (billing.unpaid_bills && billing.unpaid_bills.length) {
      billing.unpaid_bills.forEach(function (bill) {
        uh += '<div class="d-flex justify-content-between mb-1">' +
          '<span class="text-muted">' + esc(bill.month) + '</span>' +
          '<span class="font-weight-bold">&#x20B1;' + money(bill.amount) + '</span></div>';
        if (bill.penalty > 0) {
          uh += '<div class="d-flex justify-content-between mb-2">' +
            '<span class="text-muted penalty-label">+ Late Penalty</span>' +
            '<span class="font-weight-bold penalty-amount">+ &#x20B1;' + money(bill.penalty) + '</span></div>';
        }
      });
    } else if (billing.original_water_bill > 0) {
      showPaidRow = true;
      showPaidCheck = true;
      text('paid-status-amount').innerHTML = '&#x20B1;' + money(billing.original_water_bill);
    } else {
      showNoBills = true;
    }
    unpaidWrap.innerHTML = uh;

    show(text('paid-status-row'), showPaidRow);
    show(text('paid-status-check'), showPaidCheck);
    show(text('no-bills'), showNoBills);

    var carryoverRow = text('carryover-row');
    if (billing.cumulative_balance !== 0) {
      carryoverRow.classList.remove('d-none');
      var amountEl = text('carryover-amount');
      amountEl.textContent = '';
      if (billing.cumulative_balance > 0) {
        amountEl.className = 'font-weight-bold carryover-positive';
        amountEl.textContent = '\u2212 \u20B1' + money(billing.carryover);
      } else {
        amountEl.className = 'font-weight-bold carryover-negative';
        amountEl.textContent = '+ \u20B1' + money(billing.carryover);
      }
    } else {
      carryoverRow.classList.add('d-none');
    }

    text('total-due').textContent = '\u20B1' + money(billing.total_due);

    var dueDate = text('due-date');
    if (billing.due_date) {
      var days = billing.days_remaining;
      dueDate.textContent = 'Due in ' + days + ' day' + (days === 1 ? '' : 's') + ' (' + billing.due_date + ')';
      dueDate.classList.remove('d-none');
    } else {
      dueDate.classList.add('d-none');
    }

    show(text('pending-notice'), !!billing.pending_xendit);
  }

  function renderMap(customer) {
    var el = document.getElementById('billing-map');
    if (!el || !customer.x_coordinate || !customer.y_coordinate) return;
    var map = L.map(el, {
      zoomControl: false,
      attributionControl: false,
      dragging: false,
      scrollWheelZoom: false,
      doubleClickZoom: false,
      touchZoom: ('ontouchstart' in window),
      keyboard: false,
    }).setView([customer.x_coordinate, customer.y_coordinate], 18);
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', { maxZoom: 19 }).addTo(map);
    L.marker([customer.x_coordinate, customer.y_coordinate]).addTo(map);
  }

  // ---------------------------------------------------------------------
  // Pay online modal
  // ---------------------------------------------------------------------

  var PAYMENT_GROUPS = [
    { name: 'Recommended', codes: ['gcash_ewallet', 'maya_ewallet', 'qrph', 'card_domestic'], expanded: true },
    { name: 'E-Wallets', codes: ['gcash_ewallet', 'maya_ewallet', 'grabfpay', 'shopeepay'] },
    { name: 'Cards', codes: ['card_domestic', 'card_international'] },
    { name: 'Direct Debit', codes: ['bpi_directdebit', 'ubp_directdebit', 'rcbc_directdebit'] },
    { name: 'Over-the-Counter', codes: ['7eleven_otc', 'cebuana_otc', 'ecpay_otc', 'lbc_otc', 'mlhuillier_otc', 'palawan_otc', 'robinsons_otc', 'sm_otc', 'ussc_otc'] },
    { name: 'Others', codes: ['online_banking', 'billease', 'virtual_account'] },
  ];

  function feeLabel(m) {
    var label = '';
    if (m.fee_percent) label += Number(m.fee_percent).toFixed(1) + '%';
    if (m.fee_minimum) label += ' (min \u20B1' + Number(m.fee_minimum).toFixed(0) + ')';
    if (m.fee_flat) label += '\u20B1' + Number(m.fee_flat).toFixed(0) + ' flat';
    if (m.xendit_fee && (m.fee_percent || m.fee_flat)) label += ' + ';
    if (m.xendit_fee) label += '\u20B1' + Number(m.xendit_fee).toFixed(0) + ' fee';
    if (!m.fee_percent && !m.fee_flat && !m.xendit_fee) label = 'No fee';
    return label;
  }

  function buildPaymentGroups(methods) {
    var byCode = {};
    (methods || []).forEach(function (m) { byCode[m.code] = m; });

    var wrap = text('payment-groups');
    var html = '';

    PAYMENT_GROUPS.forEach(function (group) {
      var options = [];
      group.codes.forEach(function (code) {
        var m = byCode[code];
        if (!m) return;
        options.push(
          '<div class="payment-option" data-method="' + esc(m.code) + '"' +
          ' data-fee-percent="' + (m.fee_percent || 0) + '"' +
          ' data-fee-flat="' + (m.fee_flat || 0) + '"' +
          ' data-fee-minimum="' + (m.fee_minimum || 0) + '"' +
          ' data-xendit-fee="' + (m.xendit_fee || 0) + '">' +
          '<div class="payment-radio"><div class="payment-radio-dot"></div></div>' +
          '<div class="payment-option-info">' +
          '<div class="payment-method-name">' + esc(m.label) + '</div>' +
          '<div class="payment-method-fee">' + esc(feeLabel(m)) + '</div>' +
          '</div></div>'
        );
      });
      if (!options.length) return;

      var expanded = !!group.expanded;
      html +=
        '<div class="payment-group mb-1">' +
        '<div class="payment-group-header' + (expanded ? ' expanded' : '') + '">' +
        '<span class="payment-group-name">' + esc(group.name) + '</span>' +
        '<i class="payment-group-icon fas ' + (expanded ? 'fa-chevron-up' : 'fa-chevron-down') + '"></i>' +
        '</div>' +
        '<div class="payment-group-body' + (expanded ? '' : ' d-none') + '">' +
        options.join('') +
        '</div></div>';
    });

    wrap.innerHTML = html;
  }

  function paymentGroups() {
    return document.querySelectorAll('#payment-groups .payment-group');
  }

  function toggleGroup(header) {
    var body = header.nextElementSibling;
    var isOpening = body.classList.contains('d-none');
    Array.prototype.forEach.call(document.querySelectorAll('.payment-group-body'), function (b) {
      b.classList.add('d-none');
      b.style.display = '';
    });
    Array.prototype.forEach.call(document.querySelectorAll('.payment-group-header'), function (h) {
      h.classList.remove('expanded');
    });
    Array.prototype.forEach.call(document.querySelectorAll('.payment-group-icon'), function (i) {
      i.classList.remove('fa-chevron-up');
      i.classList.add('fa-chevron-down');
    });
    if (isOpening) {
      body.classList.remove('d-none');
      header.classList.add('expanded');
      var icon = header.querySelector('.payment-group-icon');
      icon.classList.remove('fa-chevron-down');
      icon.classList.add('fa-chevron-up');
    }
  }

  function selectPaymentMethod(el) {
    Array.prototype.forEach.call(document.querySelectorAll('.payment-option'), function (o) {
      o.classList.remove('selected');
    });
    el.classList.add('selected');
    var ds = el.dataset;
    selectedMethod = ds.method;

    var feePercent = parseFloat(ds.feePercent) || 0;
    var feeFlat = parseFloat(ds.feeFlat) || 0;
    var feeMin = parseFloat(ds.feeMinimum) || 0;
    var xenditFee = parseFloat(ds.xenditFee) || 0;

    var feeAmount = Math.round(BASE_AMOUNT * feePercent) / 100 + feeFlat;
    if (feeMin > 0 && feeAmount < feeMin) feeAmount = feeMin;
    feeAmount = Math.round(feeAmount * 100) / 100;
    var convenienceFee = feeAmount + xenditFee;
    var totalWithFee = BASE_AMOUNT + convenienceFee;

    text('convenience-fee-display').textContent = convenienceFee.toFixed(2);
    text('total-with-fee').textContent = totalWithFee.toFixed(2);
    text('fee-breakdown').classList.remove('d-none');
    text('pay-amount-btn').textContent = totalWithFee.toFixed(2);
    text('pay-now-btn').disabled = false;
  }

  function resetModal() {
    selectedMethod = null;
    text('pay-now-btn').disabled = true;
    text('fee-breakdown').classList.add('d-none');
    Array.prototype.forEach.call(document.querySelectorAll('.payment-option'), function (o) {
      o.classList.remove('selected');
    });
    Array.prototype.forEach.call(paymentGroups(), function (g) {
      var nameEl = g.querySelector('.payment-group-name');
      var isExpanded = nameEl && nameEl.textContent.trim() === 'Recommended';
      var body = g.querySelector('.payment-group-body');
      body.classList.toggle('d-none', !isExpanded);
      body.style.display = '';
      var icon = g.querySelector('.payment-group-icon');
      if (icon) {
        icon.classList.toggle('fa-chevron-down', !isExpanded);
        icon.classList.toggle('fa-chevron-up', isExpanded);
      }
    });
    text('pay-online-error').classList.add('d-none');
    text('pay-online-success').classList.add('d-none');
    text('pay-online-loading').classList.add('d-none');
    text('pay-online-form').classList.remove('d-none');
    text('pay-amount-btn').textContent = BASE_AMOUNT.toFixed(2);
  }

  window.retryPayment = function () {
    resetModal();
  };

  function initPayModal(billing) {
    BASE_AMOUNT = Number(billing.total_due) || 0;
    text('pay-amount').textContent = BASE_AMOUNT.toFixed(2);
    text('pay-success-amount').textContent = BASE_AMOUNT.toFixed(2);
    text('pay-amount-btn').textContent = BASE_AMOUNT.toFixed(2);
    buildPaymentGroups(billing.payment_methods);

    var wrap = text('payment-groups');
    wrap.addEventListener('click', function (e) {
      var header = e.target.closest('.payment-group-header');
      if (header) { toggleGroup(header); return; }
      var option = e.target.closest('.payment-option');
      if (option) { selectPaymentMethod(option); }
    });

    var modal = text('payOnlineModal');
    if (modal) modal.removeEventListener('hidden.bs.modal', resetModal);
    if (modal) modal.addEventListener('hidden.bs.modal', resetModal);
  }

  text('pay-now-btn').addEventListener('click', function () {
    if (!selectedMethod) return;

    text('pay-online-form').classList.add('d-none');
    text('pay-online-loading').classList.remove('d-none');

    fetch('/customer/api/invoice', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'same-origin',
      body: JSON.stringify({
        amount: BASE_AMOUNT,
        payment_method: selectedMethod,
        success_url: window.location.href,
        cancel_url: window.location.href,
      }),
    })
      .then(function (r) {
        return r.json().catch(function () { return {}; }).then(function (data) {
          if (!r.ok) { throw new Error((data && data.error) || 'Payment failed.'); }
          return data;
        });
      })
      .then(function (data) {
        if (data.redirect_url) window.location.href = data.redirect_url;
      })
      .catch(function (err) {
        text('pay-online-loading').classList.add('d-none');
        text('pay-online-error-msg').textContent = (err && err.message) || 'Payment failed. Please try again.';
        text('pay-online-error').classList.remove('d-none');
      });
  });

  // ---------------------------------------------------------------------
  // Paginated history tables
  // ---------------------------------------------------------------------

  function renderPagination(container, current, total, cb) {
    var ul = typeof container === 'string' ? document.querySelector(container) : container;
    if (!ul) return;
    ul.innerHTML = '';
    if (total <= 1) {
      ul.style.display = 'none';
      return;
    }
    ul.style.display = '';

    function item(label, page, opts) {
      opts = opts || {};
      var li = document.createElement('li');
      li.className = 'page-item' + (opts.disabled ? ' disabled' : '') + (opts.active ? ' active' : '');
      var a = document.createElement('a');
      a.className = 'page-link';
      a.href = '#';
      a.innerHTML = label;
      if (!opts.disabled && page != null) {
        a.addEventListener('click', function (e) { e.preventDefault(); cb(page); });
      }
      li.appendChild(a);
      return li;
    }

    ul.appendChild(item('&laquo;', current > 1 ? current - 1 : null, { disabled: current === 1 }));
    for (var i = Math.max(1, current - 2); i <= Math.min(total, current + 2); i++) {
      ul.appendChild(item(String(i), i, { active: i === current }));
    }
    ul.appendChild(item('&raquo;', current < total ? current + 1 : null, { disabled: current === total }));
  }

  function loadPayments(page) {
    getJSON('/customer/api/payments?page=' + page).then(function (data) {
      var tbody = document.querySelector('#payment-history-table tbody');
      var h = '';
      if (!data.items.length) {
        h = '<tr><td colspan="3" class="text-muted text-center">No payments</td></tr>';
      } else {
        data.items.forEach(function (item) {
          h += '<tr><td>' + esc(item.receipt_number) + '</td><td>&#x20B1;' +
            money(item.paid_amount) + '</td><td>' + esc(fmtDate(item.timestamp)) + '</td></tr>';
        });
      }
      tbody.innerHTML = h;
      renderPagination('#payment-pagination', data.page, data.pages, loadPayments);
    });
  }

  function loadReadings(page) {
    getJSON('/customer/api/readings?page=' + page).then(function (data) {
      var tbody = document.querySelector('#reading-history-table tbody');
      var h = '';
      if (!data.items.length) {
        h = '<tr><td colspan="3" class="text-muted text-center">No readings</td></tr>';
      } else {
        data.items.forEach(function (item) {
          h += '<tr><td>' + esc(item.reading_value) + '</td><td>' + esc(item.reader || '\u2014') +
            '</td><td>' + esc(fmtDate(item.timestamp)) + '</td></tr>';
        });
      }
      tbody.innerHTML = h;
      renderPagination('#reading-pagination', data.page, data.pages, loadReadings);
    });
  }

  function loadBillingHistory(page) {
    getJSON('/customer/api/history?page=' + page).then(function (data) {
      var tbody = document.querySelector('#billing-history-table tbody');
      var h = '';
      if (!data.items.length) {
        h = '<tr><td colspan="5" class="text-muted text-center">No billing history</td></tr>';
      } else {
        data.items.forEach(function (item) {
          var paid = item.paid_amount !== null && item.paid_amount !== undefined
            ? '&#x20B1;' + money(item.paid_amount)
            : '<span style="color:#dc3545;">Unpaid</span>';
          var penaltyDisplay = item.penalty > 0 ? '&#x20B1;' + money(item.penalty) : '';
          h +=
            '<tr>' +
            '<td>' + esc(item.month) + '</td>' +
            '<td>' + money(item.usage) + ' m&sup3;</td>' +
            '<td>&#x20B1;' + money(item.billed_amount) + '</td>' +
            '<td>' + penaltyDisplay + '</td>' +
            '<td>' + paid + '</td>' +
            '</tr>';
        });
      }
      tbody.innerHTML = h;
      renderPagination('#billing-history-pagination', data.page, data.pages, loadBillingHistory);
    });
  }

  // ---------------------------------------------------------------------
  // Boot
  // ---------------------------------------------------------------------

  function showContextError(msg) {
    var box = document.getElementById('context-error');
    var msgEl = document.getElementById('context-error-msg');
    if (box && msgEl) {
      msgEl.textContent = msg;
      box.classList.remove('d-none');
    }
  }

  function readEnvelopeError(data, status) {
    if (!data) return 'Unable to load billing data (HTTP ' + status + ').';
    var err = data.error;
    var msg = (typeof err === 'string' && err)
      || (err && err.message)
      || data.detail
      || 'Unable to load billing data.';
    if (err && err.code) { msg += ' (' + err.code + ')'; }
    else if (data.error_code) { msg += ' (' + data.error_code + ')'; }
    if (err && err.request_id) { msg += ' [' + err.request_id + ']'; }
    return msg;
  }

  function boot() {
    fetch('/customer/api/context', { credentials: 'same-origin' })
      .then(function (resp) {
        if (resp.status === 401) {
          window.location.href = '/customer/login';
          return null;
        }
        return resp.text().then(function (body) {
          var data;
          try { data = body ? JSON.parse(body) : null; } catch (e) { data = null; }
          if (!resp.ok) throw new Error(readEnvelopeError(data, resp.status));
          return data;
        });
      })
      .then(function (data) {
        if (!data) return;
        state = data;
        var customer = data.customer || {};
        var billing = data.billing || {};

        renderCustomer(customer);
        renderReadings(billing);
        renderPricing(billing);
        renderBillSummary(billing);
        renderMap(customer);
        initPayModal(billing);

        loadPayments(1);
        loadReadings(1);
        loadBillingHistory(1);
      })
      .catch(function (err) {
        console.error('Failed to load billing context:', err);
        showContextError(err && err.message ? err.message : 'Unable to load billing data.');
      });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', boot);
  } else {
    boot();
  }
})();
