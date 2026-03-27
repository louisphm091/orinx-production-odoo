/** @odoo-module **/

import { registry } from "@web/core/registry";
import { Component, onMounted, onWillUnmount, useState } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";
import { _t } from "@web/core/l10n/translation";

const EMPLOYEE_MANAGEMENT_TRANSLATION_TERMS = [
    _t("-- Create New Employee --"),
    _t("A polished workspace to manage employee profiles and monitor daily check-in / check-out in one place."),
    _t("Action"),
    _t("Active Shifts"),
    _t("Add Advance"),
    _t("Add Debt"),
    _t("Add Debt and Advance"),
    _t("Add New Employee"),
    _t("Edit Employee"),
    _t("Add a checkin note (optional)..."),
    _t("Add a checkout note..."),
    _t("Advance"),
    _t("Advanced Setting"),
    _t("All branches"),
    _t("All departments"),
    _t("All job titles"),
    _t("Amount"),
    _t("Attendance Code"),
    _t("Birth Date"),
    _t("By month"),
    _t("By working hour"),
    _t("By working shift"),
    _t("Cancel"),
    _t("Check In"),
    _t("Check Out"),
    _t("Checked Out"),
    _t("Date"),
    _t("Debt"),
    _t("Debt/Advance"),
    _t("Debt/Advance Balance:"),
    _t("Delete Employee"),
    _t("Department"),
    _t("Employee"),
    _t("Employee Code"),
    _t("Employee Directory"),
    _t("Employee Management"),
    _t("Employee Name"),
    _t("Employee Status"),
    _t("Employee updated"),
    _t("Female"),
    _t("Gender"),
    _t("ID Number"),
    _t("Image"),
    _t("Info"),
    _t("Job Title"),
    _t("Position"),
    _t("Loading check-in / check-out board..."),
    _t("Loading data..."),
    _t("Male"),
    _t("Manage Staff and Shift Attendance"),
    _t("Mark as Off"),
    _t("Mark as Working"),
    _t("Name"),
    _t("No action"),
    _t("No attendance records for this day."),
    _t("No debt/advance data available."),
    _t("No employee data found."),
    _t("No payslips available."),
    _t("No work schedule for this week."),
    _t("Note"),
    _t("Notes"),
    _t("Off"),
    _t("Off Staff"),
    _t("Overtime Salary"),
    _t("Paid"),
    _t("Pay Branch"),
    _t("Payment"),
    _t("Payslip"),
    _t("Period"),
    _t("Phone Number"),
    _t("Record Payment"),
    _t("Remaining"),
    _t("Salary Amount"),
    _t("Salary Setup"),
    _t("Salary Type"),
    _t("Save"),
    _t("Schedule"),
    _t("Search by code, employee name"),
    _t("Select branch"),
    _t("Select position"),
    _t("Select from existing users"),
    _t("No position available."),
    _t("Please select a position"),
    _t("Please select an employee"),
    _t("Shift"),
    _t("Slip code"),
    _t("Staff Check-in / Check-out Tracker"),
    _t("Status"),
    _t("Total salary"),
    _t("Track attendance by day and operate check-in or check-out directly from the board."),
    _t("Type"),
    _t("Update"),
    _t("Update Employee"),
    _t("Work Branch"),
    _t("Working"),
    _t("Working Staff"),
    _t("Working Time"),
    _t("hour"),
    _t("month"),
    _t("shift"),
    _t("Cannot update employee"),
    _t("Name is required"),
    _t("Phone Number is required"),
    _t("Birth Date is required"),
    _t("Salary Amount is required"),
    _t("Job Title is required"),
    _t("Get Verification Code"),
    _t("Verification Code"),
    _t("This verification code expires in %s."),
    _t("Code expired. Please generate a new verification code."),
    _t("Cannot generate verification code"),
    _t("Verification code copied"),
    _t("Copy"),
    _t("Confirm Check In"),
    _t("Confirm Check Out"),
    _t("Not Checked In"),
    _t("Employee code"),
    _t("Image"),
    _t("Attendance Code"),
];

