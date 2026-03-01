/** @odoo-module **/

import { Component, useState, onMounted, useRef } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";

export class SwiftInventoryForm extends Component {
  static template = "pos_theme_swift.SwiftInventoryForm";
  static props = {
    inventoryId: { type: [Number, Boolean], optional: true },
    branchName: { type: String, optional: true },
    onBack: { type: Function, optional: true },
    onSaved: { type: Function, optional: true },
  };

  setup() {
    this.orm = useService("orm");
    this.notification = useService("notification");
    this.fileRef = useRef("fileInput");
    this.searchRef = useRef("searchInput");

    this.state = useState({
      loading: false,
      saving: false,
      importing: false,
      tab: "all",
      filterKeyword: "",       // filters the existing lines table
      searchKeyword: "",       // live product search input
      searchResults: [],       // dropdown results
      searchLoading: false,
      showDropdown: false,
      note: "",
      status: "draft",
      autoCode: "Mã phiếu tự động",
      totalQtyActual: 0,
      sessionProducts: [],
      lines: [],
      filteredLines: [],
      now: this._formatNow(),
    });

    this._searchTimer = null;
    this._productSearchTimer = null;
    this._xlsxLoaded = false;

    // Bind methods used inside t-on-click arrow functions so `this` is always the component
    this.addProduct = this.addProduct.bind(this);
    this.deleteLine = this.deleteLine.bind(this);
    this.incrementQty = this.incrementQty.bind(this);
    this.decrementQty = this.decrementQty.bind(this);
    this.clearSearch = this.clearSearch.bind(this);

    onMounted(async () => {
      if (this.props.inventoryId) {
        await this._loadExistingInventory(this.props.inventoryId);
      }
    });
  }

  // ─── helpers ──────────────────────────────────────────────────

