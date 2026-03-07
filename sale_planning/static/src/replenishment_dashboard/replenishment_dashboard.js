/** @odoo-module **/

import { registry } from "@web/core/registry";
import { Component, onWillStart, onMounted, onWillUnmount, useRef, useState } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";
import { _t } from "@web/core/l10n/translation";

export class ReplenishmentDashboard extends Component {
  static template = "sale_planning.ReplenishmentDashboard";

  setup() {
    this.orm = useService("orm");
    this.notification = useService("notification");

    this.sparkRef = useRef("sparkChart");
    this.spark = null;

    this.state = useState({
      loading: true,
      error: null,
      search: "",
      filters: {
        selected_key: null,
      },
      kpis: {},
      spark: null,
      rows: [],
      detail: {
        title: "",
        category: "",
        season: "",
        analysis: { onhand: 0, forecast_30d: 0, reorder_point: 0, suggest_qty: 0 },
        reason: "",
      },
      selected_key: null,
    });

    onWillStart(async () => {
      await this.load();
    });

    onMounted(() => {
      this.renderSpark();
    });

    onWillUnmount(() => {
      this.destroySpark();
    });
  }

  badgeText(state) {
    if (state === "approved") return _t("Approved");
    if (state === "ordered") return _t("Ordered");
    return _t("Proposed");
  }

  badgeClass(state) {
    if (state === "approved") return "badge sp_badge sp_badge_approved";
    if (state === "ordered") return "badge sp_badge sp_badge_ordered";
    return "badge sp_badge sp_badge_proposed";
  }

  filteredRows() {
    const q = (this.state.search || "").trim().toLowerCase();
    const rows = this.state.rows || [];
    if (!q) return rows;
    return rows.filter((r) => (r.sku_name || "").toLowerCase().includes(q));
  }

  selectRow(key) {
    this.state.selected_key = key;
    this.state.filters.selected_key = key;
    // reload detail theo key (server trả detail)
    this.load();
  }

  async load() {
    try {
      this.state.loading = true;
      this.state.error = null;

      const data = await this.orm.call(
        "sale.planning.replenishment",
        "get_dashboard_data",
        [],
        { filters: this.state.filters || {} }
      );

      this.state.kpis = data.kpis || {};
      this.state.spark = data.spark || null;
      this.state.rows = data.rows || [];
      this.state.detail = data.detail || this.state.detail;

      if (!this.state.selected_key && this.state.detail && data.rows?.length) {
        this.state.selected_key = this.state.filters.selected_key || data.rows[0].key;
      }

      this.renderSpark();
    } catch (e) {
      console.error(e);
      this.state.error = _t("Failed to load replenishment data.");
      this.notification.add(this.state.error, { type: "danger" });
    } finally {
      this.state.loading = false;
    }
  }

  destroySpark() {
    if (this.spark) {
      this.spark.destroy();
      this.spark = null;
    }
  }

  renderSpark() {
    const Chart = window.Chart;
    if (!Chart) return;

    const canvas = this.sparkRef?.el;
    const spark = this.state.spark;
    if (!canvas || !spark) return;

    this.destroySpark();

    this.spark = new Chart(canvas.getContext("2d"), {
      type: "line",
      data: {
        labels: spark.labels || [],
        datasets: [
          {
            data: spark.values || [],
            borderColor: "rgba(16,185,129,0.9)",
            backgroundColor: "rgba(16,185,129,0.15)",
            tension: 0.35,
            fill: true,
            pointRadius: 0,
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: { legend: { display: false }, tooltip: { enabled: false } },
        scales: { x: { display: false }, y: { display: false } },
        elements: { line: { borderWidth: 2 } },
      },
    });
  }
}

registry.category("actions").add("sale_planning.replenishment", ReplenishmentDashboard);
