(function () {
    'use strict';

    var selectedCustomer = null;

    function setText(id, value) {
        var el = document.getElementById(id);
        if (el) el.textContent = value;
    }

    function setHtml(id, value) {
        var el = document.getElementById(id);
        if (el) el.innerHTML = value;
    }

    var dropdown = document.getElementById('customerDropdown');
    var searchEl = document.getElementById('customerSearch');
    var searchTimeout;

    searchEl.addEventListener('input', function () {
        clearTimeout(searchTimeout);
        var q = searchEl.value;
        if (q.length < 1) { dropdown.style.display = 'none'; return; }
        searchTimeout = setTimeout(function () {
            fetch(CUSTOMER_LOOKUP_URL + '?q=' + encodeURIComponent(q))
                .then(function (r) { return r.json(); })
                .then(function (data) {
                    dropdown.innerHTML = '';
                    if (data && data.error === 'mixed_input') {
                        dropdown.innerHTML = '<div class="item invalid-feedback d-block px-3 py-2 mb-0" style="font-size:0.82rem;">' + (data.message || 'Invalid search') + '</div>';
                        dropdown.style.display = '';
                        return;
                    }
                    if (!data || !data.length) { dropdown.style.display = 'none'; return; }
                    var h = '';
                    data.forEach(function (c) {
                        h += '<div class="item" data-number="' + esc(c.customer_number) + '" data-name="' + esc(c.name) + '"><strong>' + esc(c.customer_number) + '</strong> &mdash; ' + esc(c.name) + '<br><span class="sub">' + esc(c.address || '') + '</span></div>';
                    });
                    dropdown.innerHTML = h;
                    dropdown.style.display = '';
                })
                .catch(function () { dropdown.style.display = 'none'; });
        }, 250);
    });

    dropdown.addEventListener('click', function (e) {
        var item = e.target.closest('.item');
        if (!item) return;
        selectedCustomer = item.dataset.number;
        searchEl.value = selectedCustomer + ', ' + item.dataset.name;
        dropdown.style.display = 'none';
        loadCustomer(selectedCustomer);
    });

    document.addEventListener('click', function (e) {
        if (!e.target.closest('.autocomplete-wrap')) dropdown.style.display = 'none';
    });

    function loadCustomer(custNum) {
        fetch(API_CUSTOMER_URL.replace('0', encodeURIComponent(custNum)))
            .then(function (r) { return r.text(); })
            .then(function (text) {
                var data;
                try { data = JSON.parse(text); } catch (e) { alert('Invalid JSON response'); return; }
                if (data.error) { alert(data.error); return; }

                selectedCustomer = custNum;
                setText('custNumLabel', '(' + data.customer_number + ')');
                setText('infoCustNum', data.customer_number);
                setText('infoName', data.name || ' - ');
                setText('infoAddress', data.address || ' - ');
                setText('infoContact', data.contact_number || ' - ');
                setText('infoEmail', data.email || ' - ');

                if (data.latest_reading) {
                    setText('currentReading', data.latest_reading.reading_value != null ? data.latest_reading.reading_value : ' - ');
                    setText('currentReader', 'Recorded by: ' + (data.latest_reading.reader || data.latest_reading.reader_id || ' - '));
                    var d = new Date((data.latest_reading.timestamp || 0) * 1000);
                    setText('currentDate', d.toLocaleDateString() + ' ' + d.toLocaleTimeString());
                } else {
                    setText('currentReading', ' - ');
                    setText('currentReader', 'No readings available');
                    setText('currentDate', '');
                }

                if (data.last_reading) {
                    setText('prevReading', data.last_reading.reading_value != null ? data.last_reading.reading_value : ' - ');
                    setText('prevReader', 'Recorded by: ' + (data.last_reading.reader || data.last_reading.reader_id || ' - '));
                    var d2 = new Date((data.last_reading.timestamp || 0) * 1000);
                    setText('prevDate', d2.toLocaleDateString() + ' ' + d2.toLocaleTimeString());
                } else {
                    setText('prevReading', ' - ');
                    setText('prevReader', 'No previous reading');
                    setText('prevDate', '');
                }

                var cons = (data.consumption != null && isFinite(data.consumption)) ? Number(data.consumption) : 0;
                setHtml('consumptionLabel', cons.toFixed(2) + ' m&sup3; consumed this period');

                var tierBody = document.querySelector('#tierTable tbody');
                var th = '';
                if (data.bill_breakdown && data.bill_breakdown.length) {
                    data.bill_breakdown.forEach(function (item, idx) {
                        var rateHtml = '';
                        if (data.pricing_tiers && data.pricing_tiers[idx]) {
                            var tier = data.pricing_tiers[idx];
                            rateHtml = tier.unit === 'flat' ? '&#x20B1;' + tier.rate.toFixed(2) + ' flat' : '&#x20B1;' + tier.rate.toFixed(2) + '/m&sup3;';
                        }
                        var style = item.units === 0 ? ' style="color:#6c757d;"' : '';
                        th += '<tr' + style + '>'
                            + '<td>' + item.label + '</td>'
                            + '<td>' + ((item.units != null && isFinite(item.units)) ? Number(item.units) : 0).toFixed(2) + ' m&sup3;</td>'
                            + '<td>' + rateHtml + '</td>'
                            + '<td class="text-end font-weight-bold">&#x20B1;' + ((item.charge != null && isFinite(item.charge)) ? Number(item.charge) : 0).toFixed(2) + '</td>'
                            + '</tr>';
                    });
                    th += '<tr class="font-weight-bold" style="border-top:2px solid #1a1a2e;">'
                        + '<td colspan="3">Total Water Bill</td>'
                        + '<td class="text-end">&#x20B1;' + ((data.original_water_bill != null && isFinite(data.original_water_bill)) ? Number(data.original_water_bill) : 0).toFixed(2) + '</td>'
                        + '</tr>';
                }
                tierBody.innerHTML = th;

                var ubList = document.getElementById('unpaidBillsList');
                var uh = '';
                if (data.unpaid_bills && data.unpaid_bills.length > 0) {
                    data.unpaid_bills.forEach(function (ub) {
                        uh += '<div class="d-flex justify-content-between mb-1" style="font-size:0.85rem;">'
                            + '<span class="text-muted">' + ub.month + '</span>'
                            + '<span class="font-weight-bold">\u20B1' + ((ub.amount != null && isFinite(ub.amount)) ? Number(ub.amount) : 0).toFixed(2) + '</span>'
                            + '</div>';
                        if (ub.penalty > 0) {
                            uh += '<div class="d-flex justify-content-between mb-2" style="font-size:0.85rem;">'
                                + '<span class="text-muted" style="padding-left: 1.2rem;">+ Late Penalty</span>'
                                + '<span class="font-weight-bold" style="color: #dc3545;">+ \u20B1' + ((ub.penalty != null && isFinite(ub.penalty)) ? Number(ub.penalty) : 0).toFixed(2) + '</span>'
                                + '</div>';
                        }
                    });
                    uh += '<div class="d-flex justify-content-between mb-2 pt-1" style="border-top:1px solid #dee2e6;font-size:0.85rem;">'
                        + '<span class="font-weight-bold">Total Unpaid</span>'
                        + '<span class="font-weight-bold">\u20B1' + ((data.total_unpaid != null && isFinite(data.total_unpaid)) ? Number(data.total_unpaid) : 0).toFixed(2) + '</span>'
                        + '</div>';
                } else {
                    uh = '<p class="text-muted mb-0" style="font-size:0.85rem;">All bills paid</p>';
                }
                ubList.innerHTML = uh;

                var carryEl = document.getElementById('summaryCarryover');
                if (data.cumulative_balance !== 0) {
                    if (data.cumulative_balance > 0) {
                        var co = (data.carryover != null && isFinite(data.carryover)) ? Number(data.carryover) : 0;
                        carryEl.innerHTML = '&minus; &#x20B1;' + co.toFixed(2);
                        carryEl.style.color = '#28a745';
                    } else {
                        var co2 = (data.carryover != null && isFinite(data.carryover)) ? Number(data.carryover) : 0;
                        carryEl.innerHTML = '+ &#x20B1;' + co2.toFixed(2);
                        carryEl.style.color = '#dc3545';
                    }
                    document.getElementById('carryoverRow').style.display = '';
                } else {
                    document.getElementById('carryoverRow').style.display = 'none';
                }

                var td = (data.total_due != null && isFinite(data.total_due)) ? Number(data.total_due) : 0;
                setHtml('summaryTotalDue', '&#x20B1;' + td.toFixed(2));

                var dueRow = document.getElementById('dueDateRow');
                if (data.due_date) {
                    dueRow.textContent = 'Due in ' + data.days_remaining + ' day' + (data.days_remaining === 1 ? '' : 's') + ' (' + data.due_date + ')';
                    dueRow.style.display = '';
                } else {
                    dueRow.style.display = 'none';
                }

                var tbody = document.getElementById('billingTableBody');
                var bh = '';
                if (data.billing_items && data.billing_items.length) {
                    data.billing_items.forEach(function (item) {
                        var bd = new Date(item.timestamp * 1000);
                        var periodStr = (bd.getMonth() + 1) + '/' + bd.getFullYear();
                        var carryCell = item.carryover_offset !== 0
                            ? (item.carryover_offset < 0
                                ? '<span style="color:#dc3545;">\u2212\u20B1' + Math.abs(item.carryover_offset).toFixed(2) + '</span>'
                                : '\u20B1' + item.carryover_offset.toFixed(2))
                            : '';
                        bh += '<tr>'
                            + '<td>' + periodStr + '</td>'
                            + '<td>' + item.reading_value + '</td>'
                            + '<td>' + item.consumption + '</td>'
                            + '<td>&#x20B1;' + item.water_bill.toFixed(2) + '</td>'
                            + '<td>' + (item.penalty > 0 ? '&#x20B1;' + item.penalty.toFixed(2) : '') + '</td>'
                            + '<td>&#x20B1;' + item.total_due.toFixed(2) + '</td>'
                            + '<td>' + (item.paid_amount > 0 ? '&#x20B1;' + item.paid_amount.toFixed(2) : '') + '</td>'
                            + '<td>' + carryCell + '</td>'
                            + '<td>' + (item.status === 'Paid' ? '<span class="badge badge-success">Paid</span>' : '<span class="badge badge-danger">Unpaid</span>') + '</td>'
                            + '</tr>';
                    });
                } else {
                    bh = '<tr><td colspan="9" class="text-muted text-center">No billing records</td></tr>';
                }
                tbody.innerHTML = bh;

                document.getElementById('amountDue').value = td.toFixed(2);
                document.getElementById('payAmount').value = td.toFixed(2);
                document.getElementById('payCustNum').value = data.customer_number;

                var ph = '';
                if (data.recent_payments && data.recent_payments.length) {
                    data.recent_payments.forEach(function (p) {
                        var pd = new Date(p.timestamp * 1000);
                        var pa = (p.paid_amount != null && isFinite(p.paid_amount)) ? Number(p.paid_amount) : 0;
                        ph += '<tr><td>' + (p.receipt_number || 'N/A') + '</td><td>&#x20B1;' + pa.toFixed(2) + '</td><td>' + pd.toLocaleDateString() + '</td></tr>';
                    });
                } else {
                    ph = '<tr><td colspan="3" class="text-muted text-center">No payments</td></tr>';
                }
                document.getElementById('paymentHistoryBody').innerHTML = ph;

                document.getElementById('billingInfo').style.display = '';
            })
            .catch(function () { alert('Failed to load customer data'); });
    }

    document.getElementById('paymentForm').addEventListener('submit', function (e) {
        e.preventDefault();
        var custNum = document.getElementById('payCustNum').value;
        var amount = parseFloat(document.getElementById('payAmount').value);
        if (!custNum || !amount || amount <= 0) { alert('Please enter a valid amount'); return; }
        postJSON(SUBMIT_PAYMENT_URL, { customer_number: custNum, amount: amount })
            .then(function (data) {
                setText('receiptNum', data.receipt_number);
                setHtml('receiptAmount', '&#x20B1;' + data.amount.toFixed(2));
                bootstrap.Modal.getOrCreateInstance(document.getElementById('paymentConfirmModal')).show();
                loadCustomer(custNum);
                document.getElementById('payAmount').value = '';
            })
            .catch(function (err) { alert('Error: ' + (err && err.message ? err.message : 'Unknown')); });
    });

    document.getElementById('paymentConfirmModal').addEventListener('hidden.bs.modal', function () {
        document.getElementById('payAmount').value = document.getElementById('amountDue').value;
    });
})();
