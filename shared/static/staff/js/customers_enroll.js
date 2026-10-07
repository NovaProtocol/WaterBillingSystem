document.getElementById('create-customer-form').addEventListener('submit', function (e) {
    e.preventDefault();
    var val = function (id) {
        var el = document.getElementById(id);
        return el ? el.value.trim() : '';
    };
    var num = function (id) {
        var v = parseFloat(val(id));
        return isNaN(v) ? null : v;
    };
    fetch(ENROLL_CUSTOMER_URL, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            customer_number: val('cust-number'),
            name: val('cust-name'),
            address: val('cust-address'),
            contact_number: val('cust-contact'),
            email: val('cust-email'),
            meter_serial_number: val('cust-meter-sn'),
            x_coordinate: num('cust-x'),
            y_coordinate: num('cust-y'),
            phase: val('cust-phase') || null,
            block: val('cust-block') || null,
            street: val('cust-street') || null,
        }),
    })
        .then(function (resp) {
            return resp.json().catch(function () { return {}; }).then(function (data) {
                return { ok: resp.ok, data: data };
            });
        })
        .then(function (result) {
            var box = document.getElementById('customer-result');
            if (result.ok) {
                box.innerHTML = '<div class="alert alert-success py-2 alert-rounded">Customer <strong>' + result.data.customer_number + '</strong> enrolled.</div>';
                setTimeout(function () { location.reload(); }, 1000);
            } else {
                var msg = (result.data && (result.data.error && (result.data.error.message || result.data.error))) || 'Failed to enroll customer.';
                box.innerHTML = '<div class="alert alert-danger py-2 alert-rounded">' + msg + '</div>';
            }
        })
        .catch(function () {
            document.getElementById('customer-result').innerHTML = '<div class="alert alert-danger py-2 alert-rounded">Failed to enroll customer.</div>';
        });
});