void EMPLOYEE_MANAGEMENT_TRANSLATION_TERMS;

export class SwiftEmployeeManagement extends Component {
    static template = "pos_theme_swift.SwiftEmployeeManagement";

    setup() {
        this._t = _t;
        this.orm = useService("orm");
        this.notification = useService("notification");

        this.state = useState({
            loading: true,
            attendanceLoading: true,
            keyword: "",
            status: "working",
            rows: [],
            attendanceRows: [],
            attendanceDate: new Date().toISOString().slice(0, 10),
            selectedUserId: null,
            detail: null,
            activeTab: "info",
            showCreateModal: false,
            formMode: "create",
            showFinanceModal: false,
            showAttendanceModal: false,
            availableUsers: [],
            branches: [],
            filterOptions: {
                workBranches: [],
                payBranches: [],
                departments: [],
                jobTitles: [],
            },
            filters: {
                workBranch: "",
                payBranch: "",
                department: "",
                jobTitle: "",
            },
            createForm: {
                userId: "",
                name: "",
                phone: "",
                idNumber: "",
                birthDate: "",
                gender: "",
                department: "",
                jobTitle: "",
                workBranch: "",
                payBranch: "",
                salaryType: "hour",
                salaryAmount: 0,
                advancedSetting: false,
                overtimeEnabled: false,
                password: "",
            },
            showAccessCodeModal: false,
            accessCodeData: null,
            financeForm: {
                type: "advance",
                amount: 0,
                note: "",
            },
            attendanceForm: {
                actionName: "",
                userId: null,
                employeeName: "",
                note: "",
            },
        });

        this._searchTimer = null;

        this.loadData = this.loadData.bind(this);
        this.onSearchInput = this.onSearchInput.bind(this);
        this.setStatus = this.setStatus.bind(this);
        this.onFilterChange = this.onFilterChange.bind(this);
        this.onAttendanceDateChange = this.onAttendanceDateChange.bind(this);
        this.loadAttendanceBoard = this.loadAttendanceBoard.bind(this);
        this.openAttendanceModal = this.openAttendanceModal.bind(this);
        this.closeAttendanceModal = this.closeAttendanceModal.bind(this);
        this.confirmAttendanceAction = this.confirmAttendanceAction.bind(this);
        this.selectRow = this.selectRow.bind(this);
        this.setTab = this.setTab.bind(this);
        this.openCreate = this.openCreate.bind(this);
        this.closeCreate = this.closeCreate.bind(this);
        this.saveCreate = this.saveCreate.bind(this);
        this.saveSalary = this.saveSalary.bind(this);
        this.generateAccessCode = this.generateAccessCode.bind(this);
        this.closeAccessCodeModal = this.closeAccessCodeModal.bind(this);
        this.copyAccessCode = this.copyAccessCode.bind(this);
        this.openFinance = this.openFinance.bind(this);
        this.closeFinance = this.closeFinance.bind(this);
        this.saveFinance = this.saveFinance.bind(this);
        this.markSelectedOff = this.markSelectedOff.bind(this);
        this.markSelectedWorking = this.markSelectedWorking.bind(this);
        this.deleteSelectedEmployee = this.deleteSelectedEmployee.bind(this);
        this.onCreateSalaryInput = this.onCreateSalaryInput.bind(this);
        this.onDetailSalaryInput = this.onDetailSalaryInput.bind(this);
        this.loadAvailableUsers = this.loadAvailableUsers.bind(this);
        this.loadBranches = this.loadBranches.bind(this);
        this.loadFilterOptions = this.loadFilterOptions.bind(this);
        this.onSelectAvailableUser = this.onSelectAvailableUser.bind(this);
        this._accessCodeTimer = null;

        onMounted(async () => {
            await Promise.all([this.loadFilterOptions(), this.loadData(), this.loadAttendanceBoard()]);
        });
        onWillUnmount(() => this._clearAccessCodeTimer());
    }

