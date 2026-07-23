$(function() {
  var readingItems = [], readingPage = 1, perPage = 10;

  customerAutocomplete('#customerSearch', '#customerDropdown', function(num) {
    $('#customerSearch').val(num);
    loadReadings(num);
  });

  function renderReadingPage() {
    var tbody = $('#readingTableBody'); tbody.empty();
    var start = (readingPage - 1) * perPage;
    var page = readingItems.slice(start, start + perPage);
    var now = new Date();
    var currentYear = now.getFullYear(), currentMonth = now.getMonth();
    page.forEach(function(item) {
      var d = new Date(item.timestamp * 1000);
      var dateStr = d.toLocaleDateString() + ' ' + d.toLocaleTimeString();
      var locked = (d.getFullYear() < currentYear) || (d.getFullYear() === currentYear && d.getMonth() < currentMonth);
      var paid = item.status === 'Paid';
      var dropDisabled = locked || paid;
      var editBtn = locked
        ? '<button class="btn btn-outline-sm mr-1" disabled style="opacity:0.35"><i class="fas fa-edit"></i></button>'
        : '<button class="btn btn-outline-sm edit-reading mr-1" data-id="'+item.id+'" data-value="'+item.reading_value+'"><i class="fas fa-edit"></i></button>';
      var dropTitle = paid ? 'Bill already paid — undo payment first' : (locked ? 'Previous billing cycle' : '');
      var dropBtn = dropDisabled
        ? '<button class="btn btn-outline-sm" disabled style="opacity:0.35;border-color:#dc3545;color:#dc3545;" title="'+dropTitle+'"><i class="fas fa-trash"></i></button>'
        : '<button class="btn btn-outline-sm drop-reading" data-id="'+item.id+'" style="border-color:#dc3545;color:#dc3545;"><i class="fas fa-trash"></i></button>';
      tbody.append(
        '<tr>' +
          '<td>'+item.id+'</td>' +
          '<td>'+item.reading_value+'</td>' +
          '<td>'+(item.consumption || '0')+'</td>' +
          '<td>'+dateStr+'</td>' +
          '<td>'+editBtn+dropBtn+'</td>' +
        '</tr>'
      );
    });
    var totalPages = Math.ceil(readingItems.length / perPage) || 1;
    $('#readingPageInfo').text('Page ' + readingPage + ' of ' + totalPages + ' (' + readingItems.length + ' total)');
    renderPagination('#readingPagination', readingPage, totalPages, function(p) { readingPage = p; renderReadingPage(); });
  }

  function loadReadings(custNum) {
    $.get(API_CUSTOMER_URL.replace('0', encodeURIComponent(custNum)), function(data) {
      if (data.error) { alert(data.error); return; }
      $('#mgmtCustNum').text(custNum);
      readingItems = (data.billing_items || data.readings || []).slice();
      readingPage = 1;
      if (!$('#customerInfo').length) {
        $('#readingList .card-header').after('<div id="customerInfo"></div>');
      }
      $('#customerInfo').html(buildCustomerInfoCard(data));
      renderReadingPage();
      $('#readingList').show();
    });
  }

  $(document).on('click', '.edit-reading', function() {
    $('#editReadingId').val($(this).data('id'));
    $('#editOldValue').val($(this).data('value'));
    $('#editNewValue').val($(this).data('value'));
    $('#editReadingModal').modal('show');
  });

  $('#editReadingForm').on('submit', function(e) {
    e.preventDefault();
    var id = $('#editReadingId').val();
    var value = parseFloat($('#editNewValue').val());
    $.ajax({
      url: EDIT_READING_URL_BASE.replace('0', id),
      method: 'POST',
      contentType: 'application/json',
      data: JSON.stringify({reading_value: value}),
      success: function() { $('#editReadingModal').modal('hide'); alert('Reading updated'); location.reload(); },
      error: handleAjaxError
    });
  });

  $(document).on('click', '.drop-reading', function() {
    $('#dropReadingId').val($(this).data('id'));
    $('#dropReadingReason').val('');
    $('#dropReadingModal').modal('show');
  });

  $('#dropReadingForm').on('submit', function(e) {
    e.preventDefault();
    var id = $('#dropReadingId').val();
    var reason = $('#dropReadingReason').val();
    if (!reason) { alert('Reason is required'); return; }
    if (!confirm('Are you sure? This cannot be undone.')) return;
    $.ajax({
      url: DROP_READING_URL_BASE.replace('0', id),
      method: 'POST',
      contentType: 'application/json',
      data: JSON.stringify({reason: reason}),
      success: function() { $('#dropReadingModal').modal('hide'); alert('Reading dropped'); location.reload(); },
      error: handleAjaxError
    });
  });
});
