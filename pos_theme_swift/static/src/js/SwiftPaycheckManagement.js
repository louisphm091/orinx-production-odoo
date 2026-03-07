/** @odoo-module **/

import { registry } from "@web/core/registry";
import { Component, onMounted, useState } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";
import { _t } from "@web/core/l10n/translation";

export class SwiftPaycheckManagement extends Component {
    static template = "pos_theme_swift.SwiftPaycheckManagement";

    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");

        this.state = useState({
            loading: true,
            paycheckRecords: [],
            paycheckSearch: "",
            expandedPaycheckId: null,
            paycheckTab: "info",
            showPaymentModal: false,
            paymentMethod: "cash",
            paymentTime: "",
            paymentNote: "",
        });

        this._searchTimer = null;

        this.togglePaycheckDetail = this.togglePaycheckDetail.bind(this);
        this.setPaycheckTab = this.setPaycheckTab.bind(this);
        this.openPaymentModal = this.openPaymentModal.bind(this);
        this.closePaymentModal = this.closePaymentModal.bind(this);
        this.createPaySlip = this.createPaySlip.bind(this);
        this.onSearchInput = this.onSearchInput.bind(this);
        this.createPaycheck = this.createPaycheck.bind(this);
        this.loadPaychecks = this.loadPaychecks.bind(this);

        onMounted(async () => {
            await this.loadPaychecks();
        });
    }

    formatMoney(value) {
        return Number(value || 0).toLocaleString("en-US");
    }

    getSummaryTotals() {
        const total = this.state.paycheckRecords.reduce((acc, r) => acc + Number(r.totalSalary || 0), 0);
        const paid = this.state.paycheckRecords.reduce((acc, r) => acc + Number(r.paidToEmployee || 0), 0);
        const remaining = this.state.paycheckRecords.reduce((acc, r) => acc + Number(r.remaining || 0), 0);
        return { total, paid, remaining };
    }

    getExpandedRecord() {
        return this.state.paycheckRecords.find((r) => r.id === this.state.expandedPaycheckId) || null;
    }

    async loadPaychecks() {
        this.state.loading = true;
        try {
            const records = await this.orm.call(
                "pos.dashboard.swift",
                "get_paycheck_records",
                [this.state.paycheckSearch || ""]
            );
            this.state.paycheckRecords = records || [];
            if (this.state.expandedPaycheckId) {
                const found = this.state.paycheckRecords.some((r) => r.id === this.state.expandedPaycheckId);
                if (!found) {
                    this.state.expandedPaycheckId = null;
                }
            }
        } catch (e) {
            console.error("loadPaychecks failed", e);
            this.notification.add(_t("Cannot load paycheck data"), { type: "danger" });
        } finally {
            this.state.loading = false;
        }
    }

    onSearchInput(ev) {
        this.state.paycheckSearch = ev.target.value;
        clearTimeout(this._searchTimer);
        this._searchTimer = setTimeout(() => this.loadPaychecks(), 250);
    }

    togglePaycheckDetail(id) {
        this.state.expandedPaycheckId = this.state.expandedPaycheckId === id ? null : id;
        this.state.paycheckTab = "info";
    }

    setPaycheckTab(tab) {
        this.state.paycheckTab = tab;
    }

    async createPaycheck() {
        try {
            await this.orm.call("pos.dashboard.swift", "action_create_paycheck", []);
            await this.loadPaychecks();
            this.notification.add(_t("Paycheck created"), { type: "success" });
        } catch (e) {
            console.error("createPaycheck failed", e);
            this.notification.add(_t("Cannot create paycheck"), { type: "danger" });
        }
    }

    openPaymentModal() {
        const rec = this.getExpandedRecord();
        if (!rec) {
            return;
        }
        if (Number(rec.remaining || 0) <= 0) {
            this.notification.add(_t("No remaining amount to pay"), { type: "info" });
            return;
        }
        this.state.paymentMethod = "cash";
        this.state.paymentNote = "";
        this.state.paymentTime = new Date().toLocaleString("vi-VN");
        this.state.showPaymentModal = true;
    }

    closePaymentModal() {
        this.state.showPaymentModal = false;
    }

    async createPaySlip() {
        const rec = this.getExpandedRecord();
        if (!rec) {
            this.state.showPaymentModal = false;
            return;
        }
        try {
            const result = await this.orm.call(
                "pos.dashboard.swift",
                "action_paycheck_pay",
                [rec.id, this.state.paymentMethod, this.state.paymentNote || ""]
            );
            if (!result || !result.ok) {
                this.notification.add((result && result.message) || _t("Payment failed"), { type: "warning" });
                return;
            }
            this.notification.add(_t("Payslip created"), { type: "success" });
            this.state.showPaymentModal = false;
            await this.loadPaychecks();
        } catch (e) {
            console.error("createPaySlip failed", e);
            this.notification.add(_t("Payment failed"), { type: "danger" });
        }
    }
}

registry.category("actions").add("pos_theme_swift.swift_pos_paycheck_management", SwiftPaycheckManagement);
