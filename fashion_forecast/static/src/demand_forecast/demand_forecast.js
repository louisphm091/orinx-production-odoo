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
import { session } from "@web/session";
import { useService } from "@web/core/utils/hooks";
import { _t } from "@web/core/l10n/translation";

const DEMAND_FORECAST_TRANSLATION_TERMS = [
    _t("REVENUE FORECAST"),
    _t("Refresh Forecast"),
    _t("Advanced Settings"),
    _t("Loading data..."),
    _t("Forecast Revenue"),
    _t(" compared to last period"),
    _t("Highest Contributing SKU"),
    _t(" total demand"),
    _t("Stockout Risk"),
    _t("SKU"),
    _t("Manually Adjusted"),
    _t("Yes"),
    _t("No"),
    _t("Last update:"),
    _t("Revenue Forecast over time"),
    _t("Month"),
    _t("Week"),
    _t("Quarter"),
    _t("Adjust forecast"),
    _t("based on actual business"),
    _t("Adjustment factor"),
    _t("Reason for adjustment"),
    _t("Enter reason for adjustment..."),
    _t("Save adjustment"),
    _t("Re-forecast"),
    _t("Forecast revenue by category"),
    _t("View Details"),
    _t("Export Report"),
    _t("System uses historical data to adjust revenue forecasts"),
    _t("Forecast by SKU"),
    _t("Top"),
    _t("Category"),
    _t("Demand"),
    _t("Actual"),
    _t("No data yet"),
    _t("Corresponding inventory forecast"),
    _t("Set threshold"),
    _t("Cannot load Forecast dashboard data."),
    _t("Forecast"),
    _t("Women's jeans"),
    _t("Out of stock after 18 days if current"),
    _t("Increase 18% at housewife 16% SS current")
];

void DEMAND_FORECAST_TRANSLATION_TERMS;

const VI_VN_DEMAND_FORECAST_TRANSLATIONS = {
    "REVENUE FORECAST": "DỰ BÁO DOANH THU",
    "Revenue Forecast": "Dự báo doanh thu",
    "Demand Forecast": "Dự báo nhu cầu",
    "Refresh Forecast": "Làm mới dự báo",
    "Advanced Settings": "Cài Đặt Nâng Cao",
    "Loading data...": "Đang tải dữ liệu...",
    "Forecast Revenue": "Doanh Thu Dự Báo",
    " compared to last period": " so với kỳ trước",
    "Highest Contributing SKU": "SKU Đóng Góp Cao Nhất",
    " total demand": " tổng nhu cầu",
    "Stockout Risk": "Rủi Ro Thiếu Hàng",
    "SKU": "SKU",
    "Manually Adjusted": "Đã Điều Chỉnh Thủ Công",
    "Yes": "Có",
    "No": "Không",
    "Last update:": "Lần cập nhật:",
    "Revenue Forecast over time": "Dự báo doanh thu theo thời gian",
    "Month": "Tháng",
    "Week": "Tuần",
    "Quarter": "Quý",
    "Adjust forecast": "Điều chỉnh dự báo",
    "based on actual business": "theo thực tế kinh doanh",
    "Adjustment factor": "Hệ số điều chỉnh",
    "Reason for adjustment": "Lý do điều chỉnh",
    "Enter reason for adjustment...": "Nhập lý do điều chỉnh...",
    "Save adjustment": "Lưu điều chỉnh",
    "Re-forecast": "Tái dự báo",
    "Forecast revenue by category": "Doanh thu dự báo theo danh mục",
    "View Details": "Xem chi tiết",
    "Export Report": "Xuất báo cáo",
    "System uses historical data to adjust revenue forecasts": "Hệ thống sử dụng dữ liệu lịch sử để điều chỉnh dự báo doanh thu",
    "Forecast by SKU": "Dự báo theo SKU",
    "Top": "Top",
    "Category": "Danh Mục",
    "Demand": "Nhu Cầu",
    "Actual": "Thực Tế",
    "No data yet": "Chưa có dữ liệu",
    "Corresponding inventory forecast": "Dự báo tồn kho tương ứng",
    "Set threshold": "Thiết lập ngưỡng",
    "Cannot load Forecast dashboard data.": "Không tải được dữ liệu Forecast dashboard.",
    "Forecast": "Dự báo",
    "Women's jeans": "Quần jean nữ",
    "Out of stock after 18 days if current": "Hết hàng sau 18 ngày nếu hiện tại",
    "Increase 18% at housewife 16% SS current": "Tăng 18% tại nội trợ 16% SS hiện tại"
};


function afterPaint(cb) {
    // chạy sau khi browser vẽ xong frame hiện tại (DOM ready hơn)
    requestAnimationFrame(() => setTimeout(cb, 0));
}

export class DemandForecastDashboard extends Component {
    static template = "demand_forecast.Dashboard";

