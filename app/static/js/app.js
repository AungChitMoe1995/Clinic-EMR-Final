/**
 * Myanmar Clinic EMR - Core Interactive Frontend Utilities
 */

document.addEventListener('DOMContentLoaded', function () {
    initDynamicAgeAndDOB();
    initSirNameGenderMapping();
    initPatientViewState();
    initDynamicFormRows();
    initSettingsPreview();
});

/**
 * Bidirectional Calendar-Aware Dynamic Age <-> DOB Calculation
 */
function initDynamicAgeAndDOB() {
    const dobInput = document.getElementById('date_of_birth');
    const yearsInput = document.getElementById('age_years');
    const monthsInput = document.getElementById('age_months');
    const daysInput = document.getElementById('age_days');
    const ageDisplay = document.getElementById('age_display_text');

    if (!dobInput) return;

    function calculateAgeFromDOB(dobStr) {
        if (!dobStr) return;
        const dob = new Date(dobStr + 'T00:00:00');
        if (isNaN(dob.getTime())) return;

        const today = new Date();
        if (dob > today) {
            if (yearsInput) yearsInput.value = 0;
            if (monthsInput) monthsInput.value = 0;
            if (daysInput) daysInput.value = 0;
            if (ageDisplay) ageDisplay.innerText = '0 Days';
            return;
        }

        let years = today.getFullYear() - dob.getFullYear();
        let months = today.getMonth() - dob.getMonth();
        let days = today.getDate() - dob.getDate();

        if (days < 0) {
            const prevMonth = new Date(today.getFullYear(), today.getMonth(), 0);
            days += prevMonth.getDate();
            months -= 1;
        }

        if (months < 0) {
            years -= 1;
            months += 12;
        }

        if (yearsInput) yearsInput.value = years;
        if (monthsInput) monthsInput.value = months;
        if (daysInput) daysInput.value = days;

        const parts = [];
        if (years > 0) parts.push(years + (years === 1 ? ' Year' : ' Years'));
        if (months > 0) parts.push(months + (months === 1 ? ' Month' : ' Months'));
        if (days > 0 || parts.length === 0) parts.push(days + (days === 1 ? ' Day' : ' Days'));
        if (ageDisplay) ageDisplay.innerText = parts.join(' ');
    }

    function calculateDOBFromAge() {
        const y = parseInt(yearsInput ? yearsInput.value : 0) || 0;
        const m = parseInt(monthsInput ? monthsInput.value : 0) || 0;
        const d = parseInt(daysInput ? daysInput.value : 0) || 0;

        const target = new Date();
        target.setFullYear(target.getFullYear() - y);
        target.setMonth(target.getMonth() - m);
        target.setDate(target.getDate() - d);

        const yyyy = target.getFullYear();
        const mm = String(target.getMonth() + 1).padStart(2, '0');
        const dd = String(target.getDate()).padStart(2, '0');
        dobInput.value = `${yyyy}-${mm}-${dd}`;

        const parts = [];
        if (y > 0) parts.push(y + (y === 1 ? ' Year' : ' Years'));
        if (m > 0) parts.push(m + (m === 1 ? ' Month' : ' Months'));
        if (d > 0 || parts.length === 0) parts.push(d + (d === 1 ? ' Day' : ' Days'));
        if (ageDisplay) ageDisplay.innerText = parts.join(' ');
    }

    dobInput.addEventListener('change', function () {
        calculateAgeFromDOB(this.value);
    });

    if (yearsInput) yearsInput.addEventListener('input', calculateDOBFromAge);
    if (monthsInput) monthsInput.addEventListener('input', calculateDOBFromAge);
    if (daysInput) daysInput.addEventListener('input', calculateDOBFromAge);

    if (dobInput.value) {
        calculateAgeFromDOB(dobInput.value);
    }
}

/**
 * Sir Name -> Default Gender Mapping
 */
function initSirNameGenderMapping() {
    const sirNameSelect = document.getElementById('sir_name');
    const genderSelect = document.getElementById('gender');

    if (!sirNameSelect || !genderSelect) return;

    sirNameSelect.addEventListener('change', function () {
        const selectedOption = this.options[this.selectedIndex];
        const defaultGender = selectedOption.getAttribute('data-default-gender');
        if (defaultGender && (defaultGender === 'Male' || defaultGender === 'Female')) {
            genderSelect.value = defaultGender;
        }
    });
}

/**
 * Patient Module UI State Preservation across [Patients] [Encounters] [Appointments]
 * Discard when leaving Patients module.
 */
function initPatientViewState() {
    const currentPath = window.location.pathname;
    const isPatientModule = currentPath.startsWith('/patients') ||
                            currentPath.startsWith('/encounters') ||
                            currentPath.startsWith('/appointments');

    if (!isPatientModule) {
        // Discard temporary UI state when leaving the module
        sessionStorage.removeItem('emr_patients_filter');
        sessionStorage.removeItem('emr_encounters_filter');
        sessionStorage.removeItem('emr_appointments_filter');
    }
}

