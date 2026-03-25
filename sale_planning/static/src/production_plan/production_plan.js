/** @odoo-module **/

import { registry } from "@web/core/registry";
import { Component, onWillStart, onWillUpdateProps, useState, useEnv } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";
import { formatCurrency } from "@web/core/currency";
import { _t } from "@web/core/l10n/translation";
import { SelectCreateDialog } from "@web/views/view_dialogs/select_create_dialog";

export class ProductionPlanDashboard extends Component {
    static template = "mrp_production_plan.Dashboard";

    /**
     * The component is registered as a client action (ir.actions.client with
     * tag "mrp_production_plan.dashboard"). Props are: action, actionId,
     * updateActionState, className. The plan_id comes from action.context.
     */
    _resolveplanId() {
        // Primary: URL hash (set by direct navigation from demand forecast)
        const hash = window.location.hash;
        const hashMatch = hash.match(/mpp_plan_id=(\d+)/);
        if (hashMatch) {
            console.log("PLAN resolved from URL hash:", hashMatch[1]);
            return parseInt(hashMatch[1]);
        }
        
        // Secondary: sessionStorage (written just before navigation)
        const stored = sessionStorage.getItem("mpp_target_plan_id");
        if (stored) {
            const id = parseInt(stored);
            sessionStorage.removeItem("mpp_target_plan_id");
            console.log("PLAN resolved from sessionStorage:", id);
            return id;
        }
        
        // Fallback: action context (set by create_from_forecast)
        const ctxId = this.props.action?.context?.plan_id;
        if (ctxId) return ctxId;
        
        return null;
    }


    setup() {
        this.orm = useService("orm");
        this.env = useEnv();
        this.planId = null;
        this.planName = "Lập kế hoạch sản xuất";
        this.action = useService("action");
        this.notification = useService("notification");
        this.dialog = useService("dialog");
        this.state = useState({
            loading: true,
            months: [],
            rows: [],
            filters: {},
            editing: null,
        });

        onWillStart(async () => {
            // === DIAGNOSTIC: Log everything we can find ===
            try {
                console.log("=== PROPS KEYS:", Object.keys(this.props).join(", "));
                console.log("=== props.value:", this.props.value);
                console.log("=== props.name:", this.props.name);
                console.log("=== props.record:", this.props.record);
                console.log("=== props.record?.resId:", this.props.record?.resId);
                console.log("=== props.record?.data?:", this.props.record?.data);
                console.log("=== props.action:", this.props.action);
                console.log("=== props.action?.context:", this.props.action?.context);
                const routerSvc = this.env?.services?.router || this.env?.router;
                console.log("=== router current hash:", routerSvc?.current?.hash);
                const actionSvc = this.env?.services?.action;
                console.log("=== action service currentController:", actionSvc?.currentController);
            } catch(e) { console.warn("DIAGNOSTIC ERROR:", e); }
            // ===============================================
            
            this.planId = this._resolveplanId();
            console.log("PLAN SETUP - resolved planId:", this.planId);
            await this.load();
        });

        onWillUpdateProps(async (nextProps) => {
            // When doAction is called on an already-mounted component, Odoo
            // triggers onWillUpdateProps instead of remounting. Read from sessionStorage.
            const stored = sessionStorage.getItem("mpp_target_plan_id");
            const nextId = (stored ? parseInt(stored) : null)
                || nextProps.action?.context?.plan_id;
            if (stored) sessionStorage.removeItem("mpp_target_plan_id");
            console.log("onWillUpdateProps - nextId:", nextId, "| stored:", stored);
            if (nextId && nextId !== this.planId) {
                this.planId = nextId;
                await this.load();
            } else if (nextId && nextId === this.planId) {
                // Same plan, still reload to refresh data
                await this.load();
            }
        });

        this.onCellClick = this.onCellClick.bind(this);
        this.onAddProduct = this.onAddProduct.bind(this);
        this.onCellBlur = this.onCellBlur.bind(this);
        this.onCellKeyDown = this.onCellKeyDown.bind(this);
        this.isEditing = this.isEditing.bind(this);
    }

