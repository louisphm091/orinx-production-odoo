/** @odoo-module **/

import { registry } from "@web/core/registry";
import { Component, onWillStart, onMounted, onWillUnmount, useRef, useState } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";
import { _t } from "@web/core/l10n/translation";


export class SalePlanningDashboardProgress extends Component {
  static template = "sale_planning.DashboardProgress";

  setup() {
    this._t = _t;
    this.orm = useService("orm");
    this.notification = useService("notification");

    this.overallChartRef = useRef("overallChart");
    this.historyChartRef = useRef("historyChart");

    this.overallChart = null;
    this.historyChart = null;

    this.state = useState({
      loading: true,
      error: null,
      filters: {
        group_by: "sku",
        time_unit: "week",
        view_mode: "month",
        warehouse_id: null,
        category_id: null,
      },
      warehouses: [],
      categories: [],
      time_options: [
          { id: "week", name: _t("Week") },
          { id: "month", name: _t("Month") },
          { id: "quarter", name: _t("Quarter") },
      ],
      kpis: {},
      overall_chart: { labels: [], planned: [], actual: [], trend: [] },
      risks: [],
      sku_cards: [],
      history: { labels: [], values: [], note: "" },
    });

    onWillStart(async () => {
      await this.load();
    });

    onMounted(() => {
      this.renderCharts();
    });

    onWillUnmount(() => {
      this.destroyCharts();
    });
  }

  // String list for i18n harvester
  static _i18n_strings = [
      _t("EXECUTION PROGRESS TRACKING"),
      _t("SKU / SKU Group"),
      _t("Quarter"),
      _t("Executive Dashboard"),
      _t("Fashion Industry"),
      _t("By Time"),
      _t("Week"),
      _t("Month"),
      _t("Loading data..."),
      _t("Achieved"),
      _t("of plan"),
      _t("SKUs at risk of shortage"),
      _t("SKUs"),
      _t("SKUs on / above plan"),
      _t("Planned"),
      _t("Actual"),
      _t("Overall Execution Progress"),
      _t("Alerts & Risks"),
      _t("See All"),
      _t("Progress by SKU / Order"),
      _t("Execution History & Trends"),
      _t("Category"),
      _t("Branch"),
      _t("All"),
  ];

  async load() {
    try {
      this.state.loading = true;
      this.state.error = null;

      const data = await this.orm.call(
        "sale.planning.dashboard.progress",
        "get_dashboard_data",
        [],
        { filters: this.state.filters || {} }
      );

      this.state.kpis = data.kpis || {};
      this.state.overall_chart = data.overall_chart || this.state.overall_chart;
      this.state.risks = data.risks || [];
      this.state.sku_cards = data.sku_cards || [];
      this.state.history = data.history || this.state.history;
      
      this.state.warehouses = data.warehouses || [];
      this.state.categories = data.categories || [];

      // vẽ chart sau khi data đã vào state
      this.renderCharts();
    } catch (e) {
      console.error(e);
      this.state.error = _t("Failed to load progress dashboard data.");
      this.notification.add(this.state.error, { type: "danger" });
    } finally {
      this.state.loading = false;
    }
  }

  onFilterChange(type, value) {
      this.state.filters[type] = value || null;
      this.load();
  }

  destroyCharts() {
    if (this.overallChart) {
      this.overallChart.destroy();
      this.overallChart = null;
    }
    if (this.historyChart) {
      this.historyChart.destroy();
      this.historyChart = null;
    }
  }

  renderCharts() {
    const Chart = window.Chart;
    if (!Chart) {
      console.warn("Chart.js chưa được load (window.Chart). Kiểm tra assets chart.umd.min.js");
      return;
    }

    this.renderOverallChart(Chart);
    this.renderHistoryChart(Chart);
  }

  renderOverallChart(Chart) {
    const canvas = this.overallChartRef?.el;
    if (!canvas) return;

    const c = this.state.overall_chart || {};
    const labels = c.labels || [];
    const planned = c.planned || [];
    const actual = c.actual || [];
    const trend = c.trend || [];

    if (!labels.length) return;

    if (this.overallChart) this.overallChart.destroy();

    this.overallChart = new Chart(canvas.getContext("2d"), {
      data: {
        labels,
        datasets: [
          {
            type: "bar",
            label: _t("Planned"),
            data: planned,
            backgroundColor: "rgba(148, 163, 184, 0.55)",
            borderRadius: 8,
            barPercentage: 0.7,
            categoryPercentage: 0.75,
          },
          {
            type: "bar",
            label: _t("Actual"),
            data: actual,
            backgroundColor: "rgba(16, 185, 129, 0.55)",
            borderRadius: 8,
            barPercentage: 0.7,
            categoryPercentage: 0.75,
          },
          {
            type: "line",
            label: _t("Execution Trend"),
            data: trend,
            borderColor: "rgba(16, 185, 129, 0.9)",
            borderDash: [6, 4],
            tension: 0.35,
            pointRadius: 0,
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        interaction: { mode: "index", intersect: false },
        plugins: {
          legend: { position: "bottom" },
          tooltip: { enabled: true },
        },
        scales: {
          x: { grid: { display: false } },
          y: {
            beginAtZero: true,
            ticks: { callback: (v) => Number(v).toLocaleString("en-US") },
          },
        },
      },
    });
  }

  renderHistoryChart(Chart) {
    const canvas = this.historyChartRef?.el;
    if (!canvas) return;

    const h = this.state.history || {};
    const labels = h.labels || [];
    const values = h.values || [];
    if (!labels.length) return;

    if (this.historyChart) this.historyChart.destroy();

    this.historyChart = new Chart(canvas.getContext("2d"), {
      type: "line",
      data: {
        labels,
        datasets: [
          {
            label: _t("Progress"),
            data: values,
            borderColor: "rgba(59, 130, 246, 0.9)",
            tension: 0.35,
            fill: false,
            pointRadius: 3,
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: { legend: { display: false } },
        scales: {
          x: { grid: { display: false } },
          y: {
            beginAtZero: true,
            ticks: {
              callback: (v) => `${v}%`,
            },
          },
        },
      },
    });
  }

  fmtMoney(v) {
    const n = Number(v || 0);
    return n.toLocaleString("vi-VN");
  }
}

registry.category("actions").add("sale_planning.dashboard_progress", SalePlanningDashboardProgress);
