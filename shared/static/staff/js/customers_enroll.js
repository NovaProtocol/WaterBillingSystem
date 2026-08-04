$('#create-customer-form').on('submit', function(e) {
    e.preventDefault();
    $.ajax({
        url: ENROLL_CUSTOMER_URL,
        method: 'POST',
        contentType: 'application/json',
        data: JSON.stringify({
            customer_number: $('#cust-number').val().trim(),
            name: $('#cust-name').val().trim(),
            address: $('#cust-address').val().trim(),
            contact_number: $('#cust-contact').val().trim(),
            email: $('#cust-email').val().trim(),
            meter_serial_number: $('#cust-meter-sn').val().trim(),
            x_coordinate: parseFloat($('#cust-x').val()) || null,
            y_coordinate: parseFloat($('#cust-y').val()) || null,
            phase: $('#cust-phase').val().trim() || null,
            block: $('#cust-block').val().trim() || null,
            street: $('#cust-street').val().trim() || null,
        }),
        success: function(data) {
            $('#customer-result').html('<div class="alert alert-success py-2 alert-rounded">Customer <strong>' + data.customer_number + '</strong> enrolled.</div>');
            setTimeout(function() { location.reload(); }, 1000);
        },
        error: function(xhr) {
            var msg = 'Failed to enroll customer.';
            try { var r = JSON.parse(xhr.responseText); msg = r.error; } catch(e) {}
            $('#customer-result').html('<div class="alert alert-danger py-2 alert-rounded">' + msg + '</div>');
        }
    });
});
