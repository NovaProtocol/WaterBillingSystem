$(function() {
  var billingItems = [], billingPage = 1, perPage = 10;

  customerAutocomplete('#customerSearch', '#customerDropdown', function(num) {
    $('#customerSearch').val(num);
    loadCustomer(num);
  });

  function loadCustomer(custNum) {
    $.get(API_CUSTOMER_URL.replace('0', encodeURIComponent(custNum)))
      .done(function(data) {
      if (data.error) { alert(data.error); return; }

      $('#custNumLabel').text('#' + custNum);
      $('#infoCustNum').text(data.customer_number);
      $('#infoName').text(data.name || '—');
      $('#infoAddress').text(data.address || '—');
      $('#infoContact').text(data.contact_number || '—');
      $('#infoEmail').text(data.email || '—');

      if (data.latest_reading) {
        $('#currentReading').text(data.latest_reading.reading_value + ' m\u00B3');
        $('#currentReader').text(data.latest_reading.reader || '—');
        var cd = new Date(data.latest_reading.timestamp * 1000);
        $('#currentDate').text(cd.toLocaleDateString() + ' ' + cd.toLocaleTimeString());
      } else {
        $('#currentReading').text('—');
        $('#currentReader').text('');
        $('#currentDate').text('');
      }
      if (data.last_reading) {
        $('#prevReading').text(data.last_reading.reading_value + ' m\u00B3');
        $('#prevReader').text('Recorded by: ' + (data.last_reading.reader || 'Unknown'));
        var pd = new Date(data.last_reading.timestamp * 1000);
        $('#prevDate').text(pd.toLocaleDateString() + ' ' + pd.toLocaleTimeString());
      } else {
        $('#prevReading').text('—');
        $('#prevReader').text('No previous reading');
        $('#prevDate').text('');
      }

      var _cons = (data.consumption != null && isFinite(data.consumption)) ? Number(data.consumption) : 0;
      $('#consumptionLabel').text(_cons.toFixed(1) + ' m\u00B3');
      var tierBody = $('#tierTable tbody'); tierBody.empty();
      (data.bill_breakdown || []).forEach(function(tier) {
        var _u = (tier.units != null && isFinite(tier.units)) ? Number(tier.units) : 0;
        var _c = (tier.charge != null && isFinite(tier.charge)) ? Number(tier.charge) : 0;
        tierBody.append(
          '<tr><td>' + (tier.label||'') + '</td><td>' + _u.toFixed(2) + '</td><td>₱' + _c.toFixed(2) + '</td></tr>'
        );
      });

      var ul = $('#unpaidBillsList'); ul.empty();
      var hasUnpaid = false;
      (data.unpaid_bills || []).forEach(function(b) {
        hasUnpaid = true;
        ul.append(
          '<div class="d-flex justify-content-between mb-1">' +
            '<span class="text-muted" style="font-size: 0.85rem;">' + b.month + '</span>' +
            '<span class="font-weight-bold" style="font-size: 0.85rem;">₱' + ((b.amount!=null&&isFinite(b.amount))?Number(b.amount):0).toFixed(2) + '</span>' +
          '</div>'
        );
        if (b.penalty > 0) {
          ul.append(
            '<div class="d-flex justify-content-between mb-2">' +
              '<span class="text-muted" style="font-size: 0.85rem; padding-left: 1.2rem;">+ Late Penalty</span>' +
              '<span class="font-weight-bold" style="font-size: 0.85rem; color: #dc3545;">+ ₱' + ((b.penalty!=null&&isFinite(b.penalty))?Number(b.penalty):0).toFixed(2) + '</span>' +
            '</div>'
          );
        }
      });
      if (!hasUnpaid) { ul.append('<p class="text-muted mb-1" style="font-size:0.85rem;">No unpaid bills</p>'); }

      if (data.carryover > 0) {
        $('#carryoverRow').show();
        var _co = (data.carryover!=null&&isFinite(data.carryover))?Number(data.carryover):0;
        $('#summaryCarryover').text('₱' + _co.toFixed(2));
      } else { $('#carryoverRow').hide(); }
      var _td = (data.total_due!=null&&isFinite(data.total_due))?Number(data.total_due):0;
      $('#summaryTotalDue').text('₱' + _td.toFixed(2));
      if (data.due_date) {
        $('#dueDateRow').show().html('Due in ' + data.days_remaining + ' days (' + data.due_date + ')');
      } else { $('#dueDateRow').hide(); }

      billingItems = data.billing_items || [];
      billingPage = 1;
      renderBillingPage();

      var phb = $('#paymentHistoryBody'); phb.empty();
      (data.recent_payments || []).forEach(function(p) {
        var pd = new Date(p.timestamp * 1000);
        var _pa = (p.paid_amount!=null&&isFinite(p.paid_amount))?Number(p.paid_amount):0;
        phb.append(
          '<tr><td>' + (p.receipt_number || 'N/A') + '</td><td>₱' + _pa.toFixed(2) + '</td><td>' + pd.toLocaleDateString() + '</td><td>' + (p.cashier || '—') + '</td></tr>'
        );
      });

      $('#billingInfo').show();
    }).fail(function(xhr){ var m=(xhr.responseJSON&&xhr.responseJSON.error)||xhr.statusText||'Unknown'; alert('Failed to load customer: '+m); });
  }

  function renderBillingPage() {
    var tbody = $('#billingTableBody'); tbody.empty();
    var start = (billingPage - 1) * perPage;
    var page = billingItems.slice(start, start + perPage);
    page.forEach(function(item) {
      var dt = new Date(item.timestamp * 1000);
      var period = dt.toLocaleDateString('en-US', { month: 'long', year: 'numeric' });
      var reading = (item.reading_value!=null&&isFinite(item.reading_value))?Number(item.reading_value):0;
      var consumption = (item.consumption!=null&&isFinite(item.consumption))?Number(item.consumption):0;
      var wb = (item.water_bill!=null&&isFinite(item.water_bill))?Number(item.water_bill):0;
      var penalty = (item.penalty!=null&&isFinite(item.penalty))?Number(item.penalty):0;
      var paid = (item.paid_amount!=null&&isFinite(item.paid_amount))?Number(item.paid_amount):0;
      var _co2 = (item.carryover_offset!=null&&isFinite(item.carryover_offset))?Number(item.carryover_offset):0;
      var status = item.status || 'Unpaid';

      var statusBadge = '<span class="badge badge-success">Paid</span>';
      var actions = '';
      if (status === 'Paid') {
        statusBadge = '<span class="badge badge-success">Paid</span>';
        actions = '<button class="btn btn-outline-sm undo-payment" data-id="' + item.billing_id + '" data-amount="' + paid + '" data-receipt="' + (item.receipt_number || '') + '" title="Undo payment"><i class="fas fa-undo"></i></button>';
      } else if (status === 'Unpaid') {
        statusBadge = '<span class="badge badge-warning">Unpaid</span>';
      } else {
        statusBadge = '<span class="badge badge-secondary">' + status + '</span>';
      }

      tbody.append(
        '<tr>' +
          '<td>' + period + '</td>' +
          '<td>' + reading.toFixed(1) + '</td>' +
          '<td>' + consumption.toFixed(1) + ' m\u00B3</td>' +
          '<td>₱' + wb.toFixed(2) + '</td>' +
          '<td>₱' + penalty.toFixed(2) + '</td>' +
          '<td>₱' + paid.toFixed(2) + '</td>' +
          '<td>' + (_co2 !== 0
  ? (_co2 < 0
    ? '<span style="color:#dc3545;">−₱' + Math.abs(_co2).toFixed(2) + '</span>'
    : '₱' + _co2.toFixed(2))
  : '—') + '</td>' +
          '<td>' + statusBadge + '</td>' +
          '<td>' + actions + '</td>' +
        '</tr>'
      );
    });

    var totalPages = Math.ceil(billingItems.length / perPage) || 1;
    $('#billingPageInfo').text('Page ' + billingPage + ' of ' + totalPages + ' (' + billingItems.length + ' total)');
    renderPagination('#billingPagination', billingPage, totalPages, function(p) { billingPage = p; renderBillingPage(); });
  }

  $(document).on('click', '.undo-payment', function() {
    var id = $(this).data('id');
    if (!id) { alert('No billing ID'); return; }
    $('#undoPaymentId').val(id);
    $('#undoReason').val('');
    $('#undoPaymentModal').modal('show');
  });

  $('#undoPaymentForm').on('submit', function(e) {
    e.preventDefault();
    var id = $('#undoPaymentId').val();
    var reason = $('#undoReason').val();
    if (!reason) { alert('Reason is required'); return; }
    if (!confirm('Undo this payment? The bill will be reverted to unpaid.')) return;
    $.ajax({
      url: UNDO_PAYMENT_URL_BASE.replace('0', id),
      method: 'POST',
      contentType: 'application/json',
      data: JSON.stringify({reason: reason}),
      success: function() { $('#undoPaymentModal').modal('hide'); location.reload(); },
      error: handleAjaxError
    });
  });
});
