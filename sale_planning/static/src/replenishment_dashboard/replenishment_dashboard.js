/** @odoo-module **/

import { registry } from "@web/core/registry";
import { Component, onMounted, onPatched, useRef, useState } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";
import { _t } from "@web/core/l10n/translation";

export class ReplenishmentDashboard extends Component {
  static template = "sale_planning.ReplenishmentDashboard";

  setup() {
    this._t = _t;
    this.orm = useService("orm");
    this.notification = useService("notification");
    this.action = useService("action");

    // State management
    this.state = useState({
      loading: true,
      error: null,
      filters: {
        pos_config_id: null,
        warehouse_id: null,
        status: "all",
        search: "",
        selected_key: null,
      },
      kpis: {
        total_suggestions: 0,
        delta_vs_last_week: "+0",
        risk_skus: 0,
        risk_hint: "",
        pending: 0,
        pending_hint: "",
        ordered: 0,
        ordered_hint: "",
      },
      spark: {
        labels: [],
        values: [],
      },
      storeOptions: [],
      selectedStore: null,
      rows: [],
      pagination: {
        currentPage: 1,
        pageSize: 10,
      },
      detail: {
        title: "",
        category: "",
        season: "",
        warehouse: "",
        analysis: {
          onhand: 0,
          forecast_30d: 0,
          reorder_point: 0,
          suggest_qty: 0,
        },
        reason: "",
        state: "",
      },
    });
    this.sparkChartRef = useRef("sparkChart");

    onMounted(() => {
      this.renderSparkline();
    });
    onPatched(() => {
      this.renderSparkline();
    });

    this.load();
  }

  // strings for translation extraction
  static _i18n_strings = [
    _t("REPLENISHMENT MANAGEMENT"),
    _t("Track – Approve – Control replenishment suggestions based on forecast & inventory"),
    _t("Women's Fashion"),
    _t("HCM Warehouse"),
    _t("Month"),
    _t("Article Page"),
    _t("Stock Threshold Settings"),
    _t("Export CSV"),
    _t("Total Suggestions"),
    _t("suggestions"),
    _t("vs last week"),
    _t("Out of Stock Risk"),
    _t("SKUs"),
    _t("Pending Approval"),
    _t("Ordered"),
    _t("orders"),
    _t("Replenishment Suggestion List"),
    _t("Search..."),
    _t("All"),
    _t("Status: All"),
    _t("Filter"),
    _t("SKU / Product"),
    _t("Category"),
    _t("Warehouse"),
    _t("Current Stock"),
    _t("Threshold"),
    _t("Sug. Rep. Qty"),
    _t("Status"),
    _t("No data"),
    _t("Replenishment Suggestion"),
    _t("Proposal Analysis"),
    _t("Threshold"),
    _t("Suggested Replenishment"),
    _t("Replenishment Reason"),
    _t("Approve"),
    _t("Edit Quantity"),
    _t("Reject"),
    _t("Proposed"),
    _t("Approved"),
  ];

  async load() {
    try {
      this.state.loading = true;
      this.state.error = null;
      const data = await this.orm.call(
        "sale.planning.replenishment",
        "get_dashboard_data",
        [],
        { filters: this.state.filters }
      );
      this.state.kpis = data.kpis || this.state.kpis;
      this.state.spark = data.spark || this.state.spark;
      this.state.storeOptions = data.store_options || [];
      this.state.selectedStore = data.selected_store || null;
      if (this.state.selectedStore && !this.state.filters.pos_config_id) {
        this.state.filters.pos_config_id = this.state.selectedStore.id;
      }
      this.state.rows = data.rows || [];
      this.state.detail = data.detail || this.state.detail;
      const totalPages = this.getTotalPages();
      if (this.state.pagination.currentPage > totalPages) {
        this.state.pagination.currentPage = totalPages;
      }
      this.state.filters.selected_key = (data.detail && data.detail.title)
        ? (data.filters_echo && data.filters_echo.selected_key) || (data.rows?.[0]?.key ?? null)
        : null;
      this.renderSparkline();
    } catch (e) {
      console.error(e);
      this.state.error = _t("Failed to load replenishment data.");
    } finally {
      this.state.loading = false;
    }
  }

  normalizeSearchValue(value) {
    return (value || "")
      .toString()
      .normalize("NFD")
      .replace(/[\u0300-\u036f]/g, "")
      .toLowerCase()
      .trim();
  }

  updateSearch(ev) {
    this.state.filters.search = ev.target.value;
    this.state.pagination.currentPage = 1;
  }

  async updateStore(ev) {
    const value = ev.target.value ? parseInt(ev.target.value, 10) : null;
    this.state.filters.pos_config_id = value;
    this.state.filters.selected_key = null;
    this.state.pagination.currentPage = 1;
    await this.load();
  }

