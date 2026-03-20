/** @odoo-module **/

import { registry } from "@web/core/registry";
import { Component, onWillStart, onMounted, onWillUnmount, useRef, useState } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";

import { _t } from "@web/core/l10n/translation";


class AnalyticsDashboard extends Component {
  static template = "sale_planning.AnalyticsDashboard";

  setup() {
    this._t = _t;
    this.orm = useService("orm");
    this.notification = useService("notification");

    this.behaviorRef = useRef("behaviorChart");
    this.revenueBarRef = useRef("revenueBarChart");
    this.donutRef = useRef("donutChart");

    this.behaviorChart = null;
    this.revenueBarChart = null;
    this.donutChart = null;

    this.state = useState({
      loading: true,
      error: null,
      filters: { 
          segment: _t("Women's Fashion"), 
          sku_mode: "SKU", 
          time_grain: _t("Month"),
          warehouse_id: null,
          category_id: null,
      },
      warehouses: [],
      categories: [],
      kpis: null,
      behavior_chart: null,
      revenue_bar: null,
      revenue_by_category: [],
      pricing_mix: null,

      plan_actual_rows: [],
      data_table_rows: [],
      search: "",
    });

    onWillStart(() => this.load());
    onMounted(() => this.renderAllCharts());
    onWillUnmount(() => this.destroyAllCharts());
  }

  // String list for i18n harvester
  static _i18n_strings = [
      _t("ANALYTICS & REPORTS"),
      _t("Aggregate business performance, user behavior and compare plan vs actual for the fashion industry"),
      _t("Women's Fashion"),
      _t("Products / SKU"),
      _t("Time"),
      _t("Month"),
      _t("Online"),
      _t("Export CSV"),
      _t("Loading data..."),
      _t("User Behavior"),
      _t("vs previous period"),
      _t("Revenue"),
      _t("Growth"),
      _t("Profit"),
      _t("vs plan"),
      _t("Categories exceeded KPI"),
      _t("User Behavior Analysis"),
      _t("Revenue by Category"),
      _t("Full Price / Sale"),
      _t("full price"),
      _t("sale"),
      _t("Plan / Actual"),
      _t("Product"),
      _t("PV"),
      _t("UU"),
      _t("Full Price"),
      _t("Charts & Data Table"),
      _t("Search"),
      _t("Full Price"),
      _t("Category"),
      _t("Warehouse"),
      _t("All"),
  ];

  destroyAllCharts() {
    for (const c of [this.behaviorChart, this.revenueBarChart, this.donutChart]) {
      if (c) c.destroy();
    }
    this.behaviorChart = this.revenueBarChart = this.donutChart = null;
  }

  fmtNumber(n) {
    const x = Number(n || 0);
    return x.toLocaleString("en-US");
  }

  fmtMoneyVND(n) {
    const x = Number(n || 0);
    return x.toLocaleString("en-US") + " đ";
  }

  filteredDataRows() {
    const q = (this.state.search || "").trim().toLowerCase();
    const rows = this.state.data_table_rows || [];
    if (!q) return rows;
    return rows.filter((r) => (r.name || "").toLowerCase().includes(q));
  }

  async load() {
    try {
      this.state.loading = true;
      this.state.error = null;

      const data = await this.orm.call(
        "sale.planning.analytics.dashboard",
        "get_dashboard_data",
        [],
        { filters: this.state.filters || {} }
      );

      this.state.kpis = data.kpis || null;
      this.state.behavior_chart = data.behavior_chart || null;
      this.state.revenue_bar = data.revenue_bar || null;
      this.state.revenue_by_category = data.revenue_by_category || [];
      this.state.pricing_mix = data.pricing_mix || null;

      this.state.plan_actual_rows = data.plan_actual_rows || [];
      this.state.data_table_rows = data.data_table_rows || [];
      
      this.state.warehouses = data.warehouses || [];
      this.state.categories = data.categories || [];

      this.renderAllCharts();
    } catch (e) {
      console.error(e);
      this.state.error = _t("Failed to load Analytics & Reports data.");
      this.notification.add(this.state.error, { type: "danger" });
    } finally {
      this.state.loading = false;
    }
  }

  onFilterChange(type, value) {
      this.state.filters[type] = value || null;
      this.load();
  }

  renderAllCharts() {
    const Chart = window.Chart;
    if (!Chart) return;

    this.renderBehaviorChart(Chart);
    this.renderRevenueBar(Chart);
    this.renderDonut(Chart);
  }

  renderBehaviorChart(Chart) {
    const canvas = this.behaviorRef?.el;
    const cdata = this.state.behavior_chart;
    if (!canvas || !cdata) return;

    if (this.behaviorChart) this.behaviorChart.destroy();

    this.behaviorChart = new Chart(canvas.getContext("2d"), {
      type: "line",
      data: {
        labels: cdata.labels || [],
        datasets: (cdata.datasets || []).map((d) => ({
          label: d.label,
          data: d.data || [],
          tension: 0.35,
          fill: false,
          pointRadius: 2,
        })),
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        interaction: { mode: "index", intersect: false },
        plugins: { legend: { position: "bottom" } },
        scales: {
          x: { grid: { display: false } },
          y: {
            beginAtZero: true,
            ticks: { callback: (v) => this.fmtNumber(v) },
          },
        },
      },
    });
  }

  renderRevenueBar(Chart) {
    const canvas = this.revenueBarRef?.el;
    const bar = this.state.revenue_bar;
    if (!canvas || !bar) return;

    if (this.revenueBarChart) this.revenueBarChart.destroy();

    this.revenueBarChart = new Chart(canvas.getContext("2d"), {
      type: "bar",
      data: {
        labels: bar.labels || [],
        datasets: [
          {
            data: bar.values || [],
            backgroundColor: bar.colors || [],
            borderWidth: 0,
            borderRadius: 8,
            barPercentage: 0.7,
            categoryPercentage: 0.8,
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: { legend: { display: false } },
        scales: {
          x: { grid: { display: false }, ticks: { font: { size: 10 } } },
          y: { display: false },
        },
      },
    });
  }

  renderDonut(Chart) {
    const canvas = this.donutRef?.el;
    const mix = this.state.pricing_mix;
    if (!canvas || !mix) return;

    if (this.donutChart) this.donutChart.destroy();

    this.donutChart = new Chart(canvas.getContext("2d"), {
      type: "doughnut",
      data: {
        labels: [_t("Full Price"), _t("Sale")],
        datasets: [{
          data: [mix.full_price || 0, mix.sale || 0],
          borderWidth: 0,
          cutout: "70%",
        }],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: { legend: { display: false } },
      },
    });
  }
}

registry.category("actions").add("sale_planning.analytics", AnalyticsDashboard);
export default AnalyticsDashboard;
