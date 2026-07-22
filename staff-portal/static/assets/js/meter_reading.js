$(function() {
  $('#generateKeyForm').on('submit', function(e) {
    e.preventDefault();
    var btn = $(this).find('button[type=submit]');
    btn.prop('disabled', true).html('<i class="fas fa-spinner fa-spin mr-1"></i>Generating...');
    var label = $('#keyLabel').val().trim();
    $.ajax({
      url: GENERATE_KEY_URL,
      method: 'POST',
      contentType: 'application/json',
      data: JSON.stringify({label: label || ''}),
      success: function(resp) {
        $('#generateKeyModal').modal('hide');
        $('#generatedKey').val(resp.key);
        $('#qrcode').empty();
        new QRCode(document.getElementById('qrcode'), { text: resp.key, width: 180, height: 180 });
        $('#keyResultModal').modal('show');
        $('#generateKeyForm')[0].reset();
        btn.prop('disabled', false).text('Generate');

        var now = new Date();
        var dateStr = now.getFullYear() + '-' + String(now.getMonth()+1).padStart(2,'0') + '-' + String(now.getDate()).padStart(2,'0') + 'T' + String(now.getHours()).padStart(2,'0') + ':' + String(now.getMinutes()).padStart(2,'0');
        var row = '<tr>' +
          '<td><div class="input-group input-group-sm input-group-sm-nofold mw-260px">' +
          '<input type="password" class="form-control form-control-sm-cotta key-input form-control-monospace" value="' + resp.key + '" readonly data-full="' + resp.key + '">' +
          '<div class="input-group-append">' +
          '<button class="btn btn-outline-sm toggle-key" type="button" title="Toggle visibility"><i class="fas fa-eye"></i></button>' +
          '<button class="btn btn-outline-sm qr-key" type="button" data-key="' + resp.key + '" title="Show QR"><i class="fas fa-qrcode"></i></button>' +
          '</div></div></td>' +
          '<td>' + (resp.label || '\u2014') + '</td>' +
          '<td><span class="badge badge-success">Active</span></td>' +
          '<td>' + dateStr + '</td>' +
          '<td><button class="btn btn-outline-sm revoke-key" data-id="' + resp.id + '" title="Revoke"><i class="fas fa-trash"></i></button></td>' +
          '</tr>';
        if ($('#keysTable tbody tr').length === 0) {
          $('#keysTable tbody').append(row);
          $('#noKeysMessage').hide();
          $('#keysTable').show();
        } else {
          $('#keysTable tbody').prepend(row);
        }
      },
      error: function(xhr) {
        btn.prop('disabled', false).text('Generate');
        var errMsg = xhr.responseJSON?.error || xhr.statusText || 'unknown';
        console.error('Generate key failed:', xhr.responseText, xhr.status);
        alert('Failed to generate key: ' + errMsg);
      }
    });
  });

  $(document).on('click', '.toggle-key', function() {
    var input = $(this).closest('.input-group').find('.key-input');
    var icon = $(this).find('i');
    if (input.attr('type') === 'password') {
      input.attr('type', 'text');
      icon.removeClass('fa-eye').addClass('fa-eye-slash');
    } else {
      input.attr('type', 'password');
      icon.removeClass('fa-eye-slash').addClass('fa-eye');
    }
  });

  $(document).on('click', '#copyKeyBtn', function() {
    var key = $('#generatedKey').val();
    navigator.clipboard.writeText(key).then(function() {
      var icon = $('#copyKeyBtn').find('i');
      icon.removeClass('fa-copy').addClass('fa-check');
      setTimeout(function() { icon.removeClass('fa-check').addClass('fa-copy'); }, 2000);
    });
  });

  $(document).on('click', '.qr-key', function() {
    var key = $(this).data('key');
    $('#generatedKey').val(key);
    $('#qrcode').empty();
    new QRCode(document.getElementById('qrcode'), { text: key, width: 180, height: 180 });
    $('#keyResultModal').modal('show');
  });

  $(document).on('click', '.revoke-key', function() {
    var id = $(this).data('id');
    if (!confirm('Revoke this API key? This cannot be undone.')) return;
    var btn = $(this);
    var row = btn.closest('tr');
    $.ajax({
      url: REVOKE_KEY_URL_BASE.replace('0', id),
      method: 'POST',
      success: function() {
        row.find('.badge').removeClass('badge-success').addClass('badge-secondary').text('Revoked');
        row.find('.revoke-key').remove();
        row.addClass('revoked-row');
        if ($('#hideRevoked').is(':checked')) {
          row.hide();
        }
      },
      error: function(xhr) {
        alert('Failed to revoke key: ' + (xhr.responseJSON?.error || xhr.statusText));
      }
    });
  });

  $('#hideRevoked').on('change', function() {
    if ($(this).is(':checked')) {
      $('.revoked-row').hide();
    } else {
      $('.revoked-row').show();
    }
  });

  if ($('#hideRevoked').is(':checked')) {
    $('.revoked-row').hide();
  }
});