    formatNumber(value) {
        if (value === null || value === undefined) return "0";
        const n = Number(value);
        if (Number.isNaN(n)) return String(value);
        return n.toLocaleString("vi-VN");
    }

    async load() {
        try {
            this.state.loading = true;
            
            // Always re-resolve in case model is now populated
            const resolvedId = this._resolveplanId();
            if (resolvedId) this.planId = resolvedId;
            
            console.log("PRODUCTION PLAN LOAD - planId:", this.planId, "| env model root:", this.env?.model?.root?.resId);
            const data = await this.orm.call(
                "mrp.production.plan.dashboard",
                "get_dashboard_data",
                [],
                { filters: { ...this.state.filters, plan_id: this.planId } }
            );
            console.log("PRODUCTION PLAN DATA RECEIVED:", data);
            this.state.months = data.months;
            this.state.rows = data.rows;
        } finally {
            this.state.loading = false;
        }
    }

    async onAddProduct() {
        this.action.doAction("sale_planning.action_production_plan_wizard", {
            additionalContext: { default_plan_id: this.planId },
            onClose: () => this.load(),
        });
    }

    isEditing(rowId, label, monthIndex) {
        return this.state.editing && 
               this.state.editing.rowId === rowId && 
               this.state.editing.label === label && 
               this.state.editing.monthIndex === monthIndex;
    }

    onCellClick(rowId, label, monthIndex) {
        // Only allow editing for forecast and replenishment
        if (label.indexOf('Tồn kho') !== -1) return;
        this.state.editing = { rowId, label, monthIndex };
    }

    onCellBlur(ev, rowId, label, monthIndex) {
        this.updateCellValue(rowId, label, monthIndex, ev.target.value);
        this.state.editing = null;
    }

    onCellKeyDown(ev, rowId, label, monthIndex) {
        if (ev.key === "Enter") {
            this.updateCellValue(rowId, label, monthIndex, ev.target.value);
            this.state.editing = null;
        } else if (ev.key === "Escape") {
            this.state.editing = null;
        }
    }

    updateCellValue(rowId, label, monthIndex, value) {
        const row = this.state.rows.find(r => r.id === rowId);
        if (!row) return;

        const newValue = parseFloat(value) || 0;
        
        if (label === 'product') {
            row.values[monthIndex] = newValue;
        } else {
            const subRow = row.sub_rows.find(sr => sr.label === label);
            if (!subRow) return;
            subRow.values[monthIndex] = newValue;
        }

        this.recalculateRow(row);
    }

    recalculateRow(row) {
        const forecastRow = row.sub_rows.find(sr => sr.label.indexOf('Nhu cầu') === 0);
        const indirectRow = row.sub_rows.find(sr => sr.label.indexOf('Dự báo') === 0);
        const replenishRow = row.sub_rows.find(sr => sr.label.indexOf('Bổ sung') === 0);
        const stockRow = row.sub_rows.find(sr => sr.label.indexOf('Tồn kho') === 0);

        if (!forecastRow || !replenishRow || !stockRow) return;

        // Forecasted Inventory = Previous (Actual) stock + Replenish - Forecast Demand
        let prevStock = row.actual_stock || 0; 
        
        for (let i = 0; i < this.state.months.length; i++) {
            const demand = forecastRow.values[i] || 0;
            const indirect = indirectRow ? (indirectRow.values[i] || 0) : 0;
            const replenish = replenishRow.values[i] || 0;
            
            stockRow.values[i] = prevStock + replenish - demand - indirect;
            prevStock = stockRow.values[i];
        }
    }
}

registry.category("actions").add("mrp_production_plan.dashboard", ProductionPlanDashboard);
registry.category("fields").add("production_plan_dashboard_widget", {
    component: ProductionPlanDashboard,
});
