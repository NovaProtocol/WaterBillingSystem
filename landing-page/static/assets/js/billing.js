$(function() {
  if (CUST_LAT && CUST_LNG) {
    var el = document.getElementById('billing-map');
    if (el) {
      var map = L.map(el, { zoomControl: false, attributionControl: false, dragging: false, scrollWheelZoom: false, doubleClickZoom: false, touchZoom: ('ontouchstart' in window), keyboard: false }).setView([CUST_LAT, CUST_LNG], 18);
      L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', { maxZoom: 19 }).addTo(map);
      L.marker([CUST_LAT, CUST_LNG]).addTo(map);
    }
  }

  function loadPayments(page) {
    $.getJSON(BILLING_API_PAYMENTS_URL.replace('0', CUST_NUM) + '?page=' + page + '&per_page=10', function (data) {
      var tbody = $('#payment-history-table tbody');
      tbody.empty();
      if (data.items.length === 0) {
        tbody.append('<tr><td colspan="3" class="text-muted text-center">No payments</td></tr>');
      } else {
        $.each(data.items, function (i, item) {
          var d = new Date(item.timestamp * 1000);
          tbody.append('<tr><td>' + item.receipt_number + '</td><td>' + item.paid_amount.toFixed(2) + '</td><td>' + d.toLocaleDateString() + '</td></tr>');
        });
      }
      renderPagination('#payment-pagination', data.page, data.pages, loadPayments);
    });
  }

  function loadReadings(page) {
    $.getJSON(BILLING_API_READINGS_URL.replace('0', CUST_NUM) + '?page=' + page + '&per_page=10', function (data) {
      var tbody = $('#reading-history-table tbody');
      tbody.empty();
      if (data.items.length === 0) {
        tbody.append('<tr><td colspan="3" class="text-muted text-center">No readings</td></tr>');
      } else {
        $.each(data.items, function (i, item) {
          var d = new Date(item.timestamp * 1000);
          tbody.append('<tr><td>' + item.reading_value + '</td><td>' + (item.reader || '—') + '</td><td>' + d.toLocaleDateString() + '</td></tr>');
        });
      }
      renderPagination('#reading-pagination', data.page, data.pages, loadReadings);
    });
  }

  loadPayments(1);
  loadReadings(1);
  loadBillingHistory(1);

  function loadBillingHistory(page) {
    $.getJSON(BILLING_API_HISTORY_URL.replace('0', CUST_NUM) + '?page=' + page + '&per_page=12', function (data) {
      var tbody = $('#billing-history-table tbody');
      tbody.empty();
      if (data.items.length === 0) {
        tbody.append('<tr><td colspan="5" class="text-muted text-center">No billing history</td></tr>');
      } else {
        $.each(data.items, function (i, item) {
          var paid = item.paid_amount !== null ? '&#x20B1;' + item.paid_amount.toFixed(2) : '<span style="color:#dc3545;">Unpaid</span>';
          var penaltyDisplay = item.penalty > 0 ? '&#x20B1;' + item.penalty.toFixed(2) : '';
          tbody.append(
            '<tr>' +
              '<td>' + item.month + '</td>' +
              '<td>' + item.usage.toFixed(2) + ' m&sup3;</td>' +
              '<td>&#x20B1;' + item.billed_amount.toFixed(2) + '</td>' +
              '<td>' + penaltyDisplay + '</td>' +
              '<td>' + paid + '</td>' +
            '</tr>'
          );
        });
      }
      renderPagination('#billing-history-pagination', data.page, data.pages, loadBillingHistory);
    });
  }
});