    _swiftLangCode() {
        return (this.env?.context?.lang || document.documentElement.lang || navigator.language || "en_US")
            .replace("-", "_")
            .slice(0, 5)
            .toLowerCase();
    }

    _swiftText(text) {
        return this._t(text);
    }

    formatMoney(v) {
        return Number(v || 0).toLocaleString("vi-VN");
    }

    parseCurrencyInput(rawValue) {
        const digits = String(rawValue || "").replace(/[^\d]/g, "");
        return digits ? Number(digits) : 0;
    }

    getInitials(name) {
        return String(name || "")
            .trim()
            .split(/\s+/)
            .slice(0, 2)
            .map((part) => part.charAt(0).toUpperCase())
            .join("") || "--";
    }

    getAttendanceToneClass(tone) {
        return `is-${tone || "muted"}`;
    }

    getGenderLabel(gender) {
        if (gender === "male") {
            return this._t("Male");
        }
        if (gender === "female") {
            return this._t("Female");
        }
        return gender || "-";
    }

    getWorkingCount() {
        return this.state.status === "working" ? this.state.rows.length : 0;
    }

    getOffCount() {
        return this.state.status === "off" ? this.state.rows.length : 0;
    }

    getActiveShiftCount() {
        return this.state.attendanceRows.filter((row) => row.statusTone === "warning").length;
    }

    getAttendanceReadyCount() {
        return this.state.attendanceRows.filter((row) => row.statusTone === "success").length;
    }

    getAttendanceModalTitle() {
        return this.state.attendanceForm.actionName === "action_employee_checkin"
            ? this._t("Confirm Check In")
            : this._t("Confirm Check Out");
    }

    getAttendanceModalConfirmLabel() {
        return this.state.attendanceForm.actionName === "action_employee_checkin"
            ? this._t("Check In")
            : this._t("Check Out");
    }

    async loadData() {
        this.state.loading = true;
        try {
            const data = await this.orm.call("pos.dashboard.swift", "get_employee_list_data", [
                this.state.keyword || "",
                this.state.status,
                this.state.filters,
            ]);
            this.state.rows = data.rows || [];
            if (this.state.selectedUserId) {
                const exists = this.state.rows.some((r) => r.userId === this.state.selectedUserId);
                if (!exists) {
                    this.state.selectedUserId = null;
                    this.state.detail = null;
                }
            }
        } catch (e) {
            console.error("load employee data failed", e);
            this.notification.add(_t("Cannot load employee data"), { type: "danger" });
        } finally {
            this.state.loading = false;
        }
    }

    onSearchInput(ev) {
        this.state.keyword = ev.target.value;
        clearTimeout(this._searchTimer);
        this._searchTimer = setTimeout(() => {
            this.loadData();
            this.loadAttendanceBoard();
        }, 250);
    }

    async setStatus(status) {
        this.state.status = status;
        await this.loadData();
    }

    async onFilterChange(field, value) {
        this.state.filters[field] = value || "";
        await Promise.all([this.loadData(), this.loadAttendanceBoard()]);
    }

    async onAttendanceDateChange(ev) {
        this.state.attendanceDate = ev.target.value;
        await this.loadAttendanceBoard();
    }

    async loadAttendanceBoard() {
        this.state.attendanceLoading = true;
        try {
            const data = await this.orm.call("pos.dashboard.swift", "get_employee_checkin_board", [
                this.state.attendanceDate,
                this.state.filters,
                this.state.keyword || "",
            ]);
            this.state.attendanceRows = data.rows || [];
        } catch (e) {
            console.error("load attendance board failed", e);
            this.notification.add(_t("Cannot load check-in/check-out board"), { type: "danger" });
            this.state.attendanceRows = [];
        } finally {
            this.state.attendanceLoading = false;
        }
    }

    openAttendanceModal(actionName, row) {
        this.state.attendanceForm.actionName = actionName;
        this.state.attendanceForm.userId = row.userId;
        this.state.attendanceForm.employeeName = row.employeeName;
        this.state.attendanceForm.note = "";
        this.state.showAttendanceModal = true;
    }

