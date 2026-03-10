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

        this.state = useState({
            loading: true,
            error: null,
            filters: {
                view_mode: "timeline", // timeline | calendar
                group_by: "sku",       // sku | group
                period: "week",        // week | month
            },
            kpis: null,
            timeline: { cols: [], rows: [], view_mode: "timeline" },
            selected: null,
            inventory_link: null,
            performance: null,
            risk_alerts: [],
            last_update: "",
            active_row_key: "r1",
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

            this.state.kpis = data.kpis || null;
            this.state.timeline = data.timeline || { cols: [], rows: [], view_mode: "timeline" };
            this.state.selected = data.selected || null;
            this.state.inventory_link = data.inventory_link || null;
            this.state.performance = data.performance || null;
            this.state.risk_alerts = data.risk_alerts || [];
            this.state.last_update = data.last_update || "";
        } catch (e) {
            console.error(e);
            this.state.error = _t("Failed to load Sale Schedule dashboard data.");
            this.notification.add(this.state.error, { type: "danger" });
        } finally {
            this.state.loading = false;
        }
    }

    setViewMode(mode) {
        this.state.filters.view_mode = mode;
        this.load();
    }

    selectRow(row) {
        this.state.active_row_key = row.key;
        // demo: nếu muốn chọn row thì gọi lại backend lấy detail theo row.key
        // hiện tại dùng mock fixed để nhanh
    }

    formatMoneyVND(v) {
        const n = Number(v || 0);
        return n.toLocaleString("vi-VN") + " đ";
    }
}

registry.category("actions").add("sale_schedule.dashboard", SaleScheduleDashboard);
