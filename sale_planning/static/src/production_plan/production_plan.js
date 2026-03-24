/** @odoo-module **/

import { registry } from "@web/core/registry";
import { Component, onWillStart, useState } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";
import { formatCurrency } from "@web/core/currency";

export class ProductionPlanDashboard extends Component {
    static template = "mrp_production_plan.Dashboard";

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.state = useState({
            loading: true,
            months: [],
            rows: [],
            filters: {},
        });

        onWillStart(async () => {
            await this.load();
        });
    }

    formatNumber(value) {
        if (value === null || value === undefined) return "0";
        const n = Number(value);
        if (Number.isNaN(n)) return String(value);
        return n.toLocaleString("en-US");
    }

    async load() {
        try {
            this.state.loading = true;
            const data = await this.orm.call(
                "mrp.production.plan.dashboard",
                "get_dashboard_data",
                [],
                { filters: this.state.filters }
            );
            this.state.months = data.months;
            this.state.rows = data.rows;
        } finally {
            this.state.loading = false;
        }
    }

    onFilterChange(name, value) {
        this.state.filters[name] = value;
        this.load();
    }
}

registry.category("actions").add("mrp_production_plan.dashboard", ProductionPlanDashboard);