    closeAttendanceModal() {
        this.state.showAttendanceModal = false;
        this.state.attendanceForm.actionName = "";
        this.state.attendanceForm.userId = null;
        this.state.attendanceForm.employeeName = "";
        this.state.attendanceForm.note = "";
    }

    async confirmAttendanceAction() {
        const actionName = this.state.attendanceForm.actionName;
        const userId = this.state.attendanceForm.userId;
        const note = this.state.attendanceForm.note || "";
        if (!actionName || !userId) {
            return;
        }
        try {
            const res = await this.orm.call("pos.dashboard.swift", actionName, [userId, note]);
            if (!res || !res.ok) {
                this.notification.add((res && res.message) || _t("Cannot update check-in/check-out status"), { type: "warning" });
                return;
            }
            this.notification.add(
                actionName === "action_employee_checkin" ? _t("Employee checked in") : _t("Employee checked out"),
                { type: "success" }
            );
            this.closeAttendanceModal();
            await this.loadAttendanceBoard();
        } catch (e) {
            console.error("confirmAttendanceAction failed", e);
            this.notification.add(_t("Cannot update check-in/check-out status"), { type: "danger" });
        }
    }

    async selectRow(row) {
        if (this.state.selectedUserId === row.userId) {
            this.state.selectedUserId = null;
            this.state.detail = null;
            return;
        }
        this.state.selectedUserId = row.userId;
        this.state.activeTab = "info";
        this.closeAccessCodeModal();
        try {
            const data = await this.orm.call("pos.dashboard.swift", "get_employee_detail_data", [row.userId]);
            if (!data || !data.ok) {
                this.notification.add((data && data.message) || _t("Cannot load employee detail"), { type: "warning" });
                this.state.detail = null;
                return;
            }
            this.state.detail = data;
            this.state.detail.profile.salaryAmount = this.parseCurrencyInput(this.state.detail.profile.salaryAmount);
        } catch (e) {
            console.error("load employee detail failed", e);
            this.notification.add(_t("Cannot load employee detail"), { type: "danger" });
            this.state.detail = null;
        }
    }

    setTab(tab) {
        this.state.activeTab = tab;
    }

    resetCreateForm() {
        this.state.createForm = {
            userId: "",
            name: "",
            phone: "",
            idNumber: "",
            birthDate: "",
            gender: "",
            department: "",
            jobTitle: "",
            workBranch: "",
            payBranch: "",
            salaryType: "hour",
            salaryAmount: 0,
            advancedSetting: false,
            overtimeEnabled: false,
            password: "",
        };
    }

    async openCreate() {
        this.resetCreateForm();
        this.state.formMode = "create";
        this.state.showCreateModal = true;
        await Promise.all([this.loadAvailableUsers(), this.loadBranches()]);
    }

    _resolveJobTitleId(jobTitleName) {
        const selected = this.state.filterOptions.jobTitles.find(
            (jobTitle) => jobTitle.name === (jobTitleName || "")
        );
        return selected ? selected.id : (jobTitleName || "");
    }

    async openEditEmployee() {
        if (!this.state.selectedUserId || !this.state.detail) {
            this.notification.add(_t("Please select an employee"), { type: "warning" });
            return;
        }
        const profile = this.state.detail.profile || {};
        this.state.formMode = "edit";
        this.state.createForm = {
            userId: this.state.selectedUserId,
            name: profile.name || "",
            phone: profile.phone || "",
            idNumber: profile.idNumber || "",
            birthDate: profile.birthDate || "",
            gender: profile.gender || "",
            department: profile.department || "",
            jobTitle: this._resolveJobTitleId(profile.jobTitle),
            workBranch: profile.workBranch || "",
            payBranch: profile.payBranch || "",
            salaryType: profile.salaryType || "hour",
            salaryAmount: this.parseCurrencyInput(profile.salaryAmount),
            advancedSetting: Boolean(profile.advancedSetting),
            overtimeEnabled: Boolean(profile.overtimeEnabled),
            password: "",
        };
        this.state.showCreateModal = true;
        await Promise.all([this.loadFilterOptions(), this.loadBranches()]);
    }

