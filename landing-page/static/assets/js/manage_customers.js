$(function() {
    var currentClearNfcId = null;

    $(document).on('click', '.edit-customer', function() {
        var $btn = $(this);
        $('#editCustId').val($btn.data('id'));
        $('#editCustNumber').val($btn.data('number'));
        $('#editCustName').val($btn.data('name'));
        $('#editCustContact').val($btn.data('contact'));
        $('#editCustAddress').val($btn.data('address'));
        $('#editCustEmail').val($btn.data('email'));
        $('#editCustPhase').val($btn.data('phase'));
        $('#editCustBlock').val($btn.data('block'));
        $('#editCustStreet').val($btn.data('street'));
        $('#editCustMeterSn').val($btn.data('meter-sn'));
        $('#editCustX').val($btn.data('x'));
        $('#editCustY').val($btn.data('y'));

        var nfcTagId = $btn.data('nfc-tag-id') || '';
        var hasNfc = nfcTagId.length > 0;
        var $clearBtn = $('#clearNfcBtn');
        var $label = $('#clearNfcLabel');
        if (hasNfc) {
            $clearBtn.prop('disabled', false).css({opacity:1,background:'#dc3545',color:'#fff',border:'1px solid #dc3545',cursor:'pointer'});
            $label.text('Clear NFC Mapping (' + nfcTagId.substring(0, 12) + '...)');
        } else {
            $clearBtn.prop('disabled', true).css({opacity:0.4,background:'#e9ecef',color:'#6c757d',border:'1px solid #dee2e6',cursor:'not-allowed'});
            $label.text('No NFC Mapping');
        }

        currentClearNfcId = $btn.data('id');
        $('#editCustomerModal').modal('show');
    });

    $('#editCustomerForm').on('submit', function(e) {
        e.preventDefault();
        var id = $('#editCustId').val();
        $.ajax({
            url: EDIT_CUSTOMER_URL_BASE.replace('0', id),
            method: 'POST',
            contentType: 'application/json',
            data: JSON.stringify({
                name: $('#editCustName').val().trim(),
                address: $('#editCustAddress').val().trim(),
                contact_number: $('#editCustContact').val().trim(),
                email: $('#editCustEmail').val().trim(),
                phase: $('#editCustPhase').val().trim(),
                block: $('#editCustBlock').val().trim(),
                meter_serial_number: $'#editCustMeterSn'.val().trim(),
                street: $('#editCustStreet').val().trim(),
        $('#editCustMeterSn').val($btn.data('meter-sn'));
                x_coordinate: parseFloat($('#editCustX').val()) || null,
                y_coordinate: parseFloat($('#editCustY').val()) || null,
            }),
            success: function() { $('#editCustomerModal').modal('hide'); location.reload(); },
            error: handleAjaxError
        });
    });

    $(document).on('click', '.toggle-active', function() {
        var id = $(this).data('id');
        var active = $(this).data('active') === 'true';
        var action = active ? 'deactivate' : 'reactivate';
        if (!confirm('Are you sure you want to ' + action + ' this customer? This may affect billing.')) return;
        $.ajax({
            url: TOGGLE_ACTIVE_URL_BASE.replace('0', id),
            method: 'POST',
            success: function() { location.reload(); },
            error: handleAjaxError
        });
    });

    $('#clearNfcBtn').on('click', function() {
        if (!currentClearNfcId || $(this).prop('disabled')) return;
        if (!confirm('Clear NFC mapping for this customer? The mobile app will detect this change and remove the tag from its local cache on next sync.')) return;
        $.ajax({
            url: CLEAR_NFC_URL_BASE.replace('0', currentClearNfcId),
            method: 'POST',
            success: function(data) {
                alert(data.message);
                $('#editCustomerModal').modal('hide');
                location.reload();
            },
            error: handleAjaxError
        });
    });
});