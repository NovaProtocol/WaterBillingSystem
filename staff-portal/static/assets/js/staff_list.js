function buildPerms(prefix) {
    var perms = {};
    $(prefix + ' .custom-control-input:checked').each(function() {
        perms[$(this).val()] = true;
    });
    return perms;
}

$('#create-staff-form').on('submit', function(e) {
    e.preventDefault();
    var perms = buildPerms('#create-staff-form');
    $.ajax({
        url: STAFF_CREATE_URL,
        method: 'POST',
        contentType: 'application/json',
        data: JSON.stringify({
            name: $('#staff-name').val().trim(),
            username: $('#staff-username').val().trim(),
            password: $('#staff-password').val(),
            email: $('#staff-email').val().trim(),
            contact_number: $('#staff-contact').val().trim(),
            can_read_meters: perms.can_read_meters || false,
            can_accept_payment: perms.can_accept_payment || false,
            can_enroll_customer: perms.can_enroll_customer || false,
            can_drop_reading: perms.can_drop_reading || false,
            can_drop_payment: perms.can_drop_payment || false,
            can_enroll_staff: perms.can_enroll_staff || false,
            can_manage_billing: perms.can_manage_billing || false,
        }),
        success: function(data) {
            $('#staff-result').html('<div class="alert alert-success py-2 alert-rounded">Staff <strong>' + data.name + '</strong> created.</div>');
            setTimeout(function() { location.reload(); }, 1000);
        },
        error: function(xhr) {
            var msg = 'Failed to create staff.';
            try { var r = JSON.parse(xhr.responseText); msg = r.error; } catch(e) {}
            $('#staff-result').html('<div class="alert alert-danger py-2 alert-rounded">' + msg + '</div>');
        }
    });
});

var permIdMap = {
    can_read_meters: 'edit-perm-read',
    can_accept_payment: 'edit-perm-payment',
    can_enroll_customer: 'edit-perm-enroll',
    can_drop_reading: 'edit-perm-drop-read',
    can_drop_payment: 'edit-perm-drop-pay',
    can_manage_billing: 'edit-perm-billing',
    can_enroll_staff: 'edit-perm-staff',
};

$('.edit-staff').on('click', function() {
    var id = $(this).data('id');
    $.get(STAFF_EDIT_URL_BASE.replace('0', id), function(data) {
        $('#edit-staff-id').val(data.id);
        $('#edit-staff-name').val(data.name);
        $('#edit-staff-username').val(data.username);
        $('#edit-staff-password').val('');
        $('#edit-staff-email').val(data.email || '');
        $('#edit-staff-contact').val(data.contact_number || '');
        $('.edit-perm').prop('checked', false);
        $.each(permIdMap, function(perm, id) {
            if (data[perm]) $('#' + id).prop('checked', true);
        });
        $('#edit-perm-active').prop('checked', data.is_active);
        $('#edit-staff-result').empty();
        $('#editStaffModal').modal('show');
    });
});

$('#edit-staff-form').on('submit', function(e) {
    e.preventDefault();
    var perms = buildPerms('#editStaffModal');
    var id = $('#edit-staff-id').val();
    $.ajax({
        url: STAFF_EDIT_URL_BASE.replace('0', id),
        method: 'POST',
        contentType: 'application/json',
        data: JSON.stringify({
            name: $('#edit-staff-name').val().trim(),
            username: $('#edit-staff-username').val().trim(),
            password: $('#edit-staff-password').val(),
            email: $('#edit-staff-email').val().trim(),
            contact_number: $('#edit-staff-contact').val().trim(),
            can_read_meters: perms.can_read_meters || false,
            can_accept_payment: perms.can_accept_payment || false,
            can_enroll_customer: perms.can_enroll_customer || false,
            can_drop_reading: perms.can_drop_reading || false,
            can_drop_payment: perms.can_drop_payment || false,
            can_enroll_staff: perms.can_enroll_staff || false,
            can_manage_billing: perms.can_manage_billing || false,
            is_active: perms.is_active || false,
        }),
        success: function(data) {
            $('#edit-staff-result').html('<div class="alert alert-success py-2 alert-rounded">Staff <strong>' + data.name + '</strong> updated.</div>');
            setTimeout(function() { location.reload(); }, 1000);
        },
        error: function(xhr) {
            var msg = 'Failed to update staff.';
            try { var r = JSON.parse(xhr.responseText); msg = r.error; } catch(e) {}
            $('#edit-staff-result').html('<div class="alert alert-danger py-2 alert-rounded">' + msg + '</div>');
        }
    });
});