/**
 * Dynamic Form Rows for Clinical Workspace (+ Add Diagnosis, + Add Medicine, etc.)
 */
function initDynamicFormRows() {
    // Add Diagnosis
    const addDiagBtn = document.getElementById('btn-add-diagnosis');
    const diagContainer = document.getElementById('diagnoses-container');
    if (addDiagBtn && diagContainer) {
        addDiagBtn.addEventListener('click', function () {
            const row = document.createElement('div');
            row.className = 'diagnosis-row d-flex gap-2 mb-2 align-items-center';
            row.innerHTML = `
                <input type="text" name="diagnosis_text[]" class="form-control form-control-sm" placeholder="Diagnosis (e.g. Acute Bronchitis)" required>
                <select name="diagnosis_category[]" class="form-select form-select-sm" style="width: 140px;">
                    <option value="Primary">Primary</option>
                    <option value="Secondary">Secondary</option>
                    <option value="Provisional">Provisional</option>
                    <option value="Confirmed">Confirmed</option>
                </select>
                <button type="button" class="btn btn-outline-danger btn-sm remove-row-btn" title="Remove">&times;</button>
            `;
            diagContainer.appendChild(row);
        });
    }

    // Add Medicine / Prescription item
    const addMedBtn = document.getElementById('btn-add-medicine');
    const medContainer = document.getElementById('medicines-container');
    if (addMedBtn && medContainer) {
        addMedBtn.addEventListener('click', function () {
            const row = document.createElement('div');
            row.className = 'medicine-row border rounded p-2 mb-2 bg-light';
            row.innerHTML = `
                <div class="row g-2 mb-1">
                    <div class="col-md-5">
                        <input type="text" name="medicine_name[]" class="form-control form-control-sm" placeholder="Medicine / Item name" required>
                    </div>
                    <div class="col-md-2">
                        <input type="text" name="dose[]" class="form-control form-control-sm" placeholder="Dose (e.g. 500mg)">
                    </div>
                    <div class="col-md-2">
                        <input type="text" name="route[]" class="form-control form-control-sm" placeholder="Route (e.g. Oral)">
                    </div>
                    <div class="col-md-3 d-flex gap-1">
                        <input type="text" name="frequency[]" class="form-control form-control-sm" placeholder="Freq (e.g. TDS)">
                        <button type="button" class="btn btn-outline-danger btn-sm remove-row-btn" title="Remove">&times;</button>
                    </div>
                </div>
                <div class="row g-2">
                    <div class="col-md-3">
                        <input type="text" name="duration[]" class="form-control form-control-sm" placeholder="Duration (e.g. 5 days)">
                    </div>
                    <div class="col-md-3">
                        <input type="number" step="any" name="quantity[]" class="form-control form-control-sm" placeholder="Qty">
                    </div>
                    <div class="col-md-6">
                        <input type="text" name="instructions[]" class="form-control form-control-sm" placeholder="Instructions (e.g. After meals)">
                    </div>
                </div>
            `;
            medContainer.appendChild(row);
        });
    }

    // Add Investigation
    const addInvBtn = document.getElementById('btn-add-investigation');
    const invContainer = document.getElementById('investigations-container');
    if (addInvBtn && invContainer) {
        addInvBtn.addEventListener('click', function () {
            const row = document.createElement('div');
            row.className = 'investigation-row d-flex gap-2 mb-2 align-items-center';
            row.innerHTML = `
                <input type="text" name="investigation_name[]" class="form-control form-control-sm" placeholder="Investigation name (e.g. CBC, Chest X-Ray)" required>
                <select name="investigation_status[]" class="form-select form-select-sm" style="width: 140px;">
                    <option value="Ordered">Ordered</option>
                    <option value="Pending">Pending</option>
                    <option value="Completed">Completed</option>
                </select>
                <input type="text" name="investigation_result[]" class="form-control form-control-sm" placeholder="Result / Report summary">
                <button type="button" class="btn btn-outline-danger btn-sm remove-row-btn" title="Remove">&times;</button>
            `;
            invContainer.appendChild(row);
        });
    }

    // Add Procedure
    const addProcBtn = document.getElementById('btn-add-procedure');
    const procContainer = document.getElementById('procedures-container');
    if (addProcBtn && procContainer) {
        addProcBtn.addEventListener('click', function () {
            const row = document.createElement('div');
            row.className = 'procedure-row d-flex gap-2 mb-2 align-items-center';
            row.innerHTML = `
                <input type="text" name="procedure_name[]" class="form-control form-control-sm" placeholder="Procedure name" required>
                <select name="procedure_status[]" class="form-select form-select-sm" style="width: 140px;">
                    <option value="Completed">Completed</option>
                    <option value="In Progress">In Progress</option>
                    <option value="Scheduled">Scheduled</option>
                </select>
                <input type="text" name="procedure_notes[]" class="form-control form-control-sm" placeholder="Notes">
                <button type="button" class="btn btn-outline-danger btn-sm remove-row-btn" title="Remove">&times;</button>
            `;
            procContainer.appendChild(row);
        });
    }

    // Add Voucher Item in Billing
    const addVoucherItemBtn = document.getElementById('btn-add-voucher-item');
    const voucherItemsTable = document.getElementById('voucher-items-tbody');
    if (addVoucherItemBtn && voucherItemsTable) {
        addVoucherItemBtn.addEventListener('click', function () {
            const tr = document.createElement('tr');
            tr.className = 'voucher-item-row';
            tr.innerHTML = `
                <td><input type="text" name="item_desc[]" class="form-control form-control-sm" placeholder="Item / Service description" required></td>
                <td><input type="number" step="any" name="item_qty[]" class="form-control form-control-sm item-calc-qty" value="1" required></td>
                <td><input type="number" step="any" name="item_price[]" class="form-control form-control-sm item-calc-price" value="0" required></td>
                <td><input type="text" class="form-control form-control-sm item-calc-amount" readonly value="0.00"></td>
                <td><button type="button" class="btn btn-outline-danger btn-sm remove-row-btn">&times;</button></td>
            `;
            voucherItemsTable.appendChild(tr);
            bindVoucherCalculations();
        });
        bindVoucherCalculations();
    }

    // Delegated listener for row removals
    document.addEventListener('click', function (e) {
        if (e.target && e.target.classList.contains('remove-row-btn')) {
            const row = e.target.closest('.diagnosis-row, .medicine-row, .investigation-row, .procedure-row, .voucher-item-row');
            if (row) {
                row.remove();
                if (typeof updateVoucherTotals === 'function') {
                    updateVoucherTotals();
                }
            }
        }
    });
}

