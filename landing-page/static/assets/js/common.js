var csrfToken = $('meta[name="csrf-token"]').attr('content');
$.ajaxSetup({
  beforeSend: function(xhr, settings) {
    if (!/^(GET|HEAD|OPTIONS|TRACE)$/i.test(settings.type) && !this.crossDomain) {
      xhr.setRequestHeader("X-CSRFToken", csrfToken);
    }
  }
});

function handleAjaxError(xhr) {
  alert('Error: ' + (xhr.responseJSON ? xhr.responseJSON.error : 'Unknown'));
}

function renderPagination(container, cp, tp, cb) {
  var ul = $(container).empty();
  if (tp <= 1) { ul.closest('nav').hide(); return; }
  ul.closest('nav').show();
  var p = $('<li class="page-item"><a class="page-link" href="#">&laquo;</a></li>');
  p.find('a').on('click', function(e) { e.preventDefault(); if (cp > 1) cb(cp - 1); });
  if (cp === 1) p.addClass('disabled');
  ul.append(p);
  for (var i = Math.max(1, cp - 2); i <= Math.min(tp, cp + 2); i++) {
    var l = $('<li class="page-item"><a class="page-link" href="#">' + i + '</a></li>');
    if (i === cp) l.addClass('active');
    l.find('a').on('click', (function(p) { return function(e) { e.preventDefault(); cb(p); }; })(i));
    ul.append(l);
  }
  var n = $('<li class="page-item"><a class="page-link" href="#">&raquo;</a></li>');
  n.find('a').on('click', function(e) { e.preventDefault(); if (cp < tp) cb(cp + 1); });
  if (cp === tp) n.addClass('disabled');
  ul.append(n);
}

function customerAutocomplete(inputId, dropdownId, onSelect) {
  var searchTimeout;
  $(inputId).on('input', function() {
    clearTimeout(searchTimeout);
    var q = $(this).val();
    if (q.length < 1) { $(dropdownId).hide(); return; }
    searchTimeout = setTimeout(function() {
      $.get(CUSTOMER_LOOKUP_URL, {q: q}, function(data) {
        var d = $(dropdownId); d.empty();
        if (!data || !data.length) { d.hide(); return; }
        data.forEach(function(c) {
          d.append('<div class="item" data-number="'+c.customer_number+'" data-name="'+$('<span>').text(c.name).html()+'"><strong>'+c.customer_number+'</strong> &mdash; '+$('<span>').text(c.name).html()+'<br><span class="sub">'+$('<span>').text(c.address||'').html()+'</span></div>');
        });
        d.show();
      });
    }, 250);
  });
  $(document).on('click', dropdownId + ' .item', function() {
    var num = $(this).data('number');
    var name = $(this).data('name');
    $(dropdownId).hide();
    onSelect(num, name);
  });
  $(document).on('click', function(e) {
    if (!$(e.target).closest(inputId).length && !$(e.target).closest(dropdownId).length) $(dropdownId).hide();
  });
}

function buildCustomerInfoCard(data) {
  var h = '<div class="card mb-3" style="border:1px solid #e9ecef;border-radius:12px;box-shadow:0 1px 4px rgba(0,0,0,0.04);">';
  h += '<div class="card-body p-3"><div class="row align-items-center">';
  h += '<div class="col-auto"><div style="width:44px;height:44px;border-radius:50%;background:linear-gradient(135deg,#e94560,#c0392b);display:flex;align-items:center;justify-content:center;color:#fff;font-weight:700;font-size:18px;">' + $('<span>').text((data.name || '?')[0].toUpperCase()).html() + '</div></div>';
  h += '<div class="col"><div style="font-weight:700;font-size:1.05rem;color:#1a1a2e;">' + $('<span>').text(data.name || 'Unknown').html() + '</div>';
  h += '<div style="font-size:0.82rem;color:#6c757d;"><i class="fas fa-hashtag mr-1" style="font-size:0.7rem;"></i>' + $('<span>').text(data.customer_number).html() + '</div></div>';
  h += '<div class="col-12 mt-2"><div class="row text-center">';
  if (data.phase) h += '<div class="col"><div style="font-size:0.7rem;color:#adb5bd;text-transform:uppercase;letter-spacing:0.3px;">Phase</div><div style="font-weight:600;font-size:0.9rem;color:#1a1a2e;">' + $('<span>').text(data.phase).html() + '</div></div>';
  if (data.block) h += '<div class="col"><div style="font-size:0.7rem;color:#adb5bd;text-transform:uppercase;letter-spacing:0.3px;">Block</div><div style="font-weight:600;font-size:0.9rem;color:#1a1a2e;">' + $('<span>').text(data.block).html() + '</div></div>';
  if (data.street) h += '<div class="col"><div style="font-size:0.7rem;color:#adb5bd;text-transform:uppercase;letter-spacing:0.3px;">Street</div><div style="font-weight:600;font-size:0.9rem;color:#1a1a2e;">' + $('<span>').text(data.street).html() + '</div></div>';
  h += '<div class="col"><div style="font-size:0.7rem;color:#adb5bd;text-transform:uppercase;letter-spacing:0.3px;">Contact</div><div style="font-weight:600;font-size:0.9rem;color:#1a1a2e;">' + ($('<span>').text(data.contact_number || '—').html()) + '</div></div>';
  h += '</div></div>';
  if (data.address) h += '<div class="col-12 mt-2"><div style="font-size:0.78rem;color:#6c757d;background:#f8f9fa;border-radius:8px;padding:6px 10px;"><i class="fas fa-map-pin mr-1" style="color:#e94560;"></i>' + $('<span>').text(data.address).html() + '</div></div>';
  h += '</div></div></div>';
  return h;
}
