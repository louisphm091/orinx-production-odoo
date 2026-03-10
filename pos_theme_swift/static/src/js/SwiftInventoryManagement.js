/** @odoo-module **/

import { registry } from "@web/core/registry";
import { Component, useState, onMounted } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";
import { _t } from "@web/core/l10n/translation";
import { SwiftInventoryForm } from "./SwiftInventoryForm";


export class SwiftInventory extends Component {
  static template = "pos_theme_swift.SwiftInventory";
  static components = { SwiftInventoryForm };
  static _i18n_strings = [
    _t("Inventory Voucher"),
    _t("Search by voucher code"),
    _t("Select branch"),
    _t("Audit"),
    _t("Export"),
    _t("Columns"),
    _t("Settings"),
    _t("Loading data..."),
    _t("Audit Code"),
    _t("Time"),
    _t("Balance Date"),
    _t("Actual Qty"),
    _t("Total Actual"),
    _t("Total Diff"),
    _t("Diff Inc"),
    _t("Diff Dec"),
    _t("Notes"),
    _t("Status"),
    _t("Draft"),
    _t("Balanced"),
    _t("No inventory vouchers for this branch"),
    _t("Select a branch to view inventory vouchers"),
    _t("Branch"),
    _t("Please select a branch before creating an inventory voucher."),
    _t("Notification"),
    _t("Excel export function is under development."),
    _t("PDF export function is under development."),
    _t("Column options are under development."),
    _t("Settings are under development."),
  ];

  setup() {
    this._t = _t;
    this.orm = useService("orm");
    this.action = useService("action");
    this.notification = useService("notification");

    this.state = useState({
      loading: true,
      keyword: "",
      checkAll: false,
      records: [],
      configs: [],
      selectedConfigId: false,
      view: "list",
      editId: false,
      branchName: "",
    });

    this._allRecords = [];
    this._searchTimer = null;

    // Bind methods used in template so 'this' remains correct
    this.toggleCheckAll = this.toggleCheckAll.bind(this);
    this.toggleRow = this.toggleRow.bind(this);
    this.toggleStar = this.toggleStar.bind(this);
    this.openRow = this.openRow.bind(this);
    this.onCreateInventory = this.onCreateInventory.bind(this);
    this.onFormBack = this.onFormBack.bind(this);
    this.onFormSaved = this.onFormSaved.bind(this);
    this.onSearchInput = this.onSearchInput.bind(this);
    this.onBranchChange = this.onBranchChange.bind(this);

    onMounted(async () => {
      await this._loadBranches();
      await this.loadRecords();
    });
  }

  // ─── helpers ────────────────────────────────────────────────

  formatNumber(val) {
    if (val === undefined || val === null || val === false) return "";
    const n = Number(val);
    if (isNaN(n)) return "";
    return n.toLocaleString("vi-VN");
  }

  _formatDatetime(dtStr) {
    if (!dtStr) return "";
    const d = new Date(dtStr.replace(" ", "T") + "Z");
    const pad = (v) => String(v).padStart(2, "0");
    return (
      `${d.getFullYear()}/${pad(d.getMonth() + 1)}/${pad(d.getDate())} ` +
      `${pad(d.getHours())}:${pad(d.getMinutes())}`
    );
  }

  _mapRecord(r) {
    return {
      id: r.id,
      code: r.name || r.id,
      time: this._formatDatetime(r.date),
      balance_time: this._formatDatetime(r.date),
      qty_actual: r.total_qty_actual || 0,
      total_actual: r.total_qty_actual || 0,
      diff_total: r.total_diff || 0,
      diff_inc: r.total_diff_inc || 0,
      diff_dec: Math.abs(r.total_diff_dec || 0),
      note: r.note || "",
      status: r.state === "done" ? "done" : "draft",
      starred: false,
      selected: false,
      active: false,
    };
  }

  // ─── branch name ─────────────────────────────────────────────

  _getContextConfigId() {
    const rawConfigId =
      this.props?.action?.context?.pos_config_id ||
      this.env?.config?.pos_config_id ||
      false;
    const configId = parseInt(rawConfigId, 10);
    return Number.isInteger(configId) ? configId : false;
  }