    closeCreate() {
        this.state.showCreateModal = false;
        this.resetCreateForm();
        this.state.formMode = "create";
    }

    async loadAvailableUsers() {
        try {
            const res = await this.orm.call("pos.dashboard.swift", "get_available_employee_users", [""]);
            this.state.availableUsers = res.rows || [];
        } catch (e) {
            console.error("load available users failed", e);
            this.state.availableUsers = [];
        }
    }

    async loadBranches() {
        try {
            const res = await this.orm.call("pos.dashboard.swift", "get_employee_branch_options", []);
            this.state.branches = res.rows || [];
            const firstBranch = this.state.branches[0]?.name || "";
            if (!this.state.createForm.workBranch) {
                this.state.createForm.workBranch = firstBranch;
            }
            if (!this.state.createForm.payBranch) {
                this.state.createForm.payBranch = firstBranch;
            }
        } catch (e) {
            console.error("load employee branches failed", e);
            this.state.branches = [];
        }
    }

    async loadFilterOptions() {
        try {
            const res = await this.orm.call("pos.dashboard.swift", "get_employee_filter_options", []);
            this.state.filterOptions = {
                workBranches: res.workBranches || [],
                payBranches: res.payBranches || [],
                departments: res.departments || [],
                jobTitles: res.jobTitles || [],
            };
        } catch (e) {
            console.error("load employee filter options failed", e);
            this.state.filterOptions = {
                workBranches: [],
                payBranches: [],
                departments: [],
                jobTitles: [],
            };
        }
    }

    onSelectAvailableUser(ev) {
        const userId = Number(ev.target.value || 0);
        this.state.createForm.userId = userId || "";
        if (!userId) {
            return;
        }
        const selected = this.state.availableUsers.find((u) => u.userId === userId);
        if (!selected) {
            return;
        }
        this.state.createForm.name = selected.name || "";
        this.state.createForm.phone = selected.phone || "";
    }

    async saveCreate() {
        try {
            const requiredFields = [
                { key: "name", label: _t("Name is required") },
                { key: "phone", label: _t("Phone Number is required") },
            ];
            for (const field of requiredFields) {
                const value = this.state.createForm[field.key];
                if (!String(value || "").trim()) {
                    this.notification.add(field.label, { type: "warning" });
                    return;
                }
            }
            const selectedJobTitleId = String(this.state.createForm.jobTitle || "").trim();
            const selectedJobTitle = this.state.filterOptions.jobTitles.find(
                (jobTitle) => String(jobTitle.id) === selectedJobTitleId
            );
            this.state.createForm.jobTitle = selectedJobTitle ? selectedJobTitle.name : selectedJobTitleId;
            this.state.createForm.salaryAmount = this.parseCurrencyInput(this.state.createForm.salaryAmount);
            const isEditMode = this.state.formMode === "edit";
            const methodName = isEditMode ? "update_employee_record" : "create_employee_record";
            const payload = isEditMode ? [this.state.selectedUserId, this.state.createForm] : [this.state.createForm];
            const res = await this.orm.call("pos.dashboard.swift", methodName, payload);
            if (!res || !res.ok) {
                this.notification.add(
                    (res && res.message) || (isEditMode ? _t("Cannot update employee") : _t("Cannot create employee")),
                    { type: "warning" }
                );
                return;
            }
            this.notification.add(
                isEditMode
                    ? _t("Employee updated")
                    : ((res && res.createdNewUser) ? _t("Employee created") : _t("Employee added from existing user")),
                { type: "success" }
            );
            const refreshedUserId = this.state.selectedUserId;
            this.state.showCreateModal = false;
            this.resetCreateForm();
            this.state.formMode = "create";
            await this.loadFilterOptions();
            await this.loadData();
            if (isEditMode && refreshedUserId) {
                this.state.selectedUserId = null;
                await this.selectRow({ userId: refreshedUserId });
            }
        } catch (e) {
            console.error("saveCreate failed", e);
            this.notification.add(
                this.state.formMode === "edit" ? _t("Cannot update employee") : _t("Cannot create employee"),
                { type: "danger" }
            );
        }
    }

