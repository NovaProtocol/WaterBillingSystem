function esc(s) {
  var d = document.createElement('div');
  d.textContent = s == null ? '' : String(s);
  return d.innerHTML;
}

function handleError(err) {
  var msg = err && err.message ? err.message : 'Unknown';
  alert('Error: ' + msg);
}

function postJSON(url, body) {
  return fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body || {}),
  }).then(function (r) {
    return r.json()
      .catch(function () { return {}; })
      .then(function (data) {
        if (!r.ok) {
          var inner = data && data.error;
          var msg = (inner && (inner.message || inner)) || ('Request failed (' + r.status + ')');
          throw new Error(msg);
        }
        return data;
      });
  });
}

function renderPagination(container, cp, tp, cb) {
  var ul = typeof container === 'string' ? document.querySelector(container) : container;
  if (!ul) return;
  var nav = ul.closest('nav');
  ul.innerHTML = '';
  if (tp <= 1) {
    if (nav) nav.style.display = 'none';
    return;
  }
  if (nav) nav.style.display = '';

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

  ul.appendChild(item('&laquo;', cp > 1 ? cp - 1 : null, { disabled: cp === 1 }));
  for (var i = Math.max(1, cp - 2); i <= Math.min(tp, cp + 2); i++) {
    ul.appendChild(item(String(i), i, { active: i === cp }));
  }
  ul.appendChild(item('&raquo;', cp < tp ? cp + 1 : null, { disabled: cp === tp }));
}

function customerAutocomplete(inputId, dropdownId, onSelect) {
  var input = document.querySelector(inputId);
  var dropdown = document.querySelector(dropdownId);
  if (!input || !dropdown) return;
  var searchTimeout;

  input.addEventListener('input', function () {
    clearTimeout(searchTimeout);
    var q = input.value;
    if (q.length < 1) { dropdown.style.display = 'none'; return; }
    searchTimeout = setTimeout(function () {
      fetch(CUSTOMER_LOOKUP_URL + '?q=' + encodeURIComponent(q))
        .then(function (r) { return r.json(); })
        .then(function (data) {
          dropdown.innerHTML = '';
          input.classList.remove('is-invalid');
          if (data && data.error === 'mixed_input') {
            input.classList.add('is-invalid');
            dropdown.innerHTML = '<div class="item invalid-feedback d-block px-3 py-2 mb-0" style="font-size:0.82rem;">' + esc(data.message || 'Invalid search') + '</div>';
            dropdown.style.display = '';
            return;
          }
          if (!data || !data.length) { dropdown.style.display = 'none'; return; }
          var h = '';
          data.forEach(function (c) {
            h += '<div class="item" data-number="' + esc(c.customer_number) + '" data-name="' + esc(c.name) + '">'
              + '<strong>' + esc(c.customer_number) + '</strong> - ' + esc(c.name)
              + '<br><span class="sub">' + esc(c.address || '') + '</span></div>';
          });
          dropdown.innerHTML = h;
          dropdown.style.display = '';
        });
    }, 250);
  });

  dropdown.addEventListener('click', function (e) {
    var item = e.target.closest('.item');
    if (!item) return;
    dropdown.style.display = 'none';
    onSelect(item.dataset.number, item.dataset.name);
  });

  document.addEventListener('click', function (e) {
    if (!e.target.closest(inputId) && !e.target.closest(dropdownId)) dropdown.style.display = 'none';
  });
}

function buildCustomerInfoCard(data) {
  var h = '<div class="card mb-3" style="border:1px solid #e9ecef;border-radius:12px;box-shadow:0 1px 4px rgba(0,0,0,0.04);">';
  h += '<div class="card-body p-3"><div class="row align-items-center">';
  h += '<div class="col-auto"><div style="width:44px;height:44px;border-radius:50%;background:linear-gradient(135deg,#e94560,#c0392b);display:flex;align-items:center;justify-content:center;color:#fff;font-weight:700;font-size:18px;">' + esc((data.name || '?')[0].toUpperCase()) + '</div></div>';
  h += '<div class="col"><div style="font-weight:700;font-size:1.05rem;color:#1a1a2e;">' + esc(data.name || 'Unknown') + '</div>';
  h += '<div style="font-size:0.82rem;color:#6c757d;"><i class="fas fa-hashtag me-1" style="font-size:0.7rem;"></i>' + esc(data.customer_number) + '</div></div>';
  h += '<div class="col-12 mt-2"><div class="row text-center">';
  if (data.phase) h += '<div class="col"><div style="font-size:0.7rem;color:#adb5bd;text-transform:uppercase;letter-spacing:0.3px;">Phase</div><div style="font-weight:600;font-size:0.9rem;color:#1a1a2e;">' + esc(data.phase) + '</div></div>';
  if (data.block) h += '<div class="col"><div style="font-size:0.7rem;color:#adb5bd;text-transform:uppercase;letter-spacing:0.3px;">Block</div><div style="font-weight:600;font-size:0.9rem;color:#1a1a2e;">' + esc(data.block) + '</div></div>';
  if (data.street) h += '<div class="col"><div style="font-size:0.7rem;color:#adb5bd;text-transform:uppercase;letter-spacing:0.3px;">Street</div><div style="font-weight:600;font-size:0.9rem;color:#1a1a2e;">' + esc(data.street) + '</div></div>';
  h += '<div class="col"><div style="font-size:0.7rem;color:#adb5bd;text-transform:uppercase;letter-spacing:0.3px;">Contact</div><div style="font-weight:600;font-size:0.9rem;color:#1a1a2e;">' + esc(data.contact_number || ' - ') + '</div></div>';
  h += '</div></div>';
  if (data.address) h += '<div class="col-12 mt-2"><div style="font-size:0.78rem;color:#6c757d;background:#f8f9fa;border-radius:8px;padding:6px 10px;"><i class="fas fa-map-pin me-1" style="color:#e94560;"></i>' + esc(data.address) + '</div></div>';
  h += '</div></div></div>';
  return h;
}
