/** @odoo-module **/

import { registry } from "@web/core/registry";
import { Component, onWillStart, onMounted, onWillUnmount, useRef, useState } from "@odoo/owl";
import { session } from "@web/session";
import { useService } from "@web/core/utils/hooks";
import { _t } from "@web/core/l10n/translation";

const FASHION_FORECAST_TRANSLATION_TERMS = [
    _t("DEMAND FORECAST"),
    _t("Forecast demand quantity by product, time and scenario to serve supply planning for the fashion industry"),
    _t("Month"),
    _t("This Month"),
    _t("Next Month"),
    _t("Refresh Forecast"),
    _t("Women's Fashion"),
    _t("Men's Fashion"),
    _t("SKU Group / SKU"),
    _t("SKU Group"),
    _t("SKU"),
    _t("Week"),
    _t("Quarter"),
    _t("Loading data..."),
    _t("Forecast Demand"),
    _t(" compared to last period"),
    _t("Highest Demand SKU"),
    _t(" total demand"),
    _t("Stockout Risk"),
    _t("Manually Adjusted"),
    _t("Yes"),
    _t("No"),
    _t("Last update:"),
    _t("Demand Forecast over time"),
    _t("Demand Forecast by SKU"),
    _t("Category"),
    _t("Demand"),
    _t("Actual"),
    _t("No data yet"),
    _t("View Details"),
    _t("Forecast by SKU"),
    _t("Top"),
    _t("Shortage"),
    _t("7 days"),
    _t("Use forecast results for:"),
    _t("Purchase Planning"),
    _t("Production Planning"),
    _t("Inventory Balancing"),
    _t("Cannot load Forecast dashboard data."),
    _t("Forecast"),
];

void FASHION_FORECAST_TRANSLATION_TERMS;

const VI_VN_FASHION_FORECAST_TRANSLATIONS = {
    "DEMAND FORECAST": "DỰ BÁO NHU CẦU",
    "Demand Forecast": "Dự báo nhu cầu",
    "Revenue Forecast": "Dự báo doanh thu",
    "Forecast demand quantity by product, time and scenario to serve supply planning for the fashion industry": "Dự báo số lượng nhu cầu theo sản phẩm, thời gian và kịch bản để phục vụ kế hoạch cung ứng ngành thời trang",
    "Month": "Tháng",
    "This Month": "Tháng này",
    "Next Month": "Tháng sau",
    "Refresh Forecast": "Làm mới dự báo",
    "Women's Fashion": "Thời trang nữ",
    "Men's Fashion": "Thời trang nam",
    "SKU Group / SKU": "Nhóm SKU / SKU",
    "SKU Group": "Nhóm SKU",
    "SKU": "Mã hàng",
    "Week": "Tuần",
    "Quarter": "Quý",
    "Loading data...": "Đang tải dữ liệu...",
    "Forecast Demand": "Nhu cầu dự báo",
    " compared to last period": " so với kỳ trước",
    "Highest Demand SKU": "SKU nhu cầu cao nhất",
    " total demand": " tổng nhu cầu",
    "Stockout Risk": "Nguy cơ thiếu hàng",
    "Manually Adjusted": "Đã điều chỉnh thủ công",
    "Yes": "Có",
    "No": "Không",
    "Last update:": "Lần cập nhật:",
    "Demand Forecast over time": "Dự báo nhu cầu theo thời gian",
    "Demand Forecast by SKU": "Dự báo nhu cầu theo SKU",
    "Category": "Danh mục",
    "Demand": "Nhu cầu",
    "Actual": "Thực tế",
    "No data yet": "Chưa có dữ liệu",
    "View Details": "Xem chi tiết",
    "Forecast by SKU": "Dự báo theo SKU",
    "Top": "Đầu trang",
    "Shortage": "Thiếu",
    "7 days": "7 ngày",
    "Use forecast results for:": "Sử dụng kết quả dự báo cho:",
    "Purchase Planning": "Lập kế hoạch đặt hàng",
    "Production Planning": "Lập kế hoạch sản xuất",
    "Inventory Balancing": "Cân đối tồn kho",
    "Cannot load Forecast dashboard data.": "Không tải được dữ liệu bảng điều khiển dự báo.",
    "Forecast": "Dự báo",
};

export class FashionForecastDashboard extends Component {
    static template = "fashion_forecast.Dashboard";

    setup() {
        const localization = useService("localization");
        this.tr = (text) => {
            if (!text) return "";
            const isVi = (localization.code && localization.code.startsWith("vi")) || 
                         (document.documentElement.lang && document.documentElement.lang.startsWith("vi")) ||
                         (_t.database && _t.database.lang && _t.database.lang.startsWith("vi"));
            if (isVi && VI_VN_FASHION_FORECAST_TRANSLATIONS[text.trim()]) {
                return VI_VN_FASHION_FORECAST_TRANSLATIONS[text.trim()];
            }
            return _t(text);
        };
        this.orm = useService("orm");
        this.action = useService("action");
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
                        label: this.tr("Forecast"),
                        data: forecast,
                        tension: 0.35,
                        fill: false,
                    },
                    {
                        label: this.tr("Actual"),
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
            this.state.error = this.tr("Cannot load Forecast dashboard data.");
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

    async openProductionPlanning(ev) {
        if (ev) ev.preventDefault();
        
        // 1. Collect product IDs from the current forecast rows
        const productIds = (this.state.forecast_rows || []).map(r => {
            if (!r.product_id) return null;
            if (Array.isArray(r.product_id)) return r.product_id[0];
            return r.product_id;
        }).filter(id => id);
        
        console.log("DEMAND FORECAST: openProductionPlanning calling create_from_forecast with products:", productIds);
        
        // 2. Call server to create the plan record
        const result = await this.orm.call(
            "production.plan",
            "create_from_forecast",
            [],
            {
                forecast_id: this.state.filters.forecast_id || 0,
                product_ids: productIds,
            }
        );
        
        const planId = result?.context?.plan_id || result?.params?.plan_id;
        console.log("DEMAND FORECAST: New Plan created, ID =", planId);
        
        // 3. Navigate
        if (planId) {
            // Store for fallback
            sessionStorage.setItem("mpp_target_plan_id", String(planId));
            // Navigate using URL hash which production_plan.js is now listening to
            const actionId = 1318; // sale_planning.action_mrp_production_plan_dashboard
            window.location.href = `/web#action=${actionId}&mpp_plan_id=${planId}`;
        } else {
            // Fallback
            this.action.doAction("sale_planning.action_mrp_production_plan_dashboard");
        }
    }

    openPurchasePlanning(ev) {
        if (ev) ev.preventDefault();
        // Gửi data sang phần lập kế hoạch đặt hàng
        const initial_demand_data = {};
        (this.state.forecast_rows || []).forEach(row => {
            initial_demand_data[row.product_id || row.name] = row.demand;
        });

        this.action.doAction("sale_planning.action_sale_planning_dashboard", {
            additionalContext: {
                initial_demand_data: initial_demand_data,
                from_forecast: true
            }
        });
    }
}

registry.category("actions").add("fashion_forecast.dashboard", FashionForecastDashboard);
