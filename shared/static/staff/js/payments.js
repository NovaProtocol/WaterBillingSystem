$(function() {
    var selectedCustomer = null;
    var searchTimeout;
    $('#customerSearch').on('input', function() {
        clearTimeout(searchTimeout);
        var q = $(this).val();
        if (q.length < 1) { $('#customerDropdown').hide(); return; }
        searchTimeout = setTimeout(function() {
            $.ajax(CUSTOMER_LOOKUP_URL, {
                data: {q: q},
                dataType: 'json',
                success: function(data) {
                    var d = $('#customerDropdown'); d.empty();
                    if (data && data.error === 'mixed_input') { d.append('<div class="item invalid-feedback d-block px-3 py-2 mb-0" style="font-size:0.82rem;">'+(data.message||'Invalid search')+'</div>'); d.show(); return; }
                    if (!data || !data.length) { d.hide(); return; }
                    data.forEach(function(c) {
                        d.append('<div class="item" data-number="'+c.customer_number+'" data-name="'+$('<span>').text(c.name).html()+'"><strong>'+c.customer_number+'</strong> &mdash; '+$('<span>').text(c.name).html()+'<br><span class="sub">'+$('<span>').text(c.address||'').html()+'</span></div>');
                    });
                    d.show();
                },
                error: function() {
                    $('#customerDropdown').hide();
                }
            });
        }, 250);
    });

    $(document).on('click', '#customerDropdown .item', function() {
        selectedCustomer = $(this).data('number');
        $('#customerSearch').val(selectedCustomer + ' — ' + $(this).data('name'));
        $('#customerDropdown').hide();
        loadCustomer(selectedCustomer);
    });

    $(document).on('click', function(e) {
        if (!$(e.target).closest('.autocomplete-wrap').length) $('#customerDropdown').hide();
    });

    function loadCustomer(custNum) {
        var url = API_CUSTOMER_URL.replace('0', encodeURIComponent(custNum));
        $.ajax(url, {
            dataType: 'text',
            success: function(text) {
                try {
                    var data = JSON.parse(text);
                } catch(e) {
                    alert('Invalid JSON response');
                    return;
                }
                if (data.error) { alert(data.error); return; }

                selectedCustomer = custNum;
                $('#custNumLabel').text('(' + data.customer_number + ')');
                $('#infoCustNum').text(data.customer_number);
                $('#infoName').text(data.name || '—');
                $('#infoAddress').text(data.address || '—');
                $('#infoContact').text(data.contact_number || '—');
                $('#infoEmail').text(data.email || '—');

                if (data.latest_reading) {
                    $('#currentReading').text(data.latest_reading.reading_value != null ? data.latest_reading.reading_value : '—');
                    $('#currentReader').text('Recorded by: ' + (data.latest_reading.reader || data.latest_reading.reader_id || '—'));
                    var d = new Date((data.latest_reading.timestamp||0) * 1000);
                    $('#currentDate').text(d.toLocaleDateString() + ' ' + d.toLocaleTimeString());
                } else {
                    $('#currentReading').text('—');
                    $('#currentReader').text('No readings available');
                    $('#currentDate').text('');
                }

                if (data.last_reading) {
                    $('#prevReading').text(data.last_reading.reading_value != null ? data.last_reading.reading_value : '—');
                    $('#prevReader').text('Recorded by: ' + (data.last_reading.reader || data.last_reading.reader_id || '—'));
                    var d2 = new Date((data.last_reading.timestamp||0) * 1000);
                    $('#prevDate').text(d2.toLocaleDateString() + ' ' + d2.toLocaleTimeString());
                } else {
                    $('#prevReading').text('—');
                    $('#prevReader').text('No previous reading');
                    $('#prevDate').text('');
                }

                var _cons2 = (data.consumption!=null&&isFinite(data.consumption))?Number(data.consumption):0;
                $('#consumptionLabel').html(_cons2.toFixed(2) + ' m&sup3; consumed this period');
                var tierBody = $('#tierTable tbody');
                tierBody.empty();
                if (data.bill_breakdown && data.bill_breakdown.length) {
                    data.bill_breakdown.forEach(function(item, idx) {
                        var rateHtml = '';
                        if (data.pricing_tiers && data.pricing_tiers[idx]) {
                            var tier = data.pricing_tiers[idx];
                            rateHtml = tier.unit === 'flat' ? '&#x20B1;' + tier.rate.toFixed(2) + ' flat' : '&#x20B1;' + tier.rate.toFixed(2) + '/m&sup3;';
                        }
                        var style = item.units === 0 ? ' style="color:#6c757d;"' : '';
                        tierBody.append(
                            '<tr' + style + '>' +
                                '<td>' + item.label + '</td>' +
                                '<td>' + ((item.units!=null&&isFinite(item.units))?Number(item.units):0).toFixed(2) + ' m&sup3;</td>' +
                                '<td>' + rateHtml + '</td>' +
                                '<td class="text-right font-weight-bold">&#x20B1;' + ((item.charge!=null&&isFinite(item.charge))?Number(item.charge):0).toFixed(2) + '</td>' +
                            '</tr>'
                        );
                    });
                    tierBody.append(
                        '<tr class="font-weight-bold" style="border-top:2px solid #1a1a2e;">' +
                            '<td colspan="3">Total Water Bill</td>' +
                            '<td class="text-right">&#x20B1;' + ((data.original_water_bill!=null&&isFinite(data.original_water_bill))?Number(data.original_water_bill):0).toFixed(2) + '</td>' +
                        '</tr>'
                    );
                }

                var ubList = $('#unpaidBillsList');
                ubList.empty();
                if (data.unpaid_bills && data.unpaid_bills.length > 0) {
                    data.unpaid_bills.forEach(function(ub) {
                        ubList.append(
                            '<div class="d-flex justify-content-between mb-1" style="font-size:0.85rem;">' +
                                '<span class="text-muted">' + ub.month + '</span>' +
                                '<span class="font-weight-bold">₱' + ((ub.amount!=null&&isFinite(ub.amount))?Number(ub.amount):0).toFixed(2) + '</span>' +
                            '</div>'
                        );
                        if (ub.penalty > 0) {
                            ubList.append(
                                '<div class="d-flex justify-content-between mb-2" style="font-size:0.85rem;">' +
                                    '<span class="text-muted" style="padding-left: 1.2rem;">+ Late Penalty</span>' +
                                    '<span class="font-weight-bold" style="color: #dc3545;">+ ₱' + ((ub.penalty!=null&&isFinite(ub.penalty))?Number(ub.penalty):0).toFixed(2) + '</span>' +
                                '</div>'
                            );
                        }
                    });
                    ubList.append(
                        '<div class="d-flex justify-content-between mb-2 pt-1" style="border-top:1px solid #dee2e6;font-size:0.85rem;">' +
                            '<span class="font-weight-bold">Total Unpaid</span>' +
                            '<span class="font-weight-bold">₱' + ((data.total_unpaid!=null&&isFinite(data.total_unpaid))?Number(data.total_unpaid):0).toFixed(2) + '</span>' +
                        '</div>'
                    );
                } else {
                    ubList.append('<p class="text-muted mb-0" style="font-size:0.85rem;">All bills paid</p>');
                }

                if (data.cumulative_balance !== 0) {
                    var carryText;
                    if (data.cumulative_balance > 0) {
                        var _co = (data.carryover!=null&&isFinite(data.carryover))?Number(data.carryover):0;
                        carryText = '&minus; &#x20B1;' + _co.toFixed(2);
                        $('#summaryCarryover').css('color', '#28a745');
                    } else {
                        var _co2 = (data.carryover!=null&&isFinite(data.carryover))?Number(data.carryover):0;
                        carryText = '+ &#x20B1;' + _co2.toFixed(2);
                        $('#summaryCarryover').css('color', '#dc3545');
                    }
                    $('#summaryCarryover').html(carryText);
                    $('#carryoverRow').show();
                } else {
                    $('#carryoverRow').hide();
                }

                var _td = (data.total_due!=null&&isFinite(data.total_due))?Number(data.total_due):0;
                $('#summaryTotalDue').html('&#x20B1;' + _td.toFixed(2));

                if (data.due_date) {
                    $('#dueDateRow').text('Due in ' + data.days_remaining + ' day' + (data.days_remaining === 1 ? '' : 's') + ' (' + data.due_date + ')');
                    $('#dueDateRow').show();
                } else {
                    $('#dueDateRow').hide();
                }

                var tbody = $('#billingTableBody');
                tbody.empty();
                if (data.billing_items && data.billing_items.length) {
                    data.billing_items.forEach(function(item) {
                        var d = new Date(item.timestamp * 1000);
                        var periodStr = (d.getMonth()+1) + '/' + d.getFullYear();
                        tbody.append(
                            '<tr>' +
                                '<td>' + periodStr + '</td>' +
                                '<td>' + item.reading_value + '</td>' +
                                '<td>' + item.consumption + '</td>' +
                                '<td>&#x20B1;' + item.water_bill.toFixed(2) + '</td>' +
                                '<td>' + (item.penalty > 0 ? '&#x20B1;' + item.penalty.toFixed(2) : '') + '</td>' +
                                '<td>&#x20B1;' + item.total_due.toFixed(2) + '</td>' +
                                '<td>' + (item.paid_amount > 0 ? '&#x20B1;' + item.paid_amount.toFixed(2) : '') + '</td>' +
                                '<td>' + (item.carryover_offset !== 0
                                  ? (item.carryover_offset < 0
                                    ? '<span style="color:#dc3545;">−₱' + Math.abs(item.carryover_offset).toFixed(2) + '</span>'
                                    : '₱' + item.carryover_offset.toFixed(2))
                                  : '') + '</td>' +
                                '<td>' + (item.status === 'Paid' ? '<span class="badge badge-success">Paid</span>' : '<span class="badge badge-danger">Unpaid</span>') + '</td>' +
                            '</tr>'
                        );
                    });
                } else {
                    tbody.append('<tr><td colspan="9" class="text-muted text-center">No billing records</td></tr>');
                }

                var _td2 = (data.total_due!=null&&isFinite(data.total_due))?Number(data.total_due):0;
                $('#amountDue').val(_td2.toFixed(2));
                $('#payAmount').val(_td2.toFixed(2));
                $('#payCustNum').val(data.customer_number);

                var ph = $('#paymentHistoryBody');
                ph.empty();
                if (data.recent_payments && data.recent_payments.length) {
                    data.recent_payments.forEach(function(p) {
                        var pd = new Date(p.timestamp * 1000);
                        var _pa = (p.paid_amount!=null&&isFinite(p.paid_amount))?Number(p.paid_amount):0;
                        ph.append('<tr><td>' + (p.receipt_number||'N/A') + '</td><td>&#x20B1;' + _pa.toFixed(2) + '</td><td>' + pd.toLocaleDateString() + '</td></tr>');
                    });
                } else {
                    ph.append('<tr><td colspan="3" class="text-muted text-center">No payments</td></tr>');
                }

                $('#billingInfo').show();
            },
            error: function() {
                alert('Failed to load customer data');
            }
        });
    }

    $('#paymentForm').on('submit', function(e) {
        e.preventDefault();
        var custNum = $('#payCustNum').val();
        var amount = parseFloat($('#payAmount').val());
        if (!custNum || !amount || amount <= 0) { alert('Please enter a valid amount'); return; }
        $.ajax({
            url: SUBMIT_PAYMENT_URL,
            method: 'POST',
            contentType: 'application/json',
            data: JSON.stringify({customer_number: custNum, amount: amount}),
            success: function(data) {
                $('#receiptNum').text(data.receipt_number);
                $('#receiptAmount').html('&#x20B1;' + data.amount.toFixed(2));
                $('#paymentConfirmModal').modal('show');
                loadCustomer(custNum);
                $('#payAmount').val('');
            },
            error: function(xhr) { alert('Error: ' + (xhr.responseJSON ? xhr.responseJSON.error : 'Unknown')); }
        });
    });

    $('#paymentConfirmModal').on('hidden.bs.modal', function() {
        $('#payAmount').val($('#amountDue').val());
    });
});
