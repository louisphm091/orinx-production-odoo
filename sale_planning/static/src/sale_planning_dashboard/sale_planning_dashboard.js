/** @odoo-module **/

import { registry } from "@web/core/registry";
import { Component, onWillStart, onMounted, onWillUnmount, useRef, useState } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";
import { _t } from "@web/core/l10n/translation";

export class SalePlanningDashboard extends Component {
    static template = "sale_planning.Dashboard";

    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");

        // refs (OWL)
        this.mainChartRef = useRef("mainChart");
        this.revByCategoryChartRef = useRef("revByCategoryChart");
        this.inventoryChartRef = useRef("inventoryChart");

        // chart instances
        this._mainChart = null;
        this._revChart = null;
        this._invChart = null;

        this.state = useState({
            loading: true,
            error: null,
            filters: {
                warehouse_id: null,
            },
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
        });

        onWillStart(async () => {
            await this.load();
        });

        onMounted(() => {
            // render charts after first mount (DOM exists)
            this._scheduleRenderAllCharts();
        });

        onWillUnmount(() => {
            this._destroyAllCharts();
        });
    }

    async load() {
        try {
            this.state.loading = true;
            this.state.error = null;

            const data = await this.orm.call(
                "sale.planning.dashboard",
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

            this._scheduleRenderAllCharts();
        } catch (e) {
            console.error(e);
            this.state.error = _t("Failed to load Sale Planning dashboard data.");
            this.notification.add(this.state.error, { type: "danger" });
        } finally {
            this.state.loading = false;
        }
    }

    // -------- Chart helpers --------
    _getChart() {
        const Chart = window.Chart;
        if (!Chart) {
            console.warn("Chart.js not loaded -> check assets + path chart.umd.min.js");
            return null;
        }
        return Chart;
    }

    _scheduleRenderAllCharts() {
        // không dùng nextTick để tránh lỗi; dùng requestAnimationFrame
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
                    { label: _t("Demand"), data: demand, tension: 0.35, fill: true },
                    { label: _t("Supply Plan"), data: plan, tension: 0.35, fill: false, borderDash: [6, 4] },
                    { label: _t("Out of Stock Risk"), data: risk, tension: 0.35, fill: false, borderDash: [2, 6] },
                ],
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                interaction: { mode: "index", intersect: false },
                plugins: { legend: { position: "bottom" } },
                scales: {
                    y: { beginAtZero: true, ticks: { callback: (v) => this.formatNumber(v) } },
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
                    },
                    {
                        type: "line",
                        label: _t("Trend"),
                        data: inv.trend_series || [],
                        borderDash: [6, 4],
                        tension: 0.45,
                        fill: false,
                        pointRadius: 0,
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
}

registry.category("actions").add("sale_planning.dashboard", SalePlanningDashboard);