  _formatNow() {
    const d = new Date();
    const pad = (v) => String(v).padStart(2, "0");
    return `${pad(d.getDate())}/${pad(d.getMonth() + 1)}/${d.getFullYear()} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
  }

  _formatNumber(val) {
    const n = Number(val || 0);
    if (isNaN(n)) return "0";
    return n.toLocaleString("vi-VN");
  }

  // ─── load existing ────────────────────────────────────────────

  async _loadExistingInventory(id) {
    this.state.loading = true;
    try {
      const rec = await this.orm.call("pos.dashboard.swift", "get_inventory_detail", [id]);
      if (rec) {
        this.state.autoCode = rec.name || "Mã phiếu tự động";
        this.state.status = rec.state || "draft";
        this.state.note = rec.note || "";
        this.state.lines = (rec.lines || []).map((l) => ({
          id: l.product_id,
          barcode: l.barcode || "",
          name: l.product_name || "",
          uom: l.uom || "",
          qty_on_hand: l.qty_on_hand || 0,
          qty_actual: l.qty_actual || 0,
          diff: l.diff || 0,
          diff_value: l.diff_value || 0,
          price: l.price || 0,
        }));
        this._recalcTotal();
        this._applyFilter();
        this._refreshSessionProducts();
      }
    } catch (e) {
      console.error("[SwiftInventoryForm] _loadExistingInventory failed:", e);
    } finally {
      this.state.loading = false;
    }
  }

  // ─── xlsx loading ─────────────────────────────────────────────

  async _ensureXlsx() {
    if (window.XLSX) return true;
    // XLSX is loaded as a static asset (xlsx.mini.min.js) — it attaches to window.XLSX
    // Give it a moment if not yet available
    for (let i = 0; i < 10; i++) {
      if (window.XLSX) return true;
      await new Promise((r) => setTimeout(r, 100));
    }
    return !!window.XLSX;
  }

  // ─── filter & tab ─────────────────────────────────────────────

  _applyFilter() {
    const kw = (this.state.filterKeyword || "").trim().toLowerCase();
    const tab = this.state.tab;

    let result = this.state.lines;

    if (kw) {
      result = result.filter(
        (l) =>
          (l.barcode || "").toLowerCase().includes(kw) ||
          (l.name || "").toLowerCase().includes(kw)
      );
    }

    if (tab === "match") {
      result = result.filter((l) => l.diff === 0);
    } else if (tab === "diff") {
      result = result.filter((l) => l.diff !== 0);
    } else if (tab === "unchecked") {
      result = result.filter((l) => l.qty_on_hand === l.qty_actual && l.qty_on_hand === 0);
    }

    this.state.filteredLines = result;
  }

  _refreshSessionProducts() {
    this.state.sessionProducts = this.state.lines.map((l) => ({
      name: l.name,
      qty: l.qty_actual,
    }));
  }

  tabCount(tab) {
    const lines = this.state.lines;
    if (tab === "all") return lines.length;
    if (tab === "match") return lines.filter((l) => l.diff === 0).length;
    if (tab === "diff") return lines.filter((l) => l.diff !== 0).length;
    if (tab === "unchecked") return lines.filter((l) => l.qty_on_hand === l.qty_actual && l.qty_on_hand === 0).length;
    return 0;
  }

  // ─── event handlers ───────────────────────────────────────────

  setTab(tab) {
    this.state.tab = tab;
    this._applyFilter();
  }

  // ── Top-bar: live product search ───────────────────────────────

  onProductSearchInput(ev) {
    const val = ev.target.value;
    this.state.searchKeyword = val;
    clearTimeout(this._productSearchTimer);
    if (!val.trim()) {
      this.state.searchResults = [];
      this.state.showDropdown = false;
      return;
    }
    this.state.showDropdown = true;
    this.state.searchLoading = true;
    this._productSearchTimer = setTimeout(async () => {
      try {
        const results = await this.orm.call(
          "pos.dashboard.swift",
          "get_inventory_products",
          [val.trim()]
        );
        this.state.searchResults = results || [];
      } catch (e) {
        console.error("[SwiftInventoryForm] product search:", e);
        this.state.searchResults = [];
      } finally {
        this.state.searchLoading = false;
      }
    }, 250);
  }

  onProductSearchKeydown(ev) {
    if (ev.key === "Escape") {
      this.clearSearch();
    }
  }

  clearSearch() {
    this.state.searchKeyword = "";
    this.state.searchResults = [];
    this.state.showDropdown = false;
  }

  addProduct(p) {
    const existing = this.state.lines.find((l) => l.id === p.id);
    if (existing) {
      this.onQtyChange(existing, existing.qty_actual + 1);
    } else {
      const qtyActual = 1;
      const diff = qtyActual - (p.qty_on_hand || 0);
      this.state.lines.push({
        id: p.id,
        barcode: p.barcode || "",
        name: p.name || "",
        uom: p.uom || "",
        qty_on_hand: p.qty_on_hand || 0,
        qty_actual: qtyActual,
        diff,
        diff_value: diff * (p.price || 0),
        price: p.price || 0,
      });
      this._recalcTotal();
      this._refreshSessionProducts();
      this._applyFilter();
    }
    // Keep dropdown open so user can keep scanning / adding quickly.
    // Focus back to input
    if (this.searchRef.el) this.searchRef.el.focus();
  }

  // ── Tab-filter (filter lines already in the list) ──────────────

  onFilterInput(ev) {
    this.state.filterKeyword = ev.target.value;
    clearTimeout(this._searchTimer);
    this._searchTimer = setTimeout(() => this._applyFilter(), 200);
  }

  onQtyChange(line, val) {
    const n = parseFloat(val) || 0;
    line.qty_actual = n;
    line.diff = n - line.qty_on_hand;
    line.diff_value = line.diff * line.price;
    this._recalcTotal();
    this._refreshSessionProducts();
    this._applyFilter();
  }

  incrementQty(line) {
    this.onQtyChange(line, line.qty_actual + 1);
  }

  decrementQty(line) {
    this.onQtyChange(line, Math.max(0, line.qty_actual - 1));
  }

  deleteLine(line) {
    const idx = this.state.lines.indexOf(line);
    if (idx !== -1) this.state.lines.splice(idx, 1);
    this._recalcTotal();
    this._refreshSessionProducts();
    this._applyFilter();
  }

  _recalcTotal() {
    this.state.totalQtyActual = this.state.lines.reduce(
      (acc, l) => acc + (l.qty_actual || 0), 0
    );
  }

  onChooseFile() {
    this.fileRef.el && this.fileRef.el.click();
  }

  onBack() {
    if (this.props.onBack) this.props.onBack();
  }

  // ─── Excel / CSV import ───────────────────────────────────────

  async onFileChange(ev) {
    const file = ev.target.files && ev.target.files[0];
    if (!file) return;

    this.state.importing = true;
    ev.target.value = ""; // reset so re-select works

    try {
      const rows = await this._parseFile(file);
      if (!rows || rows.length === 0) {
        this.notification.add("File không có dữ liệu hàng hóa.", { type: "warning", title: "Nhập file" });
        return;
      }
      await this._importRows(rows);
    } catch (e) {
      console.error("[SwiftInventoryForm] onFileChange:", e);
      this.notification.add("Lỗi khi đọc file. Vui lòng kiểm tra định dạng.", { type: "danger", title: "Nhập file" });
    } finally {
      this.state.importing = false;
    }
  }

  async _parseFile(file) {
    const name = (file.name || "").toLowerCase();
    if (name.endsWith(".csv")) {
      return this._parseCsv(file);
    }
    // Excel: try XLSX (bundled as static asset exposes window.XLSX)
    const ok = await this._ensureXlsx();
    if (ok) {
      return this._parseXlsx(file);
    }
    // Fallback: try to read as text CSV even if .xlsx
    return this._parseCsv(file);
  }

  _parseCsv(file) {
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = (e) => {
        try {
          const text = e.target.result;
          const lines = text.split(/\r?\n/).filter(Boolean);
          if (!lines.length) { resolve([]); return; }
          const header = lines[0].split(/[,;\t]/).map((h) => h.trim().toLowerCase());
          const rows = [];
          for (let i = 1; i < lines.length; i++) {
            const cells = lines[i].split(/[,;\t]/);
            const row = {};
            header.forEach((h, idx) => { row[h] = (cells[idx] || "").trim(); });
            rows.push(row);
          }
          resolve(rows);
        } catch (err) { reject(err); }
      };
      reader.onerror = reject;
      reader.readAsText(file, "UTF-8");
    });
  }

  _parseXlsx(file) {
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = (e) => {
        try {
          const data = new Uint8Array(e.target.result);
          const wb = window.XLSX.read(data, { type: "array" });
          const ws = wb.Sheets[wb.SheetNames[0]];
          const jsonRows = window.XLSX.utils.sheet_to_json(ws, { defval: "" });
          // Normalize keys to lowercase
          const rows = jsonRows.map((r) => {
            const norm = {};
            Object.entries(r).forEach(([k, v]) => { norm[k.trim().toLowerCase()] = String(v || "").trim(); });
            return norm;
          });
          resolve(rows);
        } catch (err) { reject(err); }
      };
      reader.onerror = reject;
      reader.readAsArrayBuffer(file);
    });
  }

  // Map Excel row → { barcode, qty }
  _extractRowData(row) {
    // Find barcode key (mã hàng / barcode / sku / ma hang / mã vạch / ma_hang)
    const barcodeKeys = ["mã hàng", "ma hang", "barcode", "sku", "mã vạch", "ma_hang", "ma vach", "mã_hàng", "barcodes"];
    // Find qty key (thực tế / thuc te / qty / sl thực tế / số lượng / so luong)
    const qtyKeys = ["thực tế", "thuc te", "qty", "sl thực tế", "sl thuc te", "số lượng", "so luong", "quantity", "thuc_te", "sl"];

    let barcode = "";
    for (const k of barcodeKeys) {
      if (row[k] !== undefined && row[k] !== "") { barcode = String(row[k]).trim(); break; }
    }
    // If no barcode key found, use the first column
    if (!barcode) {
      const firstKey = Object.keys(row)[0];
      if (firstKey) barcode = String(row[firstKey] || "").trim();
    }

    let qty = 1;
    for (const k of qtyKeys) {
      if (row[k] !== undefined && row[k] !== "") {
        const parsed = parseFloat(String(row[k]).replace(",", "."));
        if (!isNaN(parsed)) { qty = parsed; break; }
      }
    }

    return barcode ? { barcode, qty } : null;
  }

  async _importRows(rows) {
    // Extract barcode + qty pairs
    const items = rows.map((r) => this._extractRowData(r)).filter(Boolean);
    if (!items.length) {
      this.notification.add("Không tìm thấy cột mã hàng trong file.", { type: "warning", title: "Nhập file" });
      return;
    }

    const barcodes = [...new Set(items.map((i) => i.barcode))];

    // Look up products from server
    let products = [];
    try {
      products = await this.orm.call(
        "pos.dashboard.swift",
        "get_products_by_barcodes",
        [barcodes]
      );
    } catch (e) {
      console.error("[SwiftInventoryForm] get_products_by_barcodes:", e);
      this.notification.add("Không thể kết nối server để tra cứu sản phẩm.", { type: "danger" });
      return;
    }

    // Build a lookup map
    const productMap = {};
    for (const p of products) {
      if (p.barcode) productMap[p.barcode] = p;
    }

    let found = 0;
    let notFound = 0;

    for (const item of items) {
      const p = productMap[item.barcode];
      if (!p) { notFound++; continue; }
      found++;

      // Check if already in lines
      const existing = this.state.lines.find((l) => l.id === p.id);
      if (existing) {
        existing.qty_actual += item.qty;
        existing.diff = existing.qty_actual - existing.qty_on_hand;
        existing.diff_value = existing.diff * existing.price;
      } else {
        const qtyActual = item.qty;
        const diff = qtyActual - (p.qty_on_hand || 0);
        this.state.lines.push({
          id: p.id,
          barcode: p.barcode || item.barcode,
          name: p.name || "",
          uom: p.uom || "",
          qty_on_hand: p.qty_on_hand || 0,
          qty_actual: qtyActual,
          diff,
          diff_value: diff * (p.price || 0),
          price: p.price || 0,
        });
      }
    }

    this._recalcTotal();
    this._refreshSessionProducts();
    this._applyFilter();

    if (notFound > 0) {
      this.notification.add(
        `Đã nhập ${found} sản phẩm. ${notFound} mã hàng không tìm thấy trong hệ thống.`,
        { type: "warning", title: "Nhập file" }
      );
    } else {
      this.notification.add(
        `Đã nhập ${found} sản phẩm thành công.`,
        { type: "success", title: "Nhập file" }
      );
    }
  }

  // ─── save ─────────────────────────────────────────────────────

  async onSave() { await this._submit("draft"); }
  async onComplete() { await this._submit("done"); }

  async _submit(state) {
    if (this.state.saving) return;
    this.state.saving = true;
    try {
      const lines = this.state.lines.map((l) => ({
        product_id: l.id,
        qty_actual: l.qty_actual || 0,
      }));
      const result = await this.orm.call("pos.dashboard.swift", "create_or_update_inventory", [{
        id: this.props.inventoryId || false,
        note: this.state.note || "",
        state,
        lines,
      }]);
      const label = state === "done" ? "Đã hoàn thành kiểm kho." : "Đã lưu phiếu tạm.";
      this.notification.add(label, { type: "success", title: "Kiểm kho" });
      if (this.props.onSaved) this.props.onSaved(result);
    } catch (e) {
      console.error("[SwiftInventoryForm] _submit failed:", e);
      this.notification.add("Lỗi khi lưu phiếu kiểm kho.", { type: "danger", title: "Lỗi" });
    } finally {
      this.state.saving = false;
    }
  }
}
