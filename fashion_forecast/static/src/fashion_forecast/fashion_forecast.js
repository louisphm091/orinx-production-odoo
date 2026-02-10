/** @odoo-module **/

import { registry } from "@web/core/registry";
import { Component, onWillStart, onMounted, onWillUnmount, useRef, useState } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";

export class FashionForecastDashboard extends Component {
    static template = "fashion_forecast.Dashboard";

    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");

        this.chartRef = useRef("forecastChart");
        this.chart = null;

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
        });

        onWillStart(async () => {
            await this.load(); // load data trước
        });

        onMounted(() => {
            // render chart lần đầu sau khi DOM sẵn sàng
            this.renderChart();
        });

        onWillUnmount(() => {
            this.destroyChart();
        });
    }

    destroyChart() {
        if (this.chart) {
            this.chart.destroy();
            this.chart = null;
        }
    }

    renderChart() {
        // Chart.js UMD phải load xong -> window.Chart
        const Chart = window.Chart;
        if (!Chart) {
            console.warn("Chart.js chưa được load. Kiểm tra web.assets_backend / đường dẫn chart.umd.min.js");
            return;
        }
        const canvas = this.chartRef.el;
        if (!canvas) return;

        // destroy trước khi vẽ lại
        this.destroyChart();

        const labels = this.state.series.labels || [];
        const forecast = this.state.series.forecast || [];
        const actual = this.state.series.actual || [];

        this.chart = new Chart(canvas.getContext("2d"), {
            type: "line",
            data: {
                labels,
                datasets: [
                    {
                        label: "Forecast",
                        data: forecast,
                        tension: 0.35,
                        fill: false,
                    },
                    {
                        label: "Actual",
                        data: actual,
                        tension: 0.35,
                        fill: false,
                    },
                ],
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                interaction: { mode: "index", intersect: false },
                plugins: {
                    legend: { display: true },
                    tooltip: { enabled: true },
                },
                scales: {
                    y: {
                        beginAtZero: true,
                        ticks: {
                            callback: (v) => this.formatNumber(v),
                        },
                    },
                },
            },
        });
    }

    async load() {
        try {
            this.state.loading = true;
            this.state.error = null;

            const data = await this.orm.call(
                "fashion.forecast.dashboard",
                "get_dashboard_data",
                [],
                { filters: this.state.filters || {} }
            );

            this.state.kpis = data.kpis || this.state.kpis;
            this.state.series = data.series || this.state.series;

            this.state.forecast_rows = data.forecast_rows || [];
            this.state.forecast_leak_rows = data.forecast_leak_rows || [];
            this.state.top_rows = this.state.forecast_rows;

            if (data.adjustment_percent !== undefined && data.adjustment_percent !== null) {
                this.state.adjustment_percent = data.adjustment_percent;
            }

            // ✅ mỗi lần load xong thì vẽ lại chart
            this.renderChart();
        } catch (e) {
            console.error(e);
            this.state.error = "Không tải được dữ liệu Forecast dashboard.";
            this.notification.add(this.state.error, { type: "danger" });
        } finally {
            this.state.loading = false;
        }
    }

    formatNumber(value) {
        if (value === null || value === undefined) return "";
        const n = Number(value);
        if (Number.isNaN(n)) return String(value);
        return n.toLocaleString("en-US"); // 12,500
    }
}

registry.category("actions").add("fashion_forecast.dashboard", FashionForecastDashboard);
