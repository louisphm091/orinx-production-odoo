/** @odoo-module **/

import { registry } from "@web/core/registry";
import { Component, onWillStart, onMounted, useState } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";

export class SaleScheduleDashboard extends Component {
    static template = "sale_planning.SaleScheduleDashboard";

    setup() {
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
            this.state.error = "Không tải được dữ liệu Sale Schedule dashboard.";
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
