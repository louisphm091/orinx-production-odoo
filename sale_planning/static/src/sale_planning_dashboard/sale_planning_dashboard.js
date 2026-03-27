/** @odoo-module **/

import { registry } from "@web/core/registry";
import { Component, onWillStart, onMounted, onWillUnmount, useRef, useState } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";
import { _t } from "@web/core/l10n/translation";

export class SalePlanningDashboard extends Component {
    static template = "sale_planning.Dashboard";

    setup() {
        this._t = _t;
        this.orm = useService("orm");
        this.notification = useService("notification");
        this.action = useService("action");

        // refs (OWL)
        this.mainChartRef = useRef("mainChart");
        this.revByCategoryChartRef = useRef("revByCategoryChart");
        this.inventoryChartRef = useRef("inventoryChart");

        // chart instances
        this._mainChart = null;
        this._revChart = null;
        this._invChart = null;

        // Extract context and params carefully
        const action = this.props.action || {};
        const context = action.context || {};
        const params = action.params || {};
        
        // Find forecast_id in multiple places
        const defaultForecastId = context.default_forecast_id || params.forecast_id || context.forecast_id;
        const defaultWarehouseId = context.default_warehouse_id || params.warehouse_id || context.warehouse_id;

        // State management
        this.state = useState({
            loading: true,
            loading_first_time: true,
            creating: false,
            error: null,
            filters: {
                warehouse_id: defaultWarehouseId || null,
                forecast_id: defaultForecastId || null,
                category_id: null,
                time_range: "this_month",
            },
            warehouses: [],
            categories: [],
            time_options: [
                { id: "today", name: _t("Today") },
                { id: "this_week", name: _t("This Week") },
                { id: "this_month", name: _t("This Month") },
            ],
            kpis: {
                total_supply_need: 0,
                purchase_plan_qty: 0,
                risk_sku_count: 0,
                waiting_orders: 0,
                growth_percent: 0,
                last_update: "",
            },
            main_chart: { labels: [], demand: [], plan: [], risk: [] },
            rev_by_category: [],
            rev_spark: { labels: [], values: [], colors: [] },
            inventory_forecast: null,
            order_suggestions: [],
            pagination: {
                currentPage: 1,
                pageSize: 10,
            },
        });

        onWillStart(async () => {
            await this.load();
        });

        onMounted(() => {
            this._scheduleRenderAllCharts();
        });

        onWillUnmount(() => {
            this._destroyAllCharts();
        });
    }

    // List of strings used in XML for Odoo's translation harvester
    static _i18n_strings = [
        _t("Supply / Purchase Plan"),
        _t("Plan and track purchase/supply plans based on demand and production plans"),
        _t("SKU / SKU Group"),
        _t("Refresh"),
        _t("Category"),
        _t("All"),
        _t("Warehouse"),
        _t("Time"),
        _t("Create Supply Plan"),
        _t("Loading data..."),
        _t("Total Supply Demand"),
        _t("units"),
        _t("vs previous period"),
        _t("Planned Purchase"),
        _t("of demand"),
        _t("Out of Stock Risk"),
        _t("SKUs"),
        _t("Expected shortage in 14 days"),
        _t("Waiting for Delivery"),
        _t("orders"),
        _t("Updated today"),
        _t("Purchase Recommendations"),
        _t("Updated:"),
        _t("Inventory Forecast"),
        _t("Forecast Revenue by Category"),
        _t("No data"),
        _t("System uses historical data to adjust revenue forecasts"),
        _t("Purchase Suggestions (SKU)"),
        _t("Create Purchase Recommendation"),
        _t("No."),
        _t("SKU"),
        _t("Rec. Purchase"),
        _t("Status"),
        _t("Stable"),
        _t("Today"),
        _t("This Week"),
        _t("This Month"),
    ];

    async load() {
        try {
            this.state.loading = true;
            this.state.error = null;
            
            const model = "sale.planning.dashboard"; 
            const data = await this.orm.call(
                model,
                "get_dashboard_data",
                [],
                { filters: this.state.filters || {} }
            );

            this.state.kpis = data.kpis || this.state.kpis;
            this.state.main_chart = data.main_chart || this.state.main_chart;
            this.state.rev_by_category = data.rev_by_category || [];
            this.state.rev_spark = data.rev_spark || this.state.rev_spark;
            this.state.inventory_forecast = data.inventory_forecast || null;
            this.state.order_suggestions = data.order_suggestions || [];
            
            this.state.warehouses = data.warehouses || [];
            this.state.categories = data.categories || [];

            this._scheduleRenderAllCharts();
        } catch (e) {
            console.error(e);
            this.state.error = _t("Failed to load Sale Planning dashboard data.");
            this.notification.add(this.state.error, { type: "danger" });
        } finally {
            this.state.loading = false;
        }
    }

