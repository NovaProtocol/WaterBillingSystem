var sortBy = 'customer_number', sortDir = 'asc', currentPage = 1, searchQ = '';

function loadCustomers() {
  var url = CUSTOMERS_SEARCH_URL + '?q=' + encodeURIComponent(searchQ) + '&sort_by=' + sortBy + '&sort_dir=' + sortDir + '&page=' + currentPage + '&size=50';
  $.getJSON(url, function(data) {
    var tbody = $('#customerTableBody').empty();
    var customers = data.customers || [];
    if (!customers.length) {
      tbody.append('<tr><td colspan="7" class="text-muted text-center py-4">No customers found.</td></tr>');
    } else {
      customers.forEach(function(c) {
        var active = c.is_active !== false;
        var badge = active ? '<span class="badge badge-success badge-pill-cotta">Active</span>'
          : '<span class="badge badge-secondary badge-pill-cotta">Inactive</span>';
        var totalDue = (c.total_due || 0) > 0
          ? '<span class="total-due">&#x20B1;' + (c.total_due || 0).toFixed(2) + '</span>'
          : '<span class="text-muted">&#x20B1;0.00</span>';
        var phaseBlock = (c.phase || c.block || c.street)
          ? (c.phase ? '<span class="badge badge-light badge-phase">' + esc(c.phase) + '</span> ' : '')
          + (c.block ? '<span class="badge badge-light badge-phase">' + esc(c.block) + '</span> ' : '')
          + (c.street ? '<span class="badge badge-light badge-phase">' + esc(c.street) + '</span>' : '')
          : '<span class="text-muted table-font-xxs">\u2014</span>';

        tbody.append('<tr class="' + (active ? '' : 'table-light text-muted') + '">'
          + '<td class="cust-number">' + esc(c.customer_number) + '</td>'
          + '<td><div class="cust-name">' + esc(c.name || '\u2014') + '</div>'
          + (c.address ? '<div class="cust-address-sm">' + esc(c.address) + '</div>' : '') + '</td>'
          + '<td><div class="d-flex flex-wrap flex-gap-xs">' + phaseBlock + '</div></td>'
          + '<td class="table-font-xxs">' + esc(c.contact_number || '\u2014') + '</td>'
          + '<td class="text-right text-medium">' + totalDue + '</td>'
          + '<td class="text-center">' + badge + '</td>'
          + '<td class="text-center"><div class="d-flex flex-gap-xs justify-content-center">'
          + '<button class="btn btn-sm btn-table-action btn-table-edit edit-customer" data-id="' + c.id + '" data-number="' + esc(c.customer_number) + '" data-name="' + esc(c.name || '') + '" data-address="' + esc(c.address || '') + '" data-contact="' + esc(c.contact_number || '') + '" data-email="' + esc(c.email || '') + '" data-phase="' + esc(c.phase || '') + '" data-block="' + esc(c.block || '') + '" data-meter-sn="' + esc(c.meter_serial_number || '') + '" data-street="' + esc(c.street || '') + '" data-x="' + (c.x_coordinate || '') + '" data-y="' + (c.y_coordinate || '') + '" data-nfc-tag-id="' + esc(c.nfc_uid || '') + '" title="Edit"><i class="fas fa-pen mr-1"></i>Edit</button>'
          + '<button class="btn btn-sm btn-table-action ' + (active ? 'btn-table-deactivate' : 'btn-table-activate') + ' toggle-active" data-id="' + c.id + '" data-active="' + active + '" title="' + (active ? 'Deactivate' : 'Reactivate') + '"><i class="fas ' + (active ? 'fa-ban' : 'fa-check-circle') + ' mr-1"></i>' + (active ? 'Deactivate' : 'Reactivate') + '</button>'
          + '</div></td></tr>');
      });
    }
    var total = data.total || 0, pages = data.pages || 1;
    $('#totalCount').text(total);
    if (pages > 1) {
      $('#paginationFooter').show();
      $('#pageInfo').text('Page ' + data.page + ' of ' + pages + ' (' + total + ' total)');
      var ul = $('#paginationUl').empty();
      ul.append('<li class="page-item ' + (currentPage <= 1 ? 'disabled' : '') + '"><a class="page-link" href="#">\u00ab</a></li>');
      for (var p = Math.max(1, currentPage - 3); p <= Math.min(pages, currentPage + 3); p++) {
        (function(pg) {
          ul.append('<li class="page-item ' + (pg === currentPage ? 'active' : '') + '"><a class="page-link" href="#">' + pg + '</a></li>');
        })(p);
      }
      ul.append('<li class="page-item ' + (currentPage >= pages ? 'disabled' : '') + '"><a class="page-link" href="#">\u00bb</a></li>');
      ul.find('a').on('click', function(e) {
        e.preventDefault();
        var txt = $(this).text().trim();
        if (txt === '\u00ab' && currentPage > 1) { currentPage--; loadCustomers(); }
        else if (txt === '\u00bb' && currentPage < pages) { currentPage++; loadCustomers(); }
        else { var n = parseInt(txt); if (!isNaN(n)) { currentPage = n; loadCustomers(); } }
      });
    } else {
      $('#paginationFooter').hide();
    }
  });
}

function esc(s) { return $('<span>').text(s || '').html(); }

$(function() {
  loadCustomers();

  var searchTimer;
  $('#searchInput').on('input', function() {
    clearTimeout(searchTimer);
    searchTimer = setTimeout(function() {
      searchQ = $('#searchInput').val().trim();
      currentPage = 1;
      loadCustomers();
    }, 300);
  });

  $('#sortSelect').on('change', function() {
    sortBy = $(this).val();
    currentPage = 1;
    loadCustomers();
  });

  $('#sortDirBtn').on('click', function() {
    sortDir = sortDir === 'asc' ? 'desc' : 'asc';
    $(this).find('i').attr('class', 'fas fa-sort-amount-' + (sortDir === 'asc' ? 'up-alt' : 'down'));
    currentPage = 1;
    loadCustomers();
  });
});
