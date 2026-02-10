/** @odoo-module **/

import { registry } from "@web/core/registry";
import {
    Component,
    onWillStart,
    onMounted,
    onPatched,
    onWillUnmount,
    useRef,
    useState,
} from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";

function afterPaint(cb) {
    // chạy sau khi browser vẽ xong frame hiện tại (DOM ready hơn)
    requestAnimationFrame(() => setTimeout(cb, 0));
}

export class DemandForecastDashboard extends Component {
    static template = "demand_forecast.Dashboard";

    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");

        this.mainChartRef = useRef("forecastChart");
        this.revByCategoryChartRef = useRef("revByCategoryChart");
        this.inventoryChartRef = useRef("inventoryChart");

        this.mainChart = null;
        this.revByCategoryChart = null;
        this.inventoryChart = null;

        this.state = useState({
            loading: true,
            error: null,
            filters: {
                forecast_id: null,
                warehouse_id: null,
                date_from: null,
                date_to: null,
                time_grain: "month",
            },
            kpis: {
                sku_forecast: 0,
                delta_percent: "0%",
                top_sku_name: "-",
                top_sku_share: "0%",
                low_stock_sku_count: 0,
                low_stock_hint: "",
                manual_adjusted: false,
                last_update: "",
            },
            series: { labels: [], forecast: [], actual: [] },
            forecast_rows: [],
            forecast_leak_rows: [],
            top_rows: [],
            adjustment_percent: 0,
            rev_spark: null,
            inventory_forecast: null,
        });

        onWillStart(async () => {
            await this.load();
        });

        onMounted(() => {
            afterPaint(() => this.renderAllCharts());
        });

        onPatched(() => {
            if (this.state.loading) return;
            afterPaint(() => this.renderAllCharts());
        });

        onWillUnmount(() => {
            this.destroyAllCharts();
        });
    }

    formatNumber(value) {
        if (value === null || value === undefined) return "";
        const n = Number(value);
        if (Number.isNaN(n)) return String(value);
        return n.toLocaleString("en-US");
    }
    getChartLib() {
        const Chart = window.Chart;
        if (!Chart) {
            console.warn("Chart.js chưa load. Check web.assets_backend / chart.umd.min.js");
            return null;
        }
        return Chart;
    }

    destroyAllCharts() {
        for (const c of ["mainChart", "revByCategoryChart", "inventoryChart"]) {
            if (this[c]) {
                this[c].destroy();
                this[c] = null;
            }
        }
    }

    renderAllCharts() {
        this.renderMainLineChart();
        this.renderRevByCategorySpark();
        this.renderInventoryChart();
    }

    renderMainLineChart() {
        const Chart = this.getChartLib();
        if (!Chart) return;

        const canvas = this.mainChartRef?.el;
        if (!canvas) return;

        const labels = this.state.series?.labels || [];
        if (!labels.length) return;

        if (this.mainChart) this.mainChart.destroy();

        this.mainChart = new Chart(canvas.getContext("2d"), {
            type: "line",
            data: {
                labels,
                datasets: [
                    { label: "Forecast", data: this.state.series.forecast || [], tension: 0.35, fill: false },
                    { label: "Actual", data: this.state.series.actual || [], tension: 0.35, fill: false, borderDash: [6, 4] },
                ],
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                interaction: { mode: "index", intersect: false },
                plugins: { legend: { display: true, position: "bottom" } },
                scales: { y: { beginAtZero: true } },
            },
        });
    }

    renderRevByCategorySpark() {
        const Chart = this.getChartLib();
        if (!Chart) return;

        const spark = this.state.rev_spark;
        const canvas = this.revByCategoryChartRef?.el;
        if (!spark || !canvas) return;
        if (!Array.isArray(spark.labels) || !spark.labels.length) return;

        if (this.revByCategoryChart) this.revByCategoryChart.destroy();

        this.revByCategoryChart = new Chart(canvas.getContext("2d"), {
            type: "bar",
            data: {
                labels: spark.labels,
                datasets: [{
                    data: spark.values || [],
                    backgroundColor: spark.colors || [],
                    borderWidth: 0,
                    borderRadius: 6,
                    barPercentage: 0.7,
                    categoryPercentage: 0.9,
                }],
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: { legend: { display: false } },
                scales: {
                    x: { grid: { display: false }, border: { display: false } },
                    y: { display: false, grid: { display: false }, border: { display: false } },
                },
            },
        });
    }

    renderInventoryChart() {
        const Chart = this.getChartLib();
        if (!Chart) return;

        const inv = this.state.inventory_forecast;
        const canvas = this.inventoryChartRef?.el;
        if (!inv || !canvas) return;
        if (!Array.isArray(inv.labels) || !inv.labels.length) return;

        if (this.inventoryChart) this.inventoryChart.destroy();

        this.inventoryChart = new Chart(canvas.getContext("2d"), {
            data: {
                labels: inv.labels,
                datasets: [
                    { type: "bar", data: inv.onhand_series || [], backgroundColor: "#6ee7b7", borderRadius: 6 },
                    { type: "line", data: inv.trend_series || [], borderColor: "#22c55e", borderDash: [6, 4], tension: 0.4, fill: false, pointRadius: 0 },
                ],
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: { legend: { display: false } },
                scales: {
                    x: { display: false, grid: { display: false }, border: { display: false } },
                    y: { display: false, grid: { display: false }, border: { display: false } },
                },
            },
        });
    }

    async load() {
        try {
            this.state.loading = true;
            this.state.error = null;

            const data = await this.orm.call(
                "demand.forecast.dashboard",
                "get_dashboard_data",
                [],
                { filters: this.state.filters || {} }
            );

            this.state.kpis = data.kpis || this.state.kpis;
            this.state.series = data.series || this.state.series;
            this.state.forecast_rows = data.forecast_rows || [];
            this.state.forecast_leak_rows = data.forecast_leak_rows || [];
            this.state.top_rows = this.state.forecast_rows;

            this.state.adjustment_percent =
                data.adjustment_percent !== undefined && data.adjustment_percent !== null
                    ? data.adjustment_percent
                    : 0;

            this.state.rev_spark = data.rev_spark || null;
            this.state.inventory_forecast = data.inventory_forecast || null;

            // chart sẽ render ở onMounted/onPatched
        } catch (e) {
            console.error(e);
            this.state.error = "Không tải được dữ liệu Forecast dashboard.";
            this.notification.add(this.state.error, { type: "danger" });
        } finally {
            this.state.loading = false;
        }
    }
}

registry.category("actions").add("demand_forecast.dashboard", DemandForecastDashboard);