    paginatedSuggestions() {
        const rows = this.state.order_suggestions || [];
        const start = (this.state.pagination.currentPage - 1) * this.state.pagination.pageSize;
        return rows.slice(start, start + this.state.pagination.pageSize);
    }

    getTotalPages() {
        const totalRows = (this.state.order_suggestions || []).length;
        return Math.max(1, Math.ceil(totalRows / this.state.pagination.pageSize));
    }

    getPageNumbers() {
        const total = this.getTotalPages();
        const current = this.state.pagination.currentPage;
        const delta = 2;
        const range = [];
        const rangeWithDots = [];
        let l;

        for (let i = 1; i <= total; i++) {
            if (i === 1 || i === total || (i >= current - delta && i <= current + delta)) {
                range.push(i);
            }
        }

        for (let i of range) {
            if (l) {
                if (i - l === 2) {
                    rangeWithDots.push(l + 1);
                } else if (i - l !== 1) {
                    rangeWithDots.push('...');
                }
            }
            rangeWithDots.push(i);
            l = i;
        }

        return rangeWithDots;
    }

    changePage(page) {
        const totalPages = this.getTotalPages();
        const nextPage = Math.min(Math.max(page, 1), totalPages);
        this.state.pagination.currentPage = nextPage;
    }

    onFilterChange(type, value) {
        this.state.filters[type] = value || null;
        this.state.pagination.currentPage = 1; // Reset to page 1 on filter
        this.load();
    }

    async onCreateSupplyPlan() {
        if (this.state.creating) return;
        try {
            this.state.creating = true;
            const result = await this.orm.call(
                "sale.planning.dashboard",
                "create_supply_plan",
                [],
                {}
            );
            if (result && result.ok) {
                this.notification.add(result.message, { type: "success" });
                // Navigate to the new purchase order
                if (result.id) {
                    this.action.doAction({
                        type: "ir.actions.act_window",
                        res_model: "purchase.order",
                        res_id: result.id,
                        views: [[false, "form"]],
                        target: "current",
                    });
                }
            } else {
                this.notification.add(
                    (result && result.message) || _t("Failed to create supply plan."),
                    { type: "warning" }
                );
            }
        } catch (e) {
            console.error(e);
            this.notification.add(_t("Error creating supply plan."), { type: "danger" });
        } finally {
            this.state.creating = false;
        }
    }

    async onCreatePurchaseRecommendation() {
        if (this.state.creating) return;
        try {
            this.state.creating = true;
            const result = await this.orm.call(
                "sale.planning.dashboard",
                "create_purchase_recommendation",
                [],
                {}
            );
            if (result && result.ok) {
                this.notification.add(result.message, { type: "success" });
                if (result.id) {
                    this.action.doAction({
                        type: "ir.actions.act_window",
                        res_model: "purchase.order",
                        res_id: result.id,
                        views: [[false, "form"]],
                        target: "current",
                    });
                }
            } else {
                this.notification.add(
                    (result && result.message) || _t("Failed to create purchase recommendation."),
                    { type: "warning" }
                );
            }
        } catch (e) {
            console.error(e);
            this.notification.add(_t("Error creating purchase recommendation."), { type: "danger" });
        } finally {
            this.state.creating = false;
        }
    }

    // -------- Chart helpers --------
    _getChart() {
        const Chart = window.Chart;
        if (!Chart) {
            console.warn("Chart.js not loaded → check assets + path chart.umd.min.js");
            return null;
        }
        return Chart;
    }

    _scheduleRenderAllCharts() {
        window.requestAnimationFrame(() => {
            this.renderMainChart();
            this.renderRevByCategoryChart();
            this.renderInventoryChart();
        });
    }

    _destroyAllCharts() {
        if (this._mainChart) { this._mainChart.destroy(); this._mainChart = null; }
        if (this._revChart) { this._revChart.destroy(); this._revChart = null; }
        if (this._invChart) { this._invChart.destroy(); this._invChart = null; }
    }

