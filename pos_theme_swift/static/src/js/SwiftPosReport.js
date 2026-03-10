/** @odoo-module **/

import { registry } from "@web/core/registry";
import { Component, useState, onMounted, onPatched, onWillUnmount, useRef } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";
import { _t } from "@web/core/l10n/translation";


export class SwiftPosSalesDashboard extends Component {
  static template = "pos_theme_swift.SwiftPosSalesDashboard";
  static _i18n_strings = [
    _t("Today's Sales Results"),
    _t("Refresh"),
    _t("Today"),
    _t("Yesterday"),
    _t("This Week"),
    _t("This Month"),
    _t("Loading data..."),
    _t("Revenue"),
    _t("invoices"),
    _t("Refunds"),
    _t("Net Revenue"),
    _t("Compared to yesterday"),
    _t("Invoices"),
    _t("View List"),
    _t("By Day"),
    _t("By Hour"),
    _t("By Weekday"),
    _t("Recent Activity"),
    _t("just sold an order"),
    _t("Top 10 Best Sellers"),
    _t("By Revenue"),
    _t("By Quantity"),
    _t("Top 10 Top Customers"),
    _t("You can add customer tables / charts here."),
  ];

  setup() {
    this._t = _t;
    this.orm = useService("orm");
    this.action = useService("action");
    this.locale = this.getUserLocale();

    this.state = useState({
      loading: true,
      filter: "today",
      filterLabel: _t("Today"),
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

  getUserLocale() {
    const lang = document.documentElement.lang || navigator.language || "en-US";
    return lang.replace("_", "-");
  }

  formatVND(v) {
    const n = Number(v || 0);
    try {
      return new Intl.NumberFormat(this.locale, {
        style: "currency",
        currency: "VND",
        maximumFractionDigits: 0,
        currencyDisplay: this.locale.toLowerCase().startsWith("vi") ? "symbol" : "code",
      }).format(n);
    } catch {
      return `${n.toLocaleString(this.locale)} VND`;
    }
  }

  formatCompact(v) {
    const n = Number(v || 0);
    try {
      return new Intl.NumberFormat(this.locale, {
        notation: "compact",
        compactDisplay: "short",
        maximumFractionDigits: 1,
      }).format(n);
    } catch {
      if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)} M`;
      if (n >= 1_000) return `${Math.round(n / 1_000)}k`;
      return `${n}`;
    }
  }

  onRefresh() {
    this.load().then(() => {
      this._chartNeedsRender = true;
    });
  }

  setFilter(key) {
    const labels = {
      today: _t("Today"),
      yesterday: _t("Yesterday"),
      this_week: _t("This Week"),
      this_month: _t("This Month"),
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
    this.onRefresh();
  }

  setTabDay() { this.setTab("day"); }
  setTabHour() { this.setTab("hour"); }
  setTabWeekday() { this.setTab("weekday"); }

  onTopModeChanged() { this.onRefresh(); }
  onTopRangeChanged() { this.onRefresh(); }

  openOrders() {
    return this.action.doAction({
      type: "ir.actions.act_window",
      name: _t("POS Orders"),
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

    } catch (e) {
      console.error("[SwiftReport] renderChart failed:", e);
    }
  }
}

// register client action tag
registry.category("actions").add("pos_theme_swift.swift_pos_sales_dashboard", SwiftPosSalesDashboard);
