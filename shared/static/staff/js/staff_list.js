function buildPerms(prefix) {
    var perms = {};
    Array.prototype.forEach.call(document.querySelectorAll(prefix + ' .form-check-input:checked'), function (el) {
        perms[el.value] = true;
    });
    return perms;
}

var permIdMap = {
    can_read_meters: 'edit-perm-read',
    can_accept_payment: 'edit-perm-payment',
    can_enroll_customer: 'edit-perm-enroll',
    can_drop_reading: 'edit-perm-drop-read',
    can_drop_payment: 'edit-perm-drop-pay',
    can_manage_billing: 'edit-perm-billing',
    can_enroll_staff: 'edit-perm-staff',
};

function permFields(perms) {
    return {
        can_read_meters: perms.can_read_meters || false,
        can_accept_payment: perms.can_accept_payment || false,
        can_enroll_customer: perms.can_enroll_customer || false,
        can_drop_reading: perms.can_drop_reading || false,
        can_drop_payment: perms.can_drop_payment || false,
        can_enroll_staff: perms.can_enroll_staff || false,
        can_manage_billing: perms.can_manage_billing || false,
    };
}

document.getElementById('create-staff-form').addEventListener('submit', function (e) {
    e.preventDefault();
    var perms = buildPerms('#create-staff-form');
    var val = function (id) { return document.getElementById(id).value.trim(); };
    postJSON(STAFF_CREATE_URL, Object.assign({
        name: val('staff-name'),
        username: val('staff-username'),
        password: document.getElementById('staff-password').value,
        email: val('staff-email'),
        contact_number: val('staff-contact'),
    }, permFields(perms)))
        .then(function (data) {
            document.getElementById('staff-result').innerHTML = '<div class="alert alert-success py-2 alert-rounded">Staff <strong>' + data.name + '</strong> created.</div>';
            setTimeout(function () { location.reload(); }, 1000);
        })
        .catch(function (err) {
            document.getElementById('staff-result').innerHTML = '<div class="alert alert-danger py-2 alert-rounded">' + (err && err.message ? err.message : 'Failed to create staff.') + '</div>';
        });
});

document.addEventListener('click', function (e) {
    var btn = e.target.closest('.edit-staff');
    if (!btn) return;
    fetch(STAFF_EDIT_URL_BASE.replace('0', btn.dataset.id))
        .then(function (r) { return r.json(); })
        .then(function (data) {
            document.getElementById('edit-staff-id').value = data.id;
            document.getElementById('edit-staff-name').value = data.name;
            document.getElementById('edit-staff-username').value = data.username;
            document.getElementById('edit-staff-password').value = '';
            document.getElementById('edit-staff-email').value = data.email || '';
            document.getElementById('edit-staff-contact').value = data.contact_number || '';
            Array.prototype.forEach.call(document.querySelectorAll('.edit-perm'), function (el) { el.checked = false; });
            Object.keys(permIdMap).forEach(function (perm) {
                var el = document.getElementById(permIdMap[perm]);
                if (el && data[perm]) el.checked = true;
            });
            document.getElementById('edit-perm-active').checked = data.is_active;
            document.getElementById('edit-staff-result').innerHTML = '';
            bootstrap.Modal.getOrCreateInstance(document.getElementById('editStaffModal')).show();
        });
});

document.getElementById('edit-staff-form').addEventListener('submit', function (e) {
    e.preventDefault();
    var perms = buildPerms('#editStaffModal');
    var id = document.getElementById('edit-staff-id').value;
    var val = function (fid) { return document.getElementById(fid).value.trim(); };
    postJSON(STAFF_EDIT_URL_BASE.replace('0', id), Object.assign({
        name: val('edit-staff-name'),
        username: val('edit-staff-username'),
        password: document.getElementById('edit-staff-password').value,
        email: val('edit-staff-email'),
        contact_number: val('edit-staff-contact'),
        is_active: perms.is_active || false,
    }, permFields(perms)))
        .then(function (data) {
            document.getElementById('edit-staff-result').innerHTML = '<div class="alert alert-success py-2 alert-rounded">Staff <strong>' + data.name + '</strong> updated.</div>';
            setTimeout(function () { location.reload(); }, 1000);
        })
        .catch(function (err) {
            document.getElementById('edit-staff-result').innerHTML = '<div class="alert alert-danger py-2 alert-rounded">' + (err && err.message ? err.message : 'Failed to update staff.') + '</div>';
        });
});
