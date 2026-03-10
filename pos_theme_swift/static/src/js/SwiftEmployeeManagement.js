/** @odoo-module **/

import { registry } from "@web/core/registry";
import { Component, onMounted, useState } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";
import { _t } from "@web/core/l10n/translation";

export class SwiftEmployeeManagement extends Component {
    static template = "pos_theme_swift.SwiftEmployeeManagement";

    setup() {
        this._t = _t;
        this.orm = useService("orm");
        this.notification = useService("notification");

        this.state = useState({
            loading: true,
            keyword: "",
            status: "working",
            rows: [],
            selectedUserId: null,
            detail: null,
            activeTab: "info",
            showCreateModal: false,
            showFinanceModal: false,
            availableUsers: [],
            createForm: {
                userId: "",
                name: "",
                phone: "",
                idNumber: "",
                birthDate: "",
                gender: "",
                workBranch: _t("Central Branch"),
                payBranch: _t("Central Branch"),
                salaryType: "hour",
                salaryAmount: 0,
                advancedSetting: false,
                overtimeEnabled: false,
            },
            financeForm: {
                type: "advance",
                amount: 0,
                note: "",
            },
        });

        this._searchTimer = null;

        this.loadData = this.loadData.bind(this);
        this.onSearchInput = this.onSearchInput.bind(this);
        this.setStatus = this.setStatus.bind(this);
        this.selectRow = this.selectRow.bind(this);
        this.setTab = this.setTab.bind(this);
        this.openCreate = this.openCreate.bind(this);
        this.closeCreate = this.closeCreate.bind(this);
        this.saveCreate = this.saveCreate.bind(this);
        this.saveSalary = this.saveSalary.bind(this);
        this.openFinance = this.openFinance.bind(this);
        this.closeFinance = this.closeFinance.bind(this);
        this.saveFinance = this.saveFinance.bind(this);
        this.markSelectedOff = this.markSelectedOff.bind(this);
        this.onCreateSalaryInput = this.onCreateSalaryInput.bind(this);
        this.onDetailSalaryInput = this.onDetailSalaryInput.bind(this);
        this.loadAvailableUsers = this.loadAvailableUsers.bind(this);
        this.onSelectAvailableUser = this.onSelectAvailableUser.bind(this);

        onMounted(async () => {
            await this.loadData();
        });
    }

    formatMoney(v) {
        return Number(v || 0).toLocaleString("vi-VN");
    }

    parseCurrencyInput(rawValue) {
        const digits = String(rawValue || "").replace(/[^\d]/g, "");
        return digits ? Number(digits) : 0;
    }

    async loadData() {
        this.state.loading = true;
        try {
            const data = await this.orm.call("pos.dashboard.swift", "get_employee_list_data", [this.state.keyword || "", this.state.status]);
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
        this._searchTimer = setTimeout(() => this.loadData(), 250);
    }

    async setStatus(status) {
        this.state.status = status;
        await this.loadData();
    }

    async selectRow(row) {
        if (this.state.selectedUserId === row.userId) {
            this.state.selectedUserId = null;
            this.state.detail = null;
            return;
        }
        this.state.selectedUserId = row.userId;
        this.state.activeTab = "info";
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
            workBranch: _t("Central Branch"),
            payBranch: _t("Central Branch"),
            salaryType: "hour",
            salaryAmount: 0,
            advancedSetting: false,
            overtimeEnabled: false,
        };
    }

    async openCreate() {
        this.resetCreateForm();
        this.state.showCreateModal = true;
        await this.loadAvailableUsers();
    }

    closeCreate() {
        this.state.showCreateModal = false;
        this.resetCreateForm();
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
            this.state.createForm.salaryAmount = this.parseCurrencyInput(this.state.createForm.salaryAmount);
            const res = await this.orm.call("pos.dashboard.swift", "create_employee_record", [this.state.createForm]);
            if (!res || !res.ok) {
                this.notification.add((res && res.message) || _t("Cannot create employee"), { type: "warning" });
                return;
            }
            this.notification.add(
                (res && res.createdNewUser) ? _t("Employee created") : _t("Employee added from existing user"),
                { type: "success" }
            );
            this.state.showCreateModal = false;
            this.resetCreateForm();
            await this.loadData();

            // Ensure newly created/linked employee is visible immediately.
            if (res && res.userId && !this.state.rows.some((r) => r.userId === res.userId)) {
                const detail = await this.orm.call("pos.dashboard.swift", "get_employee_detail_data", [res.userId]);
                if (detail && detail.ok && detail.profile) {
                    const p = detail.profile;
                    const status = "working";
                    if (this.state.status === status) {
                        this.state.rows.unshift({
                            userId: res.userId,
                            employeeCode: p.employeeCode,
                            attendanceCode: p.attendanceCode || p.employeeCode,
                            employeeName: p.name || "",
                            phone: p.phone || "",
                            idNumber: p.idNumber || "",
                            debtAdvance: p.debtAdvance || 0,
                            note: "",
                            status,
                        });
                    }
                }
            }
        } catch (e) {
            console.error("saveCreate failed", e);
            this.notification.add(_t("Cannot create employee"), { type: "danger" });
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
            await this.loadData();
        } catch (e) {
            console.error("markSelectedOff failed", e);
            this.notification.add(_t("Cannot update employee status"), { type: "danger" });
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
