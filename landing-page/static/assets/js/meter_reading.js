$(function() {
    var qrInstance = null;

    function showQR(key) {
        $('#generatedKey').val(key);
        $('#keyResultModal').modal('show');
        if (qrInstance) {
            qrInstance.clear();
            qrInstance.makeCode(key);
        } else {
            qrInstance = new QRCode(document.getElementById('qrcode'), {
                text: key,
                width: 200,
                height: 200,
                colorDark: '#1a1a2e',
                colorLight: '#ffffff',
                correctLevel: QRCode.CorrectLevel.H
            });
        }
    }

    $('#generateKeyForm').on('submit', function(e) {
        e.preventDefault();
        var label = $('#keyLabel').val();
        $.ajax({
            url: GENERATE_KEY_URL,
            method: 'POST',
            contentType: 'application/json',
            data: JSON.stringify({label: label}),
            success: function(data) {
                $('#generateKeyModal').modal('hide');
                showQR(data.key);
            },
            error: function(xhr) {
                alert('Error: ' + (xhr.responseJSON ? xhr.responseJSON.error : 'Unknown'));
            }
        });
    });

    $('#copyKeyBtn').on('click', function() {
        var input = $('#generatedKey');
        input.select();
        document.execCommand('copy');
        $(this).html('<i class="fas fa-check"></i>');
        var self = this;
        setTimeout(function() { $(self).html('<i class="fas fa-copy"></i>'); }, 2000);
    });

    $('#keyResultModal').on('hidden.bs.modal', function() {
        location.reload();
    });

    $(document).on('click', '.toggle-key', function() {
        var input = $(this).closest('tr').find('.key-input');
        var isPass = input.attr('type') === 'password';
        input.attr('type', isPass ? 'text' : 'password');
        $(this).html(isPass ? '<i class="fas fa-eye-slash"></i>' : '<i class="fas fa-eye"></i>');
    });

    $(document).on('click', '.qr-key', function() {
        showQR($(this).data('key'));
    });

    $(document).on('click', '.revoke-key', function() {
        if (!confirm('Revoke this API key?')) return;
        $.ajax({
            url: REVOKE_KEY_URL_BASE.replace('0', $(this).data('id')),
            method: 'POST',
            success: function() { location.reload(); },
            error: handleAjaxError
        });
    });
});
