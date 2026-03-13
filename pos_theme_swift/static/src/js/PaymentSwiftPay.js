import { useRef, onMounted, onPatched } from "@odoo/owl";
import { _t } from "@web/core/l10n/translation";
import { patch } from "@web/core/utils/patch";
import { PaymentScreen } from "@point_of_sale/app/screens/payment_screen/payment_screen";
import { PosOrder } from "@point_of_sale/app/models/pos_order";

import { CashierName } from "@point_of_sale/app/components/navbar/cashier_name/cashier_name";

patch(PaymentScreen, {
  components: {
    ...(PaymentScreen.components || {}),
    CashierName,
  },
});

patch(PosOrder.prototype, {
  get isCustomerRequired() {
    if (this.partner_id) {
      return false;
    }
    const splitPayment = this.payment_ids.some(
      (payment) =>
        payment.payment_method_id &&
        payment.payment_method_id.split_transactions,
    );
    const invalidPartnerPreset =
      (this.preset_id?.needsName && !this.floating_order_name) ||
      this.preset_id?.needsPartner;
    return invalidPartnerPreset || this.isToInvoice() || Boolean(splitPayment);
  },
});

patch(PaymentScreen.prototype, {
  setup() {
    this._t = _t;
    super.setup();
    // Force reset Odoo's internal buffer to prevent interference on refresh
    try {
        if (this.numberBuffer) {
            this.numberBuffer.reset();
        }
    } catch(e) {
        console.warn("[Sapphire] Failed to reset numberBuffer:", e);
    }

    this.sapphireInput = useRef("sapphireInput");
    onMounted(() => this._syncSapphireInput());
    onPatched(() => this._syncSapphireInput());

    try {
      // Robust order detection on refresh
      const order = this.sppOrder();
      if (order && (order.payment_ids || order.payment_line_ids)) {
        const pls = this.sppPaymentlines(order);
        // Only clean if we are absolutely sure the structure is wrong
        const badLines = pls.filter(
          (p) => p && !this.sppPaymentlineMethod(p)
        );
        for (const bad of badLines) {
          console.warn("[Sapphire] Removing invalid payment line:", bad);
          if (typeof bad.delete === "function") bad.delete();
          else if (order.remove_paymentline) order.remove_paymentline(bad);
        }
      }
    } catch (e) {
      console.error("[Sapphire] Error during order state restoration:", e);
    }
  },

  _syncSapphireInput() {
    const input = this.sapphireInput.el;
    if (!input) return;
    // Do not sync if user is focusing or if we flagged as editing
    if (this.isSapphireEditing || document.activeElement === input) return;

    const order = this.sppOrder();
    const summary = this.getSapphireSummary(order);
    const val = summary?.amount_paid || 0;
    const formatted = this.formatSapphireNumber(val, true);
    if (input.value !== formatted) {
      input.value = formatted;
    }
  },

  onSapphireSearchInput(ev) {
    const v = ev?.target?.value ?? "";
    this.pos.searchProductWord = v;
  },

  onSapphireSearchKeydown(ev) {
    if (ev.key === "Enter") {
      ev.preventDefault();
      ev.stopPropagation();
      ev.stopImmediatePropagation?.();
      // Stay on PaymentScreen
      return;
    }
    if (ev.key === "F3") {
      ev.preventDefault();
      ev.stopPropagation();
      ev.stopImmediatePropagation?.();
      ev.target?.focus?.();
    }
  },
  _idOf(x) {
    if (!x) return null;
    if (typeof x === "number" || typeof x === "string") return x;
    if (typeof x === "object") return x.id ?? x[0] ?? x.res_id ?? null;
    return null;
  },
  sppOrder() {
    const pos = this.pos;
    if (!pos) return null;

    // Check various ways Odoo stores the current order
    const order = pos.getOrder?.() || pos.get_order?.() || pos.selectedOrder || null;
    if (order) return order;

    const OrderModel = pos.models?.["pos.order"];
    const uuid = pos.selectedOrderUuid || pos.selected_order_uuid;
    if (OrderModel?.get && uuid) return OrderModel.get(uuid) || null;

    // On refresh, sometimes we need to wait or check getAll
    if (OrderModel?.getAll) {
        const all = OrderModel.getAll();
        if (all.length > 0) return all[0];
    }

    return null;
  },
  sppPaymentlines(order) {
    if (!order) return [];
    const pids = order.payment_ids || order.paymentIds;
    if (Array.isArray(pids) && pids.length) {
      const first = pids[0];
      if (
        first &&
        typeof first === "object" &&
        ("amount" in first || "payment_method_id" in first)
      ) {
        return pids;
      }
    }

    const direct =
      order.get_paymentlines?.() ||
      order.paymentlines ||
      order.paymentLines ||
      order.payments;

    if (Array.isArray(direct) && direct.length) return direct;

    const ids = order.payment_line_ids || order.paymentLineIds;

    const PaymentModel =
      this.pos?.models?.["pos.payment"] ||
      this.pos?.models?.["pos.payment.line"];
    if (Array.isArray(ids) && ids.length && PaymentModel?.get) {
      const res = ids.map((id) => PaymentModel.get(id)).filter(Boolean);
      if (res.length) return res;
    }

    return [];
  },

  sppMethods() {
    const pos = this.pos;
    const a = pos?.payment_methods || pos?.paymentMethods;
    if (Array.isArray(a) && a.length) return a;

    const models = pos?.models || {};
    const pmModel =
      models["pos.payment.method"] ||
      models["payment.method"] ||
      models["payment_method"] ||
      models["payment_methods"] ||
      models["pos_payment_method"];

    const fromModel =
      (pmModel && typeof pmModel.getAll === "function" && pmModel.getAll()) ||
      pmModel?.records ||
      pmModel?.data ||
      null;

    if (Array.isArray(fromModel) && fromModel.length) return fromModel;

    const ids = pos?.config?.payment_method_ids;
    if (Array.isArray(ids) && ids.length && pmModel?.get) {
      const res = ids.map((id) => pmModel.get(id)).filter(Boolean);
      if (res.length) return res;
    }

    return [];
  },
  sppSelectedPaymentline(order) {
    if (!order) return null;

    const a =
      order.get_selected_paymentline?.() ||
      order.selected_paymentline ||
      order.selectedPaymentline ||
      null;
    if (a) return a;
    const selId =
      order.uiState?.selectedPaymentlineId ||
      order.uiState?.selected_paymentline_id ||
      order.uiState?.selected_paymentline ||
      null;

    if (!selId) return null;

    const id = Array.isArray(selId) ? selId[0] : selId;
    const pls = this.sppPaymentlines(order);
    return pls.find((pl) => this._idOf(pl) === id) || null;
  },

  sppSelectPaymentline(order, line) {
    if (!order || !line) return;

    if (typeof order.select_paymentline === "function") {
      order.select_paymentline(line);
      return;
    }

    if (order.uiState) {
      const id = this._idOf(line);
      if (id) {
        order.uiState.selectedPaymentlineId = id;
        order.uiState.selected_paymentline_id = id;
      }
    }
  },

  sppPaymentlineMethod(line) {
    return (
      line?.payment_method ||
      line?.payment_method_id ||
      line?.paymentMethod ||
      line?.paymentMethodId ||
      null
    );
  },

  isSapphireMethodSelected(order, method) {
    if (!order || !method) return false;
    const line = this.sppSelectedPaymentline(order);
    const pm = this.sppPaymentlineMethod(line);
    return this._idOf(pm) && this._idOf(pm) === this._idOf(method);
  },

  async onSapphireSelectMethod(ev, method) {
    if (ev) {
      ev.preventDefault();
      ev.stopPropagation();
      ev.stopImmediatePropagation?.();
    }

    const order = this.sppOrder();
    if (!order || !method) return;

    const methodId = this._idOf(method);
    if (!methodId) return;

    const pls = this.sppPaymentlines(order);

    const existing = pls.find(
      (l) => this._idOf(this.sppPaymentlineMethod(l)) === methodId,
    );
    if (existing) {
      this.sppSelectPaymentline(order, existing);
      order.trigger?.("change", order);
      this.render?.();
      return;
    }

    try {
      if (typeof order.add_paymentline === "function") {
        const ok = order.add_paymentline(method);
        if (ok === false) return;
      } else if (typeof this.addNewPaymentLine === "function") {
        await this.addNewPaymentLine(method);
      }
    } catch (e) {
      const pls2 = this.sppPaymentlines(order);
      const again = pls2.find(
        (l) => this._idOf(this.sppPaymentlineMethod(l)) === methodId,
      );
      if (again) {
        this.sppSelectPaymentline(order, again);
        order.trigger?.("change", order);
        this.render?.();
        return;
      }
      return;
    }

    const after = this.sppPaymentlines(order);
    const last = after[after.length - 1];
    if (last) this.sppSelectPaymentline(order, last);

    order.trigger?.("change", order);
    this.render?.();
  },

  getSapphireSummary(order) {
    if (!order) return null;

    const lines = order.get_orderlines?.() || order.lines || [];

    const items_count = lines.reduce((s, l) => s + (Number(l.qty) || 0), 0);

    // ---- total_items: ưu tiên subtotal_incl/tổng có thuế từ line ----
    const total_items = lines.reduce((s, l) => {
      // Odoo store thường có 1 trong các field này:
      const subtotalIncl = Number(
        l.price_subtotal_incl ??
          l.priceSubtotalIncl ??
          l.total_incl ??
          l.totalIncl ??
          l.price_with_tax ??
          l.priceWithTax,
      );

      if (!Number.isNaN(subtotalIncl) && subtotalIncl !== 0) {
        return s + subtotalIncl;
      }

      // fallback: tự tính (không đảm bảo thuế, nhưng không bao giờ ra 0 sai)
      const qty = Number(l.qty) || 0;
      const unit = Number(l.price_unit ?? l.priceUnit) || 0;
      const disc = Number(l.discount) || 0;
      const lineTotal = unit * qty * (1 - disc / 100);
      return s + (Number.isFinite(lineTotal) ? lineTotal : 0);
    }, 0);

    // ---- amount_paid: vẫn tính từ payment lines như bạn đang làm ----
    const pls = this.sppPaymentlines(order);
    const amount_paid = pls.reduce((s, pl) => {
      const a = Number(pl.amount ?? pl.payment_amount ?? 0) || 0;
      return s + a;
    }, 0);
    const discount_total = lines.reduce((s, l) => {
      const qty = Number(l.qty) || 0;
      const unit = Number(l.price_unit ?? l.priceUnit) || 0;
      const disc = Number(l.discount) || 0;
      return s + unit * qty * (disc / 100);
    }, 0);

    const other_charges = 0;

    // total_items derived from subtotalIncl is already net (discount subtracted)
    // So need_to_pay should be total_items + other_charges.
    const need_to_pay = Math.max(total_items + other_charges, 0);
    const amount_due = Math.max(need_to_pay - amount_paid, 0);

    return {
      items_count,
      total_items,
      discount_total,
      other_charges,
      need_to_pay,
      amount_due,
      amount_paid,
    };
  },

  onSapphireStopPropagation(ev) {
    ev.stopPropagation();
    ev.stopImmediatePropagation?.();
    // Do not preventDefault here so the input still works
  },

  onSapphireAmountPaidFocus(ev) {
    this.isSapphireEditing = true;
    ev.target.select();
  },

  onSapphireAmountPaidBlur(ev) {
    this.isSapphireEditing = false;
    this.render?.();
  },

  async onSapphireAmountPaidInput(ev) {
    ev.stopPropagation();
    ev.stopImmediatePropagation?.();

    const input = ev.target;
    if (!input) return;

    const start = input.selectionStart;
    const oldLength = input.value.length;

    // Scrub everything but digits
    const digits = input.value.replace(/\D/g, "");
    const next = parseInt(digits, 10) || 0;

    // Format new value with symbol
    const formatted = this.formatSapphireNumber(next, true);

    // Direct value assignment to avoid Owl interference
    if (input.value !== formatted) {
      input.value = formatted;

      // Adjust cursor position to feel natural
      const newLength = formatted.length;
      let newPos = start + (newLength - oldLength);
      // Keep cursor before the currency symbol " đ"
      if (newPos > newLength - 2) newPos = newLength - 2;
      if (newPos < 0) newPos = 0;

      try {
        input.setSelectionRange(newPos, newPos);
      } catch (e) {
        // Silently ignore selection errors on some browsers/states
      }
    }

    const order = this.sppOrder();
    if (!order) return;

    const pls = this.sppPaymentlines(order);
    let line =
      this.sppSelectedPaymentline(order) || (pls.length ? pls[0] : null);

    if (!line) {
      const methods = this.sppMethods();
      if (!methods.length) return;
      await this.onSapphireSelectMethod(null, methods[0]);
      const pls2 = this.sppPaymentlines(order);
      line =
        this.sppSelectedPaymentline(order) || (pls2.length ? pls2[0] : null);
      if (!line) return;
    }

    order.select_paymentline?.(line);

    if (!line || typeof line !== "object") {
        console.error("[Sapphire] No valid payment line to update.");
        return;
    }

    console.log("[Sapphire] Updating line amount:", {
        method: this.sppPaymentlineMethod(line)?.name,
        prev: line.amount,
        next: next
    });

    // Update amount in the store
    if (typeof line.update === "function") line.update({ amount: next });
    else if (typeof line.set_amount === "function") line.set_amount(next);
    else if (typeof line.setAmount === "function") line.setAmount(next);
    else line.amount = next;

    // Trigger changes to update the summary rows reactively
    line.trigger?.("change", line);
    order.trigger?.("change", order);
  },

  async onSapphireQuickPay(ev, amount) {
    if (ev) {
      ev.preventDefault();
      ev.stopPropagation();
      ev.stopImmediatePropagation?.();
    }

    const order = this.sppOrder();
    if (!order) return;

    // Read current value from input if available, else from order
    let cur = 0;
    const input = this.sapphireInput.el;
    if (input) {
        cur = parseInt(input.value.replace(/\D/g, ""), 10) || 0;
    } else {
        const summary = this.getSapphireSummary(order);
        cur = summary?.amount_paid || 0;
    }

    const add = Number(amount) || 0;
    const next = cur + add;

    // Update input display and force focus/editing state
    if (input) {
        input.value = String(next);
        input.focus();
        this.isSapphireEditing = true;
    }

    const pls = this.sppPaymentlines(order);

    let line =
      this.sppSelectedPaymentline(order) || (pls.length ? pls[0] : null);

    if (!line) {
      const methods = this.sppMethods();
      if (!methods.length) return;
      await this.onSapphireSelectMethod(null, methods[0]);
      const pls2 = this.sppPaymentlines(order);
      line =
        this.sppSelectedPaymentline(order) || (pls2.length ? pls2[0] : null);
      if (!line) return;
    }

    order.select_paymentline?.(line);

    if (!line || typeof line !== "object") {
        console.error("[Sapphire] No valid payment line for QuickPay.");
        return;
    }

    console.log("[Sapphire] QuickPay update:", {
        method: this.sppPaymentlineMethod(line)?.name,
        cur: cur,
        add: add,
        next: next
    });

    // Update store
    if (typeof line.update === "function") line.update({ amount: next });
    else if (typeof line.set_amount === "function") line.set_amount(next);
    else if (typeof line.setAmount === "function") line.setAmount(next);
    else line.amount = next;

    line.trigger?.("change", line);
    order.trigger?.("change", order);
    this.render?.();
  },
  getSapphireQuickAmounts() {
    return [50000, 100000, 200000, 500000];
  },

  formatSapphireNumber(v, showSymbol = false) {
    try {
      const formatted = new Intl.NumberFormat("vi-VN").format(Number(v) || 0);
      return showSymbol ? `${formatted} đ` : formatted;
    } catch {
      const num = String(Number(v) || 0);
      return showSymbol ? `${num} đ` : num;
    }
  },

  getSppMethodName(method) {
    if (!method) return "";
    if (method.type === "pay_later") {
      return _t("Transfer");
    }
    return method.name || "";
  },

  isSapphireTransferSelected(order) {
    if (!order) return false;
    const line = this.sppSelectedPaymentline(order);
    const pm = this.sppPaymentlineMethod(line);
    return pm?.type === "pay_later";
  },

  sppIsToInvoice(order) {
    if (!order) return false;
    if (typeof order.isToInvoice === "function") return !!order.isToInvoice();
    if (typeof order.is_to_invoice === "function")
      return !!order.is_to_invoice();
    if (typeof order.to_invoice === "boolean") return order.to_invoice;
    if (typeof order.toInvoice === "boolean") return order.toInvoice;

    // một số build để trong uiState
    if (order.uiState && typeof order.uiState.to_invoice === "boolean")
      return order.uiState.to_invoice;

    return false;
  },

  async onSapphirePrint(ev) {
    if (ev) {
      ev.preventDefault();
      ev.stopPropagation();
    }
    const order = this.sppOrder();
    if (order) {
        await this.pos.printReceipt({ order });
    }
  },
  async onSapphirePay(ev) {
    if (ev) {
      ev.preventDefault();
      ev.stopPropagation();
      ev.stopImmediatePropagation?.();
    }

    // PaymentScreen chuẩn có validateOrder()
    if (typeof this.validateOrder === "function") {
      await this.validateOrder();
      return;
    }

    // fallback (nếu build rename)
    if (typeof this._validateOrder === "function") {
      await this._validateOrder();
      return;
    }

    // cuối cùng: thử click nút validate gốc nếu vẫn tồn tại trong DOM
    const btn =
      this.el?.querySelector?.("button.validate") ||
      this.el?.querySelector?.("button.button.validate");
    btn?.click?.();
  },

  // --- Consistently provide methods for the item table (moved from PaymentScreenPatch.js) ---
  sppOrderlines(order) {
    return (
      order?.get_orderlines?.() ||
      order?.getOrderlines?.() ||
      order?.lines ||
      []
    );
  },
  sppLineKey(line, i) {
    return (
      line?.uuid || line?.uid || line?.id || line?.cid || (line?.product?.id ? `p-${line.product.id}-${i}` : `l-${i}`)
    );
  },
  sppLineQty(line) {
    const q = (line?.get_quantity && line.get_quantity()) ?? line?.quantity ?? line?.qty ?? 0;
    return Number.isFinite(Number(q)) ? Number(q) : 0;
  },
  sppLineUnitPrice(line) {
    const u = (line?.get_unit_price && line.get_unit_price()) ?? line?.price_unit ?? line?.unit_price ?? 0;
    return Number.isFinite(Number(u)) ? Number(u) : 0;
  },
  sppLineTotal(line) {
    const v = (line?.get_display_price && line.get_display_price()) ?? (line?.get_price_with_tax && line.get_price_with_tax()) ?? line?.price_subtotal_incl ?? line?.price_subtotal ?? (this.sppLineQty(line) * this.sppLineUnitPrice(line));
    return Number.isFinite(Number(v)) ? Number(v) : 0;
  },
  sppLineName(line) {
    return line?.full_product_name || (line?.getFullProductName && line.getFullProductName()) || line?.product?.display_name || "Item";
  },
  sppLineBarcode(line) {
    return line?.product?.barcode || line?.product?.default_code || "";
  },
  sppIndexOf(line) {
    const order = this.sppOrder();
    const lines = this.sppOrderlines(order);
    const idx = lines.indexOf(line);
    return idx >= 0 ? idx : 0;
  },
  onSapphireSearchInput(ev) {
    const v = ev?.target?.value ?? "";
    this.pos.searchProductWord = v;
  },
  onSapphireSearchKeydown(ev) {
    if (ev?.key === "Enter") {
      ev.preventDefault(); ev.stopPropagation(); ev.stopImmediatePropagation?.();
      return;
    }
    if (ev?.key === "F3") {
      ev.preventDefault(); ev.stopPropagation(); ev.stopImmediatePropagation?.();
      ev.target?.focus?.();
    }
  },
  sppIncQty(line) {
    const order = this.sppOrder();
    if (!order || !line) return;
    const qty = this.sppLineQty(line) + 1;
    if (typeof line.set_quantity === "function") line.set_quantity(qty);
    else if (typeof line.setQuantity === "function") line.setQuantity(qty);
    else line.qty = qty;
    order.trigger?.("change", order);
    this.render?.();
  },
  sppDecQty(line) {
    const order = this.sppOrder();
    if (!order || !line) return;
    const current = this.sppLineQty(line);
    if (current <= 1) { this.sppRemoveLine(line); return; }
    const newQty = current - 1;
    if (typeof line.set_quantity === "function") line.set_quantity(newQty);
    else if (typeof line.setQuantity === "function") line.setQuantity(newQty);
    else line.qty = newQty;
    order.trigger?.("change", order);
    this.render?.();
  },
  sppRemoveLine(line) {
    const order = this.sppOrder();
    if (!order || !line) return;
    if (order.remove_orderline) order.remove_orderline(line);
    else if (line.delete) line.delete();
    else if (line.set_quantity) line.set_quantity(0);
    order.trigger?.("change", order);
    this.render?.();
  },
  onSppIncLine(ev, line) {
    ev?.preventDefault(); ev?.stopPropagation();
    const order = this.sppOrder();
    if (!order || !line) return;
    const next = this.sppLineQty(line) + 1;
    if (typeof line.set_quantity === "function") line.set_quantity(next);
    else line.qty = next;
    order.trigger("change", order);
    this.render();
  },
  onSppDecLine(ev, line) {
    ev?.preventDefault(); ev?.stopPropagation();
    const order = this.sppOrder();
    if (!order || !line) return;
    const cur = this.sppLineQty(line);
    const next = Math.max(cur - 1, 0);
    if (next <= 0) {
      if (order.remove_orderline) order.remove_orderline(line);
      else if (line.delete) line.delete();
    } else {
      if (typeof line.set_quantity === "function") line.set_quantity(next);
      else line.qty = next;
    }
    order.trigger("change", order);
    this.render();
  },
  getPaymentLines() { // Renamed or used for Item table in XML
    const order = this.sppOrder();
    const lines = this.sppOrderlines(order);
    return (lines || []).map((line) => {
      const product = line.product;
      const imageUrl = `/web/image?model=product.product&id=${product.id}&field=image_128&unique=${product.write_date}`;
      return {
        id: line.uid || line.id || line.cid,
        name: this.sppLineName(line),
        qty: this.sppLineQty(line),
        unitPrice: this.formatSapphireNumber(this.sppLineUnitPrice(line)),
        total: this.formatSapphireNumber(this.sppLineTotal(line)),
        imageUrl,
        _line: line,
      };
    });
  },

  getOrderTabs() {
    const orders = (this.pos?.getOpenOrders?.() || []).filter((o) => o && !o.table_id);
    return orders.map((order, idx) => ({
      order,
      // uuid/cid are always unique even for unsaved orders; never use name alone (new orders have name '/')
      key: order.uuid || order.cid || order.uid || `order-${idx}`,
      label: _t("Order %s", idx + 1),
    }));
  },

  getFilteredProducts() {
    const word = (this.pos?.searchProductWord || "").trim().toLowerCase();
    if (!word) return [];
    const products = this.pos?.models["product.product"]?.filter((p) => {
      return (
        (p.display_name && p.display_name.toLowerCase().includes(word)) ||
        (p.barcode && String(p.barcode).includes(word)) ||
        (p.default_code && String(p.default_code).toLowerCase().includes(word))
      );
    }) || [];
    return products.slice(0, 10);
  },

  async onSapphireAddProduct(product) {
    if (!product) return;
    const tmpl = product.product_tmpl_id;
    // Skip variant configurator (Size/Color popup) when selecting a specific variant from search.
    // We only keep configuration enabled for Combo products, Tracked products (Lots), or Weighted products.
    const needsConfig = tmpl?.isCombo?.() || tmpl?.isTracked?.() || tmpl?.to_weight;
    await this.pos.addLineToCurrentOrder({
      product_id: product,
      product_tmpl_id: tmpl,
    }, {}, !!needsConfig);
    this.pos.searchProductWord = "";
    this.render?.();
  },

  onSppSelectLine(ev, line) {
    ev?.preventDefault?.(); ev?.stopPropagation?.();
    const order = this.sppOrder();
    if (!order || !line) return;
    if (typeof order.select_orderline === "function") order.select_orderline(line);
    else if (typeof order.set_selected_orderline === "function") order.set_selected_orderline(line);
    order.trigger?.("change", order);
    this.render?.();
  },

  onSppRemoveLine(ev, line) {
    ev?.preventDefault?.(); ev?.stopPropagation?.();
    const order = this.sppOrder();
    if (!order || !line) return;
    if (order.remove_orderline) order.remove_orderline(line);
    else if (line.delete) line.delete();
    order.trigger?.("change", order);
    this.render?.();
  },

  onSppOpenLineMore(ev, line) {
    ev?.preventDefault?.(); ev?.stopPropagation?.();
    console.log("[Sapphire] more line:", line);
  },

  sppLineUnit(line) { return this.sppLineUnitPrice(line); },
  sppLineUnitPriceValue(line) { return this.sppLineUnitPrice(line); },
  async closeSession() {
    // Show a confirmation dialog before closing the session
    const confirmed = window.confirm(_t("Are you sure you want to close the sales session?"));
    if (!confirmed) return;

    try {
      const orm = this.env?.services?.orm;
      const sessionId = this.pos?.session?.id || this.pos?.session_id?.[0];

      if (orm && sessionId) {
        // Call the backend to properly set session state to 'closing_control'
        await orm.call("pos.session", "action_pos_session_closing_control", [[sessionId]], {});
      }
    } catch (e) {
      console.warn("[Sapphire] Could not call action_pos_session_closing_control:", e);
    }

    // Navigate back to backend regardless of RPC result
    window.location.href = "/odoo/point-of-sale";
  },
  onSapphireBackend() {
    // Direct navigation to backend dashboard, bypassing Odoo's closing validation
    window.location.href = "/odoo/point-of-sale";
  },
  async onSapphireAddOrder() {
    const pos = this.pos;
    if (typeof pos.add_new_order === "function") {
      pos.add_new_order();
    } else if (typeof pos.createNewOrder === "function") {
      await pos.createNewOrder();
    } else if (typeof pos.addNewOrder === "function") {
      await pos.addNewOrder();
    } else {
      // Odoo 17 fallback: create order via model
      const OrderModel = pos.models?.["pos.order"];
      if (OrderModel && typeof OrderModel.create === "function") {
        const newOrder = await OrderModel.create({});
        pos.selectedOrderUuid = newOrder?.uuid;
      } else {
        console.warn("[Sapphire] Cannot create a new order: no suitable method found on pos.");
      }
    }
  },
  sppLineUom(line) {
    try {
      if (!line) return "";

      // 1. Identify UoM data (Odoo 17 uses getUnit() and product_id)
      let uom = (typeof line.getUnit === 'function' ? line.getUnit() : null) ||
                line.uom_id ||
                line.product_uom_id ||
                line.product_id?.uom_id ||
                line.product?.uom_id;

      if (!uom && line.product_id?.product_tmpl_id) {
          uom = line.product_id.product_tmpl_id.uom_id;
      }

      if (!uom) return "";

      // 2. Extract Display Name
      // Record/Object
      if (typeof uom === "object" && !Array.isArray(uom)) {
          const name = uom.name || uom.display_name || uom.uom_name || "";
          if (name) return name;
      }

      // Tuple [id, name]
      if (Array.isArray(uom) && uom.length > 1) {
          return uom[1] || "";
      }

      // ID (Number or String-ID)
      const uomId = (typeof uom === "number" || (typeof uom === "string" && !isNaN(uom))) ? parseInt(uom) : null;
      if (uomId) {
          const pos = this.pos || this.env?.pos;
          const uomCollections = [
              pos?.models?.["uom.uom"],
              pos?.units_by_id,
              pos?.units,
              pos?.data?.["uom.uom"]
          ];

          for (const coll of uomCollections) {
              if (!coll) continue;
              if (Array.isArray(coll)) {
                  const r = coll.find(m => m.id === uomId);
                  if (r) return r.name || r.display_name || "";
              } else if (typeof coll === 'object') {
                  if (coll[uomId]) return coll[uomId].name || coll[uomId].display_name || "";
                  const r = Object.values(coll).find(v => v.id === uomId);
                  if (r) return r.name || r.display_name || "";
              }
          }
      }

      // Direct String
      if (typeof uom === "string") return uom;

      return "...";
    } catch (e) {
      console.warn("[Sapphire] Error in sppLineUom:", e);
      return "Err";
    }
  },

  sppLineUomId(line) {
    if (!line) return null;
    // Check uiState first so the selection "sticks" even if qty is represented in base unit
    if (line.uiState?.selected_uom_id) return line.uiState.selected_uom_id;

    let uom = (typeof line.getUnit === 'function' ? line.getUnit() : null) ||
              line.uom_id || line.product_uom_id || line.product_id?.uom_id;
    if (uom && typeof uom === 'object' && !Array.isArray(uom)) return uom.id;
    if (Array.isArray(uom)) return uom[0];
    const id = parseInt(uom);
    return isNaN(id) ? uom : id;
  },

  sppGetLineUoms(line) {
    try {
      if (!line || !this.pos) return [];
      const product = line.product_id || line.product;
      if (!product) return [];

      const res = [];
      const baseUom = (typeof line.getUnit === 'function' ? line.getUnit() : null) || product.uom_id;
      if (baseUom) {
          res.push({
              id: baseUom.id || baseUom[0],
              name: baseUom.name || baseUom[1] || "Base"
          });
      }

      // 1. Check uom_ids (the custom M2M field for additional units/packagings)
      if (product.uom_ids && Array.isArray(product.uom_ids)) {
          for (const uomId of product.uom_ids) {
              const uom = this.pos.models["uom.uom"]?.get(uomId);
              if (uom && !res.find(x => x.id === uom.id)) {
                  res.push({
                      id: uom.id,
                      name: uom.name || uom.display_name
                  });
              }
          }
      }

      // 2. Check product.uom bridge model (used for scanners usually)
      const packings = this.pos.models["product.uom"]?.filter(pu => {
          const pid = pu.product_id?.id ?? pu.product_id;
          return pid === product.id;
      }) || [];

      for (const p of packings) {
          const u = p.uom_id;
          if (u && !res.find(x => x.id === u.id)) {
              res.push({
                  id: u.id,
                  name: u.name || u.display_name || "Pack"
              });
          }
      }
      return res;
    } catch(e) {
      console.warn("[Sapphire] Error in sppGetLineUoms:", e);
      return [];
    }
  },

  sppOnUomChange(line, ev) {
    const order = this.sppOrder();
    if (!order || !line) return;
    const uomId = parseInt(ev.target.value);
    const uom = this.pos.models["uom.uom"]?.get(uomId);
    if (uom) {
        // Store in uiState
        if (!line.uiState) line.uiState = {};
        line.uiState.selected_uom_id = uomId;

        const product = line.product_id || line.product;
        const baseUom = product?.uom_id;

        let qty = 1;
        if (baseUom && uom) {
            // Formula: base_factor / target_factor
            const bFactor = baseUom.factor || 1;
            const tFactor = uom.factor || 1;
            qty = bFactor / tFactor;
        }

        if (typeof line.set_quantity === "function") line.set_quantity(qty);
        else if (typeof line.setQuantity === "function") line.setQuantity(qty);
        else line.qty = qty;

        order.trigger?.("change", order);
        this.render?.();
    }
  },
});
