(function () {
  'use strict';

  var readingItems = [], readingPage = 1, perPage = 10;

  customerAutocomplete('#customerSearch', '#customerDropdown', function (num) {
    document.getElementById('customerSearch').value = num;
    loadReadings(num);
  });

  function renderReadingPage() {
    var tbody = document.getElementById('readingTableBody');
    var start = (readingPage - 1) * perPage;
    var page = readingItems.slice(start, start + perPage);
    var now = new Date();
    var currentYear = now.getFullYear(), currentMonth = now.getMonth();
    var h = '';
    page.forEach(function (item) {
      var d = new Date(item.timestamp * 1000);
      var dateStr = d.toLocaleDateString() + ' ' + d.toLocaleTimeString();
      var locked = (d.getFullYear() < currentYear) || (d.getFullYear() === currentYear && d.getMonth() < currentMonth);
      var paid = item.status === 'Paid';
      var dropDisabled = locked || paid;
      var editBtn = locked
        ? '<button class="btn btn-outline-sm me-1" disabled style="opacity:0.35"><i class="fas fa-edit"></i></button>'
        : '<button class="btn btn-outline-sm edit-reading me-1" data-id="' + item.id + '" data-value="' + item.reading_value + '"><i class="fas fa-edit"></i></button>';
      var dropTitle = paid ? 'Bill already paid, undo payment first' : (locked ? 'Previous billing cycle' : '');
      var dropBtn = dropDisabled
        ? '<button class="btn btn-outline-sm" disabled style="opacity:0.35;border-color:#dc3545;color:#dc3545;" title="' + dropTitle + '"><i class="fas fa-trash"></i></button>'
        : '<button class="btn btn-outline-sm drop-reading" data-id="' + item.id + '" style="border-color:#dc3545;color:#dc3545;"><i class="fas fa-trash"></i></button>';
      h += '<tr>' +
        '<td>' + item.id + '</td>' +
        '<td>' + ((item.reading_value != null) ? item.reading_value : ' - ') + '</td>' +
        '<td>' + (item.consumption || '0') + '</td>' +
        '<td>' + dateStr + '</td>' +
        '<td>' + editBtn + dropBtn + '</td>' +
        '</tr>';
    });
    tbody.innerHTML = h;
    var totalPages = Math.ceil(readingItems.length / perPage) || 1;
    document.getElementById('readingPageInfo').textContent = 'Page ' + readingPage + ' of ' + totalPages + ' (' + readingItems.length + ' total)';
    renderPagination('#readingPagination', readingPage, totalPages, function (p) { readingPage = p; renderReadingPage(); });
  }

  function loadReadings(custNum) {
    fetch(API_CUSTOMER_URL.replace('0', encodeURIComponent(custNum)))
      .then(function (r) { return r.json(); })
      .then(function (data) {
        if (data.error) { alert(data.error); return; }
        document.getElementById('mgmtCustNum').textContent = custNum;
        readingItems = (data.billing_items || data.readings || []).slice();
        readingPage = 1;
        if (!document.getElementById('customerInfo')) {
          document.querySelector('#readingList .card-header').insertAdjacentHTML('afterend', '<div id="customerInfo"></div>');
        }
        document.getElementById('customerInfo').innerHTML = buildCustomerInfoCard(data);
        renderReadingPage();
        document.getElementById('readingList').style.display = '';
      })
      .catch(function (err) { alert('Failed to load readings: ' + (err && err.message ? err.message : 'Unknown')); });
  }

  document.addEventListener('click', function (e) {
    var editBtn = e.target.closest('.edit-reading');
    if (editBtn) {
      document.getElementById('editReadingId').value = editBtn.dataset.id;
      document.getElementById('editOldValue').value = editBtn.dataset.value;
      document.getElementById('editNewValue').value = editBtn.dataset.value;
      bootstrap.Modal.getOrCreateInstance(document.getElementById('editReadingModal')).show();
      return;
    }
    var dropBtn = e.target.closest('.drop-reading');
    if (dropBtn) {
      document.getElementById('dropReadingId').value = dropBtn.dataset.id;
      document.getElementById('dropReadingReason').value = '';
      bootstrap.Modal.getOrCreateInstance(document.getElementById('dropReadingModal')).show();
    }
  });

  document.getElementById('editReadingForm').addEventListener('submit', function (e) {
    e.preventDefault();
    var id = document.getElementById('editReadingId').value;
    var value = parseFloat(document.getElementById('editNewValue').value);
    postJSON(EDIT_READING_URL_BASE.replace('0', id), { reading_value: value })
      .then(function () {
        bootstrap.Modal.getOrCreateInstance(document.getElementById('editReadingModal')).hide();
        alert('Reading updated');
        location.reload();
      })
      .catch(handleError);
  });

  document.getElementById('dropReadingForm').addEventListener('submit', function (e) {
    e.preventDefault();
    var id = document.getElementById('dropReadingId').value;
    var reason = document.getElementById('dropReadingReason').value;
    if (!reason) { alert('Reason is required'); return; }
    if (!confirm('Are you sure? This cannot be undone.')) return;
    postJSON(DROP_READING_URL_BASE.replace('0', id), { reason: reason })
      .then(function () {
        bootstrap.Modal.getOrCreateInstance(document.getElementById('dropReadingModal')).hide();
        alert('Reading dropped');
        location.reload();
      })
      .catch(handleError);
  });
})();