  async _loadBranches() {
    try {
      const configs = await this.orm.searchRead(
        "pos.config",
        [["active", "=", true]],
        ["name"],
        { order: "name asc" }
      );
      this.state.configs = configs || [];

      const contextConfigId = this._getContextConfigId();
      const selected =
        this.state.configs.find((config) => config.id === contextConfigId) ||
        this.state.configs[0] ||
        false;

      this.state.selectedConfigId = selected ? selected.id : false;
      this.state.branchName = selected ? selected.name : _t("Branch");
    } catch (_) {
      this.state.configs = [];
      this.state.selectedConfigId = false;
      this.state.branchName = _t("Branch");
    }
  }

  // ─── data loading ─────────────────────────────────────────────

  async loadRecords() {
    this.state.loading = true;
    try {
      const fields = [
        "name", "date",
        "total_qty_actual", "total_diff",
        "total_diff_inc", "total_diff_dec",
        "note", "state",
      ];
      let raw = [];
      try {
        raw = await this.orm.searchRead(
          "swift.stock.inventory",
          this.state.selectedConfigId ? [["config_id", "=", this.state.selectedConfigId]] : [["id", "=", 0]],
          fields,
          { order: "date desc", limit: 200 }
        );
      } catch (_) { raw = []; }

      this._allRecords = raw.map((r) => this._mapRecord(r));
      this._applyFilter();
    } catch (e) {
      console.error("[SwiftInventory] loadRecords failed:", e);
      this._allRecords = [];
      this.state.records = [];
    } finally {
      this.state.loading = false;
    }
  }

  _applyFilter() {
    const kw = (this.state.keyword || "").trim().toLowerCase();
    if (!kw) {
      this.state.records = this._allRecords.map((r) => ({ ...r }));
    } else {
      this.state.records = this._allRecords
        .filter((r) => String(r.code).toLowerCase().includes(kw))
        .map((r) => ({ ...r }));
    }
    this.state.checkAll = false;
  }

  // ─── event handlers ───────────────────────────────────────────

  onSearchInput(ev) {
    this.state.keyword = ev.target.value;
    clearTimeout(this._searchTimer);
    this._searchTimer = setTimeout(() => this._applyFilter(), 250);
  }

  toggleCheckAll() {
    const val = this.state.checkAll;
    this.state.records.forEach((r) => (r.selected = val));
  }

  toggleRow(r) {
    this.state.checkAll = this.state.records.every((row) => row.selected);
  }

  toggleStar(r) { r.starred = !r.starred; }

  openRow(r) {
    this.state.records.forEach((row) => (row.active = false));
    r.active = true;
    this.state.editId = r.id;
    this.state.view = "form";
  }

  onCreateInventory() {
    if (!this.state.selectedConfigId) {
      this.notification.add(_t("Please select a branch before creating an inventory voucher."), {
        type: "warning",
        title: _t("Notification"),
      });
      return;
    }
    this.state.editId = false;
    this.state.view = "form";
  }

  async onBranchChange(ev) {
    const selectedId = parseInt(ev.target.value, 10) || false;
    this.state.selectedConfigId = selectedId;
    const selected = this.state.configs.find((config) => config.id === selectedId);
    this.state.branchName = selected ? selected.name : _t("Branch");
    await this.loadRecords();
  }

  // ─── form callbacks ───────────────────────────────────────────

  onFormBack() {
    this.state.view = "list";
    this.state.editId = false;
  }

  async onFormSaved() {
    this.state.view = "list";
    this.state.editId = false;
    await this.loadRecords();
  }

  // ─── stubs ───────────────────────────────────────────────────

  exportExcel() {
    this.notification.add(_t("Excel export function is under development."), { type: "info", title: _t("Notification") });
  }
  exportPdf() {
    this.notification.add(_t("PDF export function is under development."), { type: "info", title: _t("Notification") });
  }
  openColumns() {
    this.notification.add(_t("Column options are under development."), { type: "info", title: _t("Notification") });
  }
  openSettings() {
    this.notification.add(_t("Settings are under development."), { type: "info", title: _t("Notification") });
  }
}

registry
  .category("actions")
  .add("pos_theme_swift.swift_pos_inventory_management", SwiftInventory);
