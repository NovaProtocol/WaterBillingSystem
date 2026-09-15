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
    tbody.innerHTML = '';
    var tiers = billing.pricing_tiers || [];

    billing.bill_breakdown.forEach(function (item, i) {
      var tr = document.createElement('tr');
      if (item.units === 0) tr.className = 'breakdown-row-muted';
      else tr.className = 'breakdown-row';

      var tier = tiers[i] || {};
      var rate;
      if (tier.unit === 'flat') rate = '&#x20B1;' + money(tier.rate) + ' flat';
      else rate = '&#x20B1;' + money(tier.rate) + '/m\u00B3';

      tr.innerHTML =
        '<td>' + esc(item.label) + '</td>' +
        '<td>' + money(item.units) + ' m\u00B3</td>' +
        '<td>' + rate + '</td>' +
        '<td class="text-right font-weight-bold">&#x20B1;' + money(item.charge) + '</td>';
      tbody.appendChild(tr);
    });

    var totalTr = document.createElement('tr');
    totalTr.className = 'font-weight-bold breakdown-total';
    totalTr.innerHTML =
      '<td colspan="3">Total Water Bill</td>' +
      '<td class="text-right">&#x20B1;' + money(billing.original_water_bill) + '</td>';
    tbody.appendChild(totalTr);

    table.classList.remove('d-none');
  }

  function renderBillSummary(billing) {
    var unpaidWrap = text('unpaid-bills');
    unpaidWrap.innerHTML = '';
    var showPaidRow = false;
    var showPaidCheck = false;
    var showNoBills = false;

    if (billing.unpaid_bills && billing.unpaid_bills.length) {
      billing.unpaid_bills.forEach(function (bill) {
        var row = document.createElement('div');
        row.className = 'd-flex justify-content-between mb-1';
        row.innerHTML = '<span class="text-muted">' + esc(bill.month) + '</span>' +
          '<span class="font-weight-bold">&#x20B1;' + money(bill.amount) + '</span>';
        unpaidWrap.appendChild(row);
        if (bill.penalty > 0) {
          var pen = document.createElement('div');
          pen.className = 'd-flex justify-content-between mb-2';
          pen.innerHTML = '<span class="text-muted penalty-label">+ Late Penalty</span>' +
            '<span class="font-weight-bold penalty-amount">+ &#x20B1;' + money(bill.penalty) + '</span>';
          unpaidWrap.appendChild(pen);
        }
      });
    } else if (billing.original_water_bill > 0) {
      showPaidRow = true;
      showPaidCheck = true;
      text('paid-status-amount').innerHTML = '&#x20B1;' + money(billing.original_water_bill);
    } else {
      showNoBills = true;
    }

    text('paid-status-row').classList.toggle('d-none', !showPaidRow);
    text('paid-status-check').classList.toggle('d-none', !showPaidCheck);
    text('no-bills').classList.toggle('d-none', !showNoBills);

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

    text('pending-notice').classList.toggle('d-none', !billing.pending_xendit);
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
    (methods || []).forEach(function (m) {
      byCode[m.code] = m;
    });

    var wrap = $('#payment-groups');
    wrap.empty();

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
      wrap.append(
        '<div class="payment-group mb-1">' +
        '<div class="payment-group-header' + (expanded ? ' expanded' : '') + '">' +
        '<span class="payment-group-name">' + esc(group.name) + '</span>' +
        '<i class="payment-group-icon fas ' + (expanded ? 'fa-chevron-up' : 'fa-chevron-down') + '"></i>' +
        '</div>' +
        '<div class="payment-group-body' + (expanded ? '' : ' d-none') + '">' +
        options.join('') +
        '</div></div>'
      );
    });
  }

  function toggleGroup(header) {
    var body = $(header).next('.payment-group-body');
    var isOpening = body.hasClass('d-none');
    $('.payment-group-body').addClass('d-none').css('display', '');
    $('.payment-group-header').removeClass('expanded');
    $('.payment-group-icon').removeClass('fa-chevron-up').addClass('fa-chevron-down');
    if (isOpening) {
      body.removeClass('d-none');
      $(header).addClass('expanded');
      $(header).find('.payment-group-icon').removeClass('fa-chevron-down').addClass('fa-chevron-up');
    }
  }

  function selectPaymentMethod(el) {
    $('.payment-option').removeClass('selected');
    $(el).addClass('selected');
    selectedMethod = $(el).data('method');

    var feePercent = parseFloat($(el).data('fee-percent')) || 0;
    var feeFlat = parseFloat($(el).data('fee-flat')) || 0;
    var feeMin = parseFloat($(el).data('fee-minimum')) || 0;
    var xenditFee = parseFloat($(el).data('xendit-fee')) || 0;

    var feeAmount = Math.round(BASE_AMOUNT * feePercent) / 100 + feeFlat;
    if (feeMin > 0 && feeAmount < feeMin) feeAmount = feeMin;
    feeAmount = Math.round(feeAmount * 100) / 100;
    var convenienceFee = feeAmount + xenditFee;
    var totalWithFee = BASE_AMOUNT + convenienceFee;

    $('#convenience-fee-display').text(convenienceFee.toFixed(2));
    $('#total-with-fee').text(totalWithFee.toFixed(2));
    $('#fee-breakdown').removeClass('d-none');
    $('#pay-amount-btn').text(totalWithFee.toFixed(2));
    $('#pay-now-btn').prop('disabled', false);
  }

  function resetModal() {
    selectedMethod = null;
    $('#pay-now-btn').prop('disabled', true);
    $('#fee-breakdown').addClass('d-none');
    $('.payment-option').removeClass('selected');
    $('.payment-group-body').each(function () {
      var name = $(this).closest('.payment-group').find('.payment-group-name').text().trim();
      var isExpanded = name === 'Recommended';
      $(this).toggleClass('d-none', !isExpanded).css('display', '');
    });
    $('.payment-group-icon').each(function () {
      var name = $(this).closest('.payment-group').find('.payment-group-name').text().trim();
      var isExpanded = name === 'Recommended';
      $(this).toggleClass('fa-chevron-down', !isExpanded);
      $(this).toggleClass('fa-chevron-up', isExpanded);
    });
    $('#pay-online-error').addClass('d-none');
    $('#pay-online-success').addClass('d-none');
    $('#pay-online-loading').addClass('d-none');
    $('#pay-online-form').removeClass('d-none');
    $('#pay-amount-btn').text(BASE_AMOUNT.toFixed(2));
  }

  window.retryPayment = function () {
    resetModal();
  };

  function initPayModal(billing) {
    BASE_AMOUNT = Number(billing.total_due) || 0;
    $('#pay-amount').text(BASE_AMOUNT.toFixed(2));
    $('#pay-success-amount').text(BASE_AMOUNT.toFixed(2));
    $('#pay-amount-btn').text(BASE_AMOUNT.toFixed(2));
    buildPaymentGroups(billing.payment_methods);

    $('#payment-groups').off('click').on('click', '.payment-group-header', function () {
      toggleGroup(this);
    }).on('click', '.payment-option', function () {
      selectPaymentMethod(this);
    });

    $('#payOnlineModal').off('hidden.bs.modal').on('hidden.bs.modal', resetModal);
  }

  $('#pay-now-btn').on('click', function () {
    if (!selectedMethod) return;

    $('#pay-online-form').addClass('d-none');
    $('#pay-online-loading').removeClass('d-none');

    $.ajax({
      url: '/customer/api/invoice',
      method: 'POST',
      contentType: 'application/json',
      data: JSON.stringify({
        amount: BASE_AMOUNT,
        payment_method: selectedMethod,
        success_url: window.location.href,
        cancel_url: window.location.href,
      }),
      success: function (data) {
        if (data.redirect_url) window.location.href = data.redirect_url;
      },
      error: function (xhr) {
        $('#pay-online-loading').addClass('d-none');
        var msg = 'Payment failed. Please try again.';
        try { var r = JSON.parse(xhr.responseText); msg = r.error; } catch (e) {}
        $('#pay-online-error-msg').text(msg);
        $('#pay-online-error').removeClass('d-none');
      },
    });
  });

  // ---------------------------------------------------------------------
  // Paginated history tables
  // ---------------------------------------------------------------------

  function renderPagination(container, current, total, cb) {
    var ul = $(container).empty();
    if (total <= 1) {
      ul.hide();
      return;
    }
    ul.show();
    var prev = $('<li class="page-item"><a class="page-link" href="#">&laquo;</a></li>');
    prev.find('a').on('click', function (e) { e.preventDefault(); if (current > 1) cb(current - 1); });
    if (current === 1) prev.addClass('disabled');
    ul.append(prev);
    for (var i = Math.max(1, current - 2); i <= Math.min(total, current + 2); i++) {
      var li = $('<li class="page-item"><a class="page-link" href="#">' + i + '</a></li>');
      if (i === current) li.addClass('active');
      li.find('a').on('click', (function (p) {
        return function (e) { e.preventDefault(); cb(p); };
      })(i));
      ul.append(li);
    }
    var next = $('<li class="page-item"><a class="page-link" href="#">&raquo;</a></li>');
    next.find('a').on('click', function (e) { e.preventDefault(); if (current < total) cb(current + 1); });
    if (current === total) next.addClass('disabled');
    ul.append(next);
  }

  function loadPayments(page) {
    $.getJSON('/customer/api/payments?page=' + page, function (data) {
      var tbody = $('#payment-history-table tbody');
      tbody.empty();
      if (!data.items.length) {
        tbody.append('<tr><td colspan="3" class="text-muted text-center">No payments</td></tr>');
      } else {
        data.items.forEach(function (item) {
          tbody.append('<tr><td>' + esc(item.receipt_number) + '</td><td>&#x20B1;' +
            money(item.paid_amount) + '</td><td>' + esc(fmtDate(item.timestamp)) + '</td></tr>');
        });
      }
      renderPagination('#payment-pagination', data.page, data.pages, loadPayments);
    });
  }

  function loadReadings(page) {
    $.getJSON('/customer/api/readings?page=' + page, function (data) {
      var tbody = $('#reading-history-table tbody');
      tbody.empty();
      if (!data.items.length) {
        tbody.append('<tr><td colspan="3" class="text-muted text-center">No readings</td></tr>');
      } else {
        data.items.forEach(function (item) {
          tbody.append('<tr><td>' + esc(item.reading_value) + '</td><td>' + esc(item.reader || '\u2014') +
            '</td><td>' + esc(fmtDate(item.timestamp)) + '</td></tr>');
        });
      }
      renderPagination('#reading-pagination', data.page, data.pages, loadReadings);
    });
  }

  function loadBillingHistory(page) {
    $.getJSON('/customer/api/history?page=' + page, function (data) {
      var tbody = $('#billing-history-table tbody');
      tbody.empty();
      if (!data.items.length) {
        tbody.append('<tr><td colspan="5" class="text-muted text-center">No billing history</td></tr>');
      } else {
        data.items.forEach(function (item) {
          var paid = item.paid_amount !== null && item.paid_amount !== undefined
            ? '&#x20B1;' + money(item.paid_amount)
            : '<span style="color:#dc3545;">Unpaid</span>';
          var penaltyDisplay = item.penalty > 0 ? '&#x20B1;' + money(item.penalty) : '';
          tbody.append(
            '<tr>' +
            '<td>' + esc(item.month) + '</td>' +
            '<td>' + money(item.usage) + ' m&sup3;</td>' +
            '<td>&#x20B1;' + money(item.billed_amount) + '</td>' +
            '<td>' + penaltyDisplay + '</td>' +
            '<td>' + paid + '</td>' +
            '</tr>'
          );
        });
      }
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
        return resp.text().then(function (text) {
          var data;
          try { data = text ? JSON.parse(text) : null; } catch (e) { data = null; }
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
