/** @odoo-module **/

import { registry } from "@web/core/registry";
import { Component, useState, onMounted, onPatched, onWillUnmount, useRef } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";

export class SwiftPosSalesDashboard extends Component {
  static template = "pos_theme_swift.SwiftPosSalesDashboard";

  setup() {
    this.orm = useService("orm");
    this.action = useService("action");

    this.state = useState({
      loading: true,
      filter: "today",
      filterLabel: "Hôm nay",
      tab: "day",

      kpi: { revenue: 0, refund: 0, net: 0, orders: 0 },

      topProductsMode: "revenue",
      topProductsRange: "this_month",
      top_products: [],

      recent_orders: [],
      chart_data: { labels: [], datasets: [] },
    });

    this.chartRef = useRef("netRevenueChart");
    this._chart = null;
    this._chartNeedsRender = false;

    onMounted(async () => {
      await this.load();
      // đánh dấu để onPatched render chart sau khi DOM đã paint
      this._chartNeedsRender = true;
    });

    onPatched(() => {
      if (this._chartNeedsRender) {
        this._chartNeedsRender = false;
        this.renderChart();
      }
    });

    onWillUnmount(() => this.destroyChart());
  }

  // ---------------- Format helpers ----------------
  formatVND(v) {
    const n = Number(v || 0);
    return `${n.toLocaleString("vi-VN")} đ`;
  }

  formatCompact(v) {
    const n = Number(v || 0);
    if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)} tr`;
    if (n >= 1_000) return `${Math.round(n / 1_000)}k`;
    return `${n}`;
  }

  // ---------------- Menu actions ----------------
  onRefresh() {
    this.load().then(() => {
      this._chartNeedsRender = true;
    });
  }

  setFilter(key) {
    const labels = {
      today: "Hôm nay",
      yesterday: "Hôm qua",
      this_week: "Tuần này",
      this_month: "Tháng này",
    };
    this._setFilter(key, labels[key] || key);
  }

  setFilterToday() { this.setFilter("today"); }
  setFilterYesterday() { this.setFilter("yesterday"); }
  setFilterThisWeek() { this.setFilter("this_week"); }
  setFilterThisMonth() { this.setFilter("this_month"); }

  _setFilter(key, label) {
    this.state.filter = key;
    this.state.filterLabel = label;
    this.onRefresh();
  }

  setTab(tab) {
    this.state.tab = tab;
    this.onRefresh(); // Refresh data for the new tab/chart view
  }

  onTopModeChanged() { this.onRefresh(); }
  onTopRangeChanged() { this.onRefresh(); }

  openOrders() {
    // mở list pos.order (backend)
    return this.action.doAction({
      type: "ir.actions.act_window",
      name: "POS Orders",
      res_model: "pos.order",
      views: [[false, "list"], [false, "form"]],
      target: "current",
    });
  }

  // ---------------- Data loading ----------------
  async load() {
    this.state.loading = true;
    try {
      const data = await this.orm.call("pos.dashboard.swift", "get_dashboard_data", [], {
        filter_key: this.state.filter,
      });
      if (data) {
        this.state.kpi = data.kpi || this.state.kpi;
        this.state.recent_orders = data.recent_orders || [];
        this.state.top_products = data.top_products || [];
        this.state.chart_data = data.chart_data || { labels: [], datasets: [] };
      }
    } catch (e) {
      console.error("[SwiftReport] Failed to load dashboard data:", e);
    } finally {
      this.state.loading = false;
    }
  }

  // ---------------- Chart.js ----------------
  destroyChart() {
    if (this._chart) {
      this._chart.destroy();
      this._chart = null;
    }
  }

  renderChart() {
    try {
      const canvas = this.chartRef.el;
      if (!canvas) {
        console.warn("[SwiftReport] canvas ref not ready");
        return;
      }
      if (!window.Chart) {
        console.warn("[SwiftReport] Chart.js not found on window");
        return;
      }

      // nếu canvas đang display none hoặc height = 0 -> Chart sẽ “không thấy”
      // CSS bên dưới sẽ fix height của container.

      this.destroyChart();

      const data = this.state.chart_data;
      if (!data || !data.labels || data.labels.length === 0) {
        console.warn("[SwiftReport] No chart data to render");
        return;
      }

      const ctx = canvas.getContext("2d");
      this._chart = new window.Chart(ctx, {
        type: "bar",
        data,
        options: {
          responsive: true,
          maintainAspectRatio: false,
          animation: false,
          plugins: {
            legend: { position: "bottom" },
            tooltip: { enabled: true },
          },
          scales: {
            x: { stacked: true, grid: { display: false } },
            y: { stacked: true, beginAtZero: true },
          },
        },
      });

      // debug
      // console.log("[SwiftReport] chart rendered");
    } catch (e) {
      console.error("[SwiftReport] renderChart failed:", e);
    }
  }
}

// register client action tag
registry.category("actions").add("pos_theme_swift.swift_pos_sales_dashboard", SwiftPosSalesDashboard);