  filteredRows() {
    const search = this.normalizeSearchValue(this.state.filters.search);
    const status = this.state.filters.status || "all";
    return this.state.rows.filter((row) => {
      const haystack = this.normalizeSearchValue([
        row.sku_name,
        row.category,
        row.warehouse,
        row.state,
      ].join(" "));
      const matchesSearch =
        !search || haystack.includes(search);
      const matchesStatus = status === "all" || row.state === status;
      return matchesSearch && matchesStatus;
    });
  }

  paginatedRows() {
    const rows = this.filteredRows();
    const start = (this.state.pagination.currentPage - 1) * this.state.pagination.pageSize;
    return rows.slice(start, start + this.state.pagination.pageSize);
  }

  getTotalPages() {
    const totalRows = this.filteredRows().length;
    return Math.max(1, Math.ceil(totalRows / this.state.pagination.pageSize));
  }

  getPageNumbers() {
    return Array.from({ length: this.getTotalPages() }, (_, index) => index + 1);
  }

  changePage(page) {
    const totalPages = this.getTotalPages();
    const nextPage = Math.min(Math.max(page, 1), totalPages);
    this.state.pagination.currentPage = nextPage;
  }

  editSelectedQuantity() {
    const productId = this.state.detail.product_id;
    if (!productId) {
      this.notification.add(_t("No product selected."), { type: "warning" });
      return;
    }
    this.action.doAction({
      type: "ir.actions.act_window",
      name: this.state.detail.title || _t("Product"),
      res_model: "product.product",
      res_id: productId,
      views: [[false, "form"]],
      target: "current",
    });
  }

  async selectRow(key) {
    if (!key || !this.state || !this.state.filters || this.state.filters.selected_key === key) {
      return;
    }
    this.state.filters.selected_key = key;
    await this.load();
  }

  badgeText(state) {
    switch (state) {
      case "proposed":
        return "Proposed";
      case "approved":
        return "Approved";
      case "ordered":
        return "Ordered";
      default:
        return state || "";
    }
  }

  badgeClass(state) {
    switch (state) {
      case "proposed":
        return "badge bg-info-subtle text-info";
      case "approved":
        return "badge bg-success-subtle text-success";
      case "ordered":
        return "badge bg-primary-subtle text-primary";
      default:
        return "badge bg-secondary-subtle text-secondary";
    }
  }

  renderSparkline() {
    const canvas = this.sparkChartRef.el;
    if (!canvas) {
      return;
    }
    const ctx = canvas.getContext("2d");
    const values = this.state.spark.values || [];
    const rect = canvas.getBoundingClientRect();
    const width = Math.max(Math.round(rect.width || canvas.clientWidth || 220), 220);
    const height = Math.max(Math.round(rect.height || canvas.clientHeight || 54), 54);
    const ratio = window.devicePixelRatio || 1;
    canvas.width = width * ratio;
    canvas.height = height * ratio;
    ctx.setTransform(1, 0, 0, 1, 0, 0);
    ctx.scale(ratio, ratio);
    ctx.clearRect(0, 0, width, height);

    if (!values.length) {
      return;
    }

    const max = Math.max(...values, 1);
    const min = Math.min(...values, 0);
    const range = Math.max(max - min, 1);
    const padding = 6;
    const stepX = values.length > 1 ? (width - padding * 2) / (values.length - 1) : 0;
    const points = values.map((value, index) => ({
      x: padding + index * stepX,
      y: height - padding - ((value - min) / range) * (height - padding * 2),
    }));

    ctx.beginPath();
    ctx.moveTo(points[0].x, height - padding);
    points.forEach((point) => ctx.lineTo(point.x, point.y));
    ctx.lineTo(points[points.length - 1].x, height - padding);
    ctx.closePath();
    const gradient = ctx.createLinearGradient(0, 0, 0, height);
    gradient.addColorStop(0, "rgba(16, 185, 129, 0.22)");
    gradient.addColorStop(1, "rgba(16, 185, 129, 0)");
    ctx.fillStyle = gradient;
    ctx.fill();

    ctx.beginPath();
    points.forEach((point, index) => {
      if (index === 0) {
        ctx.moveTo(point.x, point.y);
      } else {
        ctx.lineTo(point.x, point.y);
      }
    });
    ctx.strokeStyle = "#10b981";
    ctx.lineWidth = 2;
    ctx.stroke();

    points.forEach((point) => {
      ctx.beginPath();
      ctx.arc(point.x, point.y, 2.5, 0, Math.PI * 2);
      ctx.fillStyle = "#10b981";
      ctx.fill();
    });
  }
}

registry.category("actions").add("sale_planning.replenishment", ReplenishmentDashboard);