    renderMainChart() {
        const Chart = this._getChart();
        const canvas = this.mainChartRef?.el;
        if (!Chart || !canvas) return;

        const mc = this.state.main_chart || {};
        const labels = mc.labels || [];
        const demand = mc.demand || [];
        const plan = mc.plan || [];
        const risk = mc.risk || [];

        if (this._mainChart) this._mainChart.destroy();

        this._mainChart = new Chart(canvas.getContext("2d"), {
            type: "line",
            data: {
                labels,
                datasets: [
                    {
                        label: _t("Demand"),
                        data: demand,
                        tension: 0.35,
                        fill: true,
                        borderColor: "rgba(16, 185, 129, 0.9)",
                        backgroundColor: "rgba(16, 185, 129, 0.08)",
                        pointRadius: 3,
                        pointBackgroundColor: "rgba(16, 185, 129, 0.9)",
                    },
                    {
                        label: _t("Supply Plan"),
                        data: plan,
                        tension: 0.35,
                        fill: false,
                        borderDash: [6, 4],
                        borderColor: "rgba(59, 130, 246, 0.9)",
                        backgroundColor: "transparent",
                        pointRadius: 3,
                    },
                    {
                        label: _t("Out of Stock Risk"),
                        data: risk,
                        tension: 0.35,
                        fill: false,
                        borderDash: [2, 6],
                        borderColor: "rgba(251, 146, 60, 0.9)",
                        backgroundColor: "transparent",
                        pointRadius: 0,
                    },
                ],
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                interaction: { mode: "index", intersect: false },
                plugins: {
                    legend: { position: "bottom", labels: { boxWidth: 12, font: { size: 12 } } },
                    tooltip: { enabled: true },
                },
                scales: {
                    x: { grid: { display: false }, border: { display: false } },
                    y: {
                        beginAtZero: true,
                        grid: { color: "rgba(0,0,0,0.05)" },
                        ticks: { callback: (v) => this.formatNumber(v) },
                    },
                },
            },
        });
    }

    renderRevByCategoryChart() {
        const Chart = this._getChart();
        const canvas = this.revByCategoryChartRef?.el;
        if (!Chart || !canvas) return;

        const spark = this.state.rev_spark || {};
        const labels = spark.labels || [];
        const values = spark.values || [];
        const colors = spark.colors || [];

        if (this._revChart) this._revChart.destroy();

        this._revChart = new Chart(canvas.getContext("2d"), {
            type: "bar",
            data: {
                labels,
                datasets: [{
                    data: values,
                    backgroundColor: colors,
                    borderWidth: 0,
                    borderRadius: 8,
                    barPercentage: 0.7,
                    categoryPercentage: 0.9,
                }],
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: { display: false },
                    tooltip: { callbacks: { label: (ctx) => `${this.formatNumber(ctx.raw)} M` } },
                },
                scales: {
                    x: { grid: { display: false }, border: { display: false } },
                    y: { display: false, grid: { display: false }, border: { display: false } },
                },
            },
        });
    }

    renderInventoryChart() {
        const Chart = this._getChart();
        const canvas = this.inventoryChartRef?.el;
        if (!Chart || !canvas) return;

        const inv = this.state.inventory_forecast;
        if (!inv) return;

        if (this._invChart) this._invChart.destroy();

        this._invChart = new Chart(canvas.getContext("2d"), {
            data: {
                labels: inv.labels || ["", "", "", "", ""],
                datasets: [
                    {
                        type: "bar",
                        label: _t("Inventory"),
                        data: inv.onhand_series || [],
                        borderRadius: 8,
                        backgroundColor: "rgba(16, 185, 129, 0.35)",
                    },
                    {
                        type: "line",
                        label: _t("Trend"),
                        data: inv.trend_series || [],
                        borderDash: [6, 4],
                        tension: 0.45,
                        fill: false,
                        pointRadius: 0,
                        borderColor: "rgba(251, 146, 60, 0.9)",
                    },
                ],
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: { legend: { display: false } },
                scales: { x: { display: false }, y: { display: false } },
            },
        });
    }

    formatNumber(value) {
        const n = Number(value || 0);
        return Number.isFinite(n) ? n.toLocaleString("en-US") : String(value);
    }

    fmtMoney(v) {
        const n = Number(v || 0);
        return n.toLocaleString("vi-VN");
    }
}

registry.category("actions").add("sale_planning.dashboard", SalePlanningDashboard);