    async saveSalary() {
        if (!this.state.selectedUserId || !this.state.detail) {
            return;
        }
        try {
            const p = this.state.detail.profile;
            p.salaryAmount = this.parseCurrencyInput(p.salaryAmount);
            const res = await this.orm.call("pos.dashboard.swift", "update_employee_salary_setup", [this.state.selectedUserId, {
                salaryType: p.salaryType,
                salaryAmount: p.salaryAmount,
                advancedSetting: p.advancedSetting,
                overtimeEnabled: p.overtimeEnabled,
            }]);
            if (!res || !res.ok) {
                this.notification.add((res && res.message) || _t("Cannot save salary setup"), { type: "warning" });
                return;
            }
            this.notification.add(_t("Salary setup updated"), { type: "success" });
            await this.selectRow({ userId: this.state.selectedUserId });
        } catch (e) {
            console.error("saveSalary failed", e);
            this.notification.add(_t("Cannot save salary setup"), { type: "danger" });
        }
    }

    _clearAccessCodeTimer() {
        if (this._accessCodeTimer) {
            clearInterval(this._accessCodeTimer);
            this._accessCodeTimer = null;
        }
    }

    _syncAccessCodeCountdown() {
        const data = this.state.accessCodeData;
        if (!data) {
            this._clearAccessCodeTimer();
            return;
        }
        if ((data.remainingSeconds || 0) <= 0) {
            this.state.accessCodeData = {
                ...data,
                remainingSeconds: 0,
            };
            this._clearAccessCodeTimer();
            return;
        }
        this.state.accessCodeData.remainingSeconds -= 1;
    }

    _startAccessCodeTimer() {
        this._clearAccessCodeTimer();
        if (!this.state.accessCodeData || !this.state.accessCodeData.remainingSeconds) {
            return;
        }
        this._accessCodeTimer = setInterval(() => this._syncAccessCodeCountdown(), 1000);
    }

    formatAccessCodeCountdown(seconds) {
        const total = Math.max(Number(seconds || 0), 0);
        const mins = String(Math.floor(total / 60)).padStart(2, "0");
        const secs = String(total % 60).padStart(2, "0");
        return `${mins}:${secs}`;
    }

    async generateAccessCode() {
        if (!this.state.selectedUserId || !this.state.detail) {
            this.notification.add(_t("Please select an employee"), { type: "warning" });
            return;
        }
        try {
            const res = await this.orm.call("pos.dashboard.swift", "generate_employee_access_code", [this.state.selectedUserId]);
            if (!res || !res.ok) {
                this.notification.add((res && res.message) || _t("Cannot generate verification code"), { type: "warning" });
                return;
            }
            this.state.accessCodeData = res.accessCode || null;
            this.state.showAccessCodeModal = true;
            if (this.state.detail?.profile) {
                this.state.detail.profile.accessCode = res.accessCode || null;
            }
            this._startAccessCodeTimer();
        } catch (e) {
            console.error("generateAccessCode failed", e);
            this.notification.add(_t("Cannot generate verification code"), { type: "danger" });
        }
    }

    closeAccessCodeModal() {
        this.state.showAccessCodeModal = false;
        this._clearAccessCodeTimer();
    }

    async copyAccessCode() {
        const code = this.state.accessCodeData?.code;
        if (!code) {
            return;
        }
        try {
            await navigator.clipboard.writeText(code);
            this.notification.add(_t("Verification code copied"), { type: "success" });
        } catch {
            // Ignore clipboard issues in unsupported browsers.
        }
    }

    openFinance(type = "advance") {
        this.state.financeForm.type = type;
        this.state.financeForm.amount = 0;
        this.state.financeForm.note = "";
        this.state.showFinanceModal = true;
    }

    closeFinance() {
        this.state.showFinanceModal = false;
    }