    setup() {
        const localization = useService("localization");
        this.tr = (text) => {
            if (!text) return "";
            const isVi = (localization.code && localization.code.startsWith("vi")) || 
                         (document.documentElement.lang && document.documentElement.lang.startsWith("vi")) ||
                         (_t.database && _t.database.lang && _t.database.lang.startsWith("vi"));
            if (isVi && VI_VN_DEMAND_FORECAST_TRANSLATIONS[text.trim()]) {
                return VI_VN_DEMAND_FORECAST_TRANSLATIONS[text.trim()];
            }
            return _t(text);
        };
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
            editing_row: null,
            saving_row_key: null,
        });

        onWillStart(async () => {
            await this.load();
        });

        onMounted(() => {
            afterPaint(() => this.renderAllCharts());
        });

        this.onPlanProduction = this.onPlanProduction.bind(this);
        onPatched(() => {
            if (this.state.loading || this.state.editing_row) return;
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
                    { label: this.tr("Forecast"), data: this.state.series.forecast || [], tension: 0.35, fill: false },
                    { label: this.tr("Actual"), data: this.state.series.actual || [], tension: 0.35, fill: false, borderDash: [6, 4] },
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

    updateRowDemand(rowKey, newValue) {
        const normalized = Number(newValue);
        for (const row of this.state.forecast_rows || []) {
            if (row.key === rowKey) {
                row.demand = normalized;
            }
        }
        for (const row of this.state.top_rows || []) {
            if (row.key === rowKey) {
                row.demand = normalized;
            }
        }
    }

    async load(options = {}) {
        const { silent = false } = options;
        try {
            if (!silent) {
                this.state.loading = true;
            }
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
            console.log("DASHBOARD DATA DEBUG: forecast_rows", this.state.forecast_rows);
            this.state.forecast_leak_rows = data.forecast_leak_rows || [];
            this.state.top_rows = this.state.forecast_rows;
            if (data.forecast_id) {
                this.state.filters.forecast_id = data.forecast_id;
            }

            this.state.adjustment_percent =
                data.adjustment_percent !== undefined && data.adjustment_percent !== null
                    ? data.adjustment_percent
                    : 0;

            this.state.rev_spark = data.rev_spark || null;
            this.state.inventory_forecast = data.inventory_forecast || null;

            // chart sẽ render ở onMounted/onPatched
        } catch (e) {
            console.error(e);
            this.state.error = this.tr("Cannot load Forecast dashboard data.");
            this.notification.add(this.state.error, { type: "danger" });
        } finally {
            if (!silent) {
                this.state.loading = false;
            }
        }
    }

    async onPlanProduction() {
        const forecastData = {};
        const productIds = [];
        (this.state.forecast_rows || []).forEach(r => {
            const pId = Array.isArray(r.product_id) ? r.product_id[0] : r.product_id;
            if (pId) {
                productIds.push(pId);
                forecastData[pId] = r.demand || 0;
            }
        });

        console.log("PLAN PRODUCTION DEBUG: sending productIds", productIds, "forecastData", forecastData);
        const result = await this.orm.call(
            "production.plan",
            "create_from_forecast",
            [],
            {
                forecast_id: this.state.filters.forecast_id || 0,
                product_ids: productIds,
                forecast_values: forecastData,
            }
        );
        const planId = result?.context?.plan_id || result?.params?.plan_id;
        console.log("PLAN PRODUCTION DEBUG: got planId =", planId, "| full result:", result);
        
        if (planId) {
            // Store in sessionStorage AND navigate using direct URL to force fresh mount
            sessionStorage.setItem("mpp_target_plan_id", String(planId));
            // Navigate to production plan with plan_id in hash – forces fresh component mount
            const actionId = 1318; // sale_planning.action_mrp_production_plan_dashboard
            window.location.href = `/web#action=${actionId}&mpp_plan_id=${planId}`;
        } else {
            // Fallback: doAction normally
            this.action.doAction(result);
        }
    }

    onCellClick(ev, rowKey, field) {
        if (ev) {
            ev.stopPropagation();
        }
        if (field !== 'demand') return;
        this.state.editing_row = { key: rowKey };
    }

    onCellBlur(ev, row) {
        if (ev) {
            ev.stopPropagation();
        }
        this.commitCellEdit(row, ev.target.value);
    }

    onCellKeyDown(ev, row) {
        if (ev) {
            ev.stopPropagation();
        }
        if (ev.key === "Enter") {
            ev.preventDefault();
            this.commitCellEdit(row, ev.target.value);
        } else if (ev.key === "Escape") {
            this.state.editing_row = null;
        }
    }

    commitCellEdit(row, rawValue) {
        const rowKey = row.key;
        if (this.state.saving_row_key === rowKey) {
            this.state.editing_row = null;
            return;
        }
        const newVal = parseFloat(rawValue);
        this.state.editing_row = null;
        if (isNaN(newVal) || newVal === row.demand) {
            return;
        }
        this.saveCellValue(row, newVal);
    }

    async saveCellValue(row, newValue) {
        const rowKey = row.key;
        try {
            this.state.saving_row_key = rowKey;
            const pId = Array.isArray(row.product_id) ? row.product_id[0] : row.product_id;
            const result = await this.orm.call(
                "demand.forecast.dashboard",
                "save_forecast_line",
                [],
                {
                    product_id: pId,
                    qty: newValue,
                    filters: {
                        forecast_id: this.state.filters.forecast_id,
                        warehouse_id: this.state.filters.warehouse_id,
                    }
                }
            );
            if (result && result.ok) {
                if (result.forecast_id) {
                    this.state.filters.forecast_id = result.forecast_id;
                }
                this.updateRowDemand(rowKey, newValue);
                this.notification.add(this.tr("Saved forecast adjustment."), { type: "success" });
                await this.load({ silent: true });
            } else {
                this.notification.add(result.message || this.tr("Failed to save."), { type: "danger" });
            }
        } catch (e) {
            console.error(e);
            this.notification.add(this.tr("Error saving forecast."), { type: "danger" });
        } finally {
            this.state.saving_row_key = null;
        }
    }
}

registry.category("actions").add("demand_forecast.dashboard", DemandForecastDashboard);
