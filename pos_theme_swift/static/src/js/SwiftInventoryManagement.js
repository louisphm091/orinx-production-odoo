/** @odoo-module **/

import { registry } from "@web/core/registry";
import { Component, useState, onMounted } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";
import { _t } from "@web/core/l10n/translation";
import { SwiftInventoryForm } from "./SwiftInventoryForm";

export class SwiftInventory extends Component {
  static template = "pos_theme_swift.SwiftInventory";
  static components = { SwiftInventoryForm };

  setup() {
    this.orm = useService("orm");
    this.action = useService("action");
    this.notification = useService("notification");

    this.state = useState({
      loading: true,
      keyword: "",
      checkAll: false,
      records: [],
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

    onMounted(async () => {
      await this._loadBranch();
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

  async _loadBranch() {
    try {
      const configs = await this.orm.searchRead(
        "pos.config", [], ["name"], { limit: 1 }
      );
      this.state.branchName = configs.length ? configs[0].name : _t("Branch");
    } catch (_) {
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
          "swift.stock.inventory", [], fields,
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
    this.state.editId = false;
    this.state.view = "form";
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