    async saveFinance() {
        if (!this.state.selectedUserId) {
            return;
        }
        try {
            const res = await this.orm.call("pos.dashboard.swift", "add_employee_finance_entry", [
                this.state.selectedUserId,
                this.state.financeForm.type,
                this.state.financeForm.amount,
                this.state.financeForm.note,
            ]);
            if (!res || !res.ok) {
                this.notification.add((res && res.message) || _t("Cannot save debt/advance"), { type: "warning" });
                return;
            }
            this.notification.add(_t("Debt/advance saved"), { type: "success" });
            this.state.showFinanceModal = false;
            await this.selectRow({ userId: this.state.selectedUserId });
            await this.loadData();
        } catch (e) {
            console.error("saveFinance failed", e);
            this.notification.add(_t("Cannot save debt/advance"), { type: "danger" });
        }
    }

    async markSelectedOff() {
        if (!this.state.selectedUserId) {
            this.notification.add(_t("Please select an employee"), { type: "warning" });
            return;
        }
        try {
            const res = await this.orm.call("pos.dashboard.swift", "action_set_employee_status", [
                this.state.selectedUserId,
                "off",
            ]);
            if (!res || !res.ok) {
                this.notification.add((res && res.message) || _t("Cannot update employee status"), { type: "warning" });
                return;
            }
            this.notification.add(_t("Employee marked as off"), { type: "success" });
            await Promise.all([this.loadData(), this.loadAttendanceBoard()]);
        } catch (e) {
            console.error("markSelectedOff failed", e);
            this.notification.add(_t("Cannot update employee status"), { type: "danger" });
        }
    }

    async markSelectedWorking() {
        if (!this.state.selectedUserId) {
            this.notification.add(_t("Please select an employee"), { type: "warning" });
            return;
        }
        try {
            const res = await this.orm.call("pos.dashboard.swift", "action_set_employee_status", [
                this.state.selectedUserId,
                "working",
            ]);
            if (!res || !res.ok) {
                this.notification.add((res && res.message) || _t("Cannot update employee status"), { type: "warning" });
                return;
            }
            this.notification.add(_t("Employee marked as working"), { type: "success" });
            await Promise.all([this.loadData(), this.loadAttendanceBoard()]);
        } catch (e) {
            console.error("markSelectedWorking failed", e);
            this.notification.add(_t("Cannot update employee status"), { type: "danger" });
        }
    }

    async deleteSelectedEmployee() {
        if (!this.state.selectedUserId) {
            this.notification.add(_t("Please select an employee"), { type: "warning" });
            return;
        }
        const confirmed = window.confirm(_t("Remove this employee from the employee list?"));
        if (!confirmed) {
            return;
        }
        try {
            const res = await this.orm.call("pos.dashboard.swift", "action_delete_employee_record", [
                this.state.selectedUserId,
            ]);
            if (!res || !res.ok) {
                this.notification.add((res && res.message) || _t("Cannot delete employee"), { type: "warning" });
                return;
            }
            this.notification.add(_t("Employee removed from the list"), { type: "success" });
            this.state.selectedUserId = null;
            this.state.detail = null;
            await this.loadFilterOptions();
            await Promise.all([this.loadData(), this.loadAttendanceBoard()]);
        } catch (e) {
            console.error("deleteSelectedEmployee failed", e);
            this.notification.add(_t("Cannot delete employee"), { type: "danger" });
        }
    }

    onCreateSalaryInput(ev) {
        const amount = this.parseCurrencyInput(ev.target.value);
        this.state.createForm.salaryAmount = amount;
        ev.target.value = this.formatMoney(amount);
    }

    onDetailSalaryInput(ev) {
        if (!this.state.detail) {
            return;
        }
        const amount = this.parseCurrencyInput(ev.target.value);
        this.state.detail.profile.salaryAmount = amount;
        ev.target.value = this.formatMoney(amount);
    }
}

registry.category("actions").add("pos_theme_swift.swift_pos_employee_management", SwiftEmployeeManagement);