function bindVoucherCalculations() {
    const rows = document.querySelectorAll('.voucher-item-row');
    rows.forEach(function (row) {
        const qtyInput = row.querySelector('.item-calc-qty');
        const priceInput = row.querySelector('.item-calc-price');
        const amountInput = row.querySelector('.item-calc-amount');

        function recalcRow() {
            const q = parseFloat(qtyInput.value) || 0;
            const p = parseFloat(priceInput.value) || 0;
            const amt = q * p;
            if (amountInput) amountInput.value = amt.toFixed(2);
            updateVoucherTotals();
        }

        if (qtyInput) qtyInput.addEventListener('input', recalcRow);
        if (priceInput) priceInput.addEventListener('input', recalcRow);
    });

    const discountInput = document.getElementById('voucher_discount');
    if (discountInput) {
        discountInput.addEventListener('input', updateVoucherTotals);
    }
}

function updateVoucherTotals() {
    const rows = document.querySelectorAll('.voucher-item-row');
    let subtotal = 0;
    rows.forEach(function (row) {
        const amtInput = row.querySelector('.item-calc-amount');
        if (amtInput) {
            subtotal += parseFloat(amtInput.value) || 0;
        }
    });

    const discountInput = document.getElementById('voucher_discount');
    const discount = parseFloat(discountInput ? discountInput.value : 0) || 0;
    const total = Math.max(0, subtotal - discount);

    const subtotalDisplay = document.getElementById('voucher_subtotal_display');
    const totalDisplay = document.getElementById('voucher_total_display');

    if (subtotalDisplay) subtotalDisplay.innerText = subtotal.toFixed(2);
    if (totalDisplay) totalDisplay.innerText = total.toFixed(2);
}

/**
 * Settings: Registration Number Live Preview
 */
function initSettingsPreview() {
    const patternInput = document.getElementById('format_pattern');
    const nextInput = document.getElementById('next_number');
    const paddingInput = document.getElementById('padding');
    const previewDisplay = document.getElementById('reg_live_preview');

    if (!patternInput || !previewDisplay) return;

    function updatePreview() {
        const pattern = patternInput.value || 'REG-{YYYY}-{NUMBER}';
        const num = parseInt(nextInput ? nextInput.value : 1) || 1;
        const pad = parseInt(paddingInput ? paddingInput.value : 6) || 6;

        const now = new Date();
        const yyyy = String(now.getFullYear());
        const yy = String(now.getFullYear()).slice(-2);
        const mm = String(now.getMonth() + 1).padStart(2, '0');
        const dd = String(now.getDate()).padStart(2, '0');
        const numStr = String(num).padStart(pad, '0');

        let res = pattern
            .replace('{NUMBER}', numStr)
            .replace('{YYYY}', yyyy)
            .replace('{YY}', yy)
            .replace('{MM}', mm)
            .replace('{DD}', dd);

        previewDisplay.innerText = res;
    }

    patternInput.addEventListener('input', updatePreview);
    if (nextInput) nextInput.addEventListener('input', updatePreview);
    if (paddingInput) paddingInput.addEventListener('input', updatePreview);
    updatePreview();
}

