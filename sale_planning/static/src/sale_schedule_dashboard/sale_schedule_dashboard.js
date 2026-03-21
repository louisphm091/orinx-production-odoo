/** @odoo-module **/

import { registry } from "@web/core/registry";
import { Component, onWillStart, onMounted, useState } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";
import { _t } from "@web/core/l10n/translation";


export class SaleScheduleDashboard extends Component {
    static template = "sale_planning.SaleScheduleDashboard";

    setup() {
        this._t = _t;
        this.orm = useService("orm");
        this.notification = useService("notification");
        this.action = useService("action");

        this.state = useState({
            loading: true,
            error: null,
            filters: {
                view_mode: "timeline", // timeline | calendar
                group_by: "sku",       // sku | group
                period: "week",        // week | month
                warehouse_id: null,
                category_id: null,
                selected_key: null,
            },
            warehouses: [],
            categories: [],
            kpis: {
                wave_count: 0,
                main_sku: "-",
                revenue: 0,
                revenue_delta: 0,
                risk_sku_count: 0,
                need_review_count: 0,
            },
            timeline: { cols: [], rows: [], view_mode: "timeline" },
            selected: { sku: "-", campaign: "-", sku_code: "-", date_from: "", date_to: "", badges: [] },
            inventory_link: { onhand: 0, daily_sell: 0, out_of_stock_date: "-", out_of_stock_in_days: "-" },
            performance: { title: "-", progress_percent: 0, days: 0 },
            risk_alerts: [],
            last_update: "",
            active_row_key: null,
        });

        onWillStart(async () => {
            await this.load();
        });

        onMounted(() => {
            // nothing heavy here
        });
    }

    // String list for i18n harvester
    static _i18n_strings = [
        _t("SALE SCHEDULING"),
        _t("SKU / SKU Group"),
        _t("Week"),
        _t("Fashion Industry"),
        _t("By SKU"),
        _t("By Campaign"),
        _t("By Time"),
        _t("Create Schedule"),
        _t("Loading data..."),
        _t("waves"),
        _t("Main SKU: "),
        _t("vs plan"),
        _t("Schedule Risk"),
        _t("SKUs at risk of shortage"),
        _t("Schedules Needing Adjust."),
        _t("schedules to review"),
        _t("Sale Schedule Timeline by SKU"),
        _t("Timeline"),
        _t("Calendar"),
        _t("Performance Tracking by Schedule"),
        _t("Reached "),
        _t(" of plan (after "),
        _t(" days)"),
        _t("Risk Alerts"),
        _t("Schedule Details"),
        _t("Linked to Inventory"),
        _t("Current on hand: "),
        _t(" units"),
        _t("Expected daily sales: "),
        _t("Expected out of stock date: "),
        _t(" (in "),
        _t("Adjust Schedule"),
        _t("Pause Sale"),
        _t("End Early"),
        _t("Category"),
        _t("Branch"),
        _t("All"),
        _t("Open Sales Orders"),
        _t("View Product"),
        _t("View Inventory"),
        _t("No risk alerts"),
        _t("No schedule data for current filters."),
        _t("Action could not be completed."),
    ];

    async load() {
        try {
            this.state.loading = true;
            this.state.error = null;

            const data = await this.orm.call(
                "sale.schedule.dashboard",
                "get_dashboard_data",
                [],
                { filters: this.state.filters || {} }
            );

            this.state.kpis = data.kpis || this.state.kpis;
            this.state.timeline = data.timeline || { cols: [], rows: [], view_mode: "timeline" };
            this.state.selected = data.selected || this.state.selected;
            this.state.inventory_link = data.inventory_link || this.state.inventory_link;
            this.state.performance = data.performance || this.state.performance;
            this.state.risk_alerts = data.risk_alerts || [];
            this.state.last_update = data.last_update || "";
            
            this.state.warehouses = data.warehouses || [];
            this.state.categories = data.categories || [];
            this.state.active_row_key = this.state.filters.selected_key || (this.state.timeline.rows[0] && this.state.timeline.rows[0].key) || null;
            if (!this.state.filters.selected_key && this.state.active_row_key) {
                this.state.filters.selected_key = this.state.active_row_key;
            }
        } catch (e) {
            console.error(e);
            this.state.error = _t("Failed to load Sale Schedule dashboard data.");
            this.notification.add(this.state.error, { type: "danger" });
        } finally {
            this.state.loading = false;
        }
    }

    onFilterChange(type, value) {
        this.state.filters[type] = value || null;
        this.load();
    }

    setViewMode(mode) {
        this.state.filters.view_mode = mode;
        this.load();
    }

    selectRow(row) {
        this.state.active_row_key = row.key;
        this.state.filters.selected_key = row.key;
        this.load();
    }

    formatMoneyVND(v) {
        const n = Number(v || 0);
        return n.toLocaleString("vi-VN") + " đ";
    }

    async openAction(methodName) {
        try {
            const action = await this.orm.call(
                "sale.schedule.dashboard",
                methodName,
                [],
                {
                    filters: this.state.filters || {},
                    selected_key: this.state.active_row_key,
                }
            );
            if (action) {
                this.action.doAction(action);
            }
        } catch (e) {
            console.error(e);
            this.notification.add(_t("Action could not be completed."), { type: "warning" });
        }
    }
}

registry.category("actions").add("sale_schedule.dashboard", SaleScheduleDashboard);
