/** @odoo-module **/

import { registry } from "@web/core/registry";
import { Component, useState } from "@odoo/owl";
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
        category_id: null,
        status: "all",
        search: "",
        selected_key: null,
      },
      warehouses: [],
      categories: [],
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

    this.load();
  }

  async editSelectedQuantity() {
    const detail = this.state.detail;
    if (!detail || !detail.product_id) {
      this.notification.add(this._t("No product selected."), { type: "warning" });
      return;
    }
    
    const currentQty = detail.analysis?.suggest_qty || 0;
    const newQtyStr = window.prompt(this._t("Enter new replenishment quantity:"), currentQty);
    
    if (newQtyStr === null) return; // Cancelled
    
    const newQty = parseFloat(newQtyStr);
    if (isNaN(newQty) || newQty <= 0) {
        this.notification.add(this._t("Please enter a valid positive number."), { type: "warning" });
        return;
    }

    // Call approve with the new quantity
    await this.approveReplenishment(newQty);
  }

  async approveReplenishment(customQty = null) {
    const detail = this.state.detail;
    if (!detail || !detail.product_id) return;
    
    const qty = customQty !== null ? customQty : (detail.analysis?.suggest_qty || 0);
    if (qty <= 0) {
        this.notification.add(this._t("Suggested quantity must be greater than zero."), { type: "warning" });
        return;
    }

    try {
        this.state.loading = true;
        const result = await this.orm.call(
            "sale.planning.replenishment",
            "action_approve_replenishment",
            [],
            {
                params: {
                    product_id: detail.product_id,
                    qty: qty,
                    warehouse_id: this.state.filters.warehouse_id
                }
            }
        );

        if (result && result.ok) {
            this.notification.add(result.message, { type: "success" });
            if (result.res_id) {
                this.action.doAction({
                    type: "ir.actions.act_window",
                    res_model: "purchase.order",
                    res_id: result.res_id,
                    views: [[false, "form"]],
                    target: "current",
                });
            }
            await this.load();
        } else {
            this.notification.add(result.message || this._t("Failed to approve replenishment."), { type: "danger" });
        }
    } catch (err) {
        console.error(err);
        this.notification.add(this._t("Error during approval."), { type: "danger" });
    } finally {
        this.state.loading = false;
    }
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
    _t("Ordered"),
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
      this.state.storeOptions = data.store_options || [];
      this.state.selectedStore = data.selected_store || null;
      
      this.state.warehouses = data.warehouses || [];
      this.state.categories = data.categories || [];

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
    } catch (e) {
      console.error(e);
      this.state.error = _t("Failed to load replenishment data.");
    } finally {
      this.state.loading = false;
    }
  }

  onFilterChange(type, value) {
      this.state.filters[type] = value || null;
      this.state.pagination.currentPage = 1;
      this.load();
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
}

registry.category("actions").add("sale_planning.replenishment", ReplenishmentDashboard);
