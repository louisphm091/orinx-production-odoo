/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { PaymentScreen } from "@point_of_sale/app/screens/payment_screen/payment_screen";
import { PosOrder } from "@point_of_sale/app/models/pos_order";

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
    super.setup();
    try {
      const order = this.pos.getOrder();
      if (order && order.payment_ids) {
        const badLines = order.payment_ids.filter(
          (p) => !p.payment_method_id || !p.payment_method_id.id,
        );
        for (const bad of badLines) {
          console.warn("Removing corrupted payment line:", bad);
          bad.delete && bad.delete();
        }
      }
    } catch (e) {
      console.error("Error cleaning up payment lines:", e);
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
    if (typeof pos?.getOrder === "function") return pos.getOrder();
    if (typeof pos?.get_order === "function") return pos.get_order();

    const OrderModel = pos?.models?.["pos.order"];
    const uuid = pos?.selectedOrderUuid;
    if (OrderModel?.get && uuid) return OrderModel.get(uuid) || null;
    if (OrderModel?.getAll) return OrderModel.getAll()?.[0] || null;
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
    const amount_paid = pls.reduce(
      (s, pl) => s + (Number(pl.amount ?? pl.payment_amount ?? 0) || 0),
      0,
    );
    const discount_total = lines.reduce((s, l) => {
      const qty = Number(l.qty) || 0;
      const unit = Number(l.price_unit ?? l.priceUnit) || 0;
      const disc = Number(l.discount) || 0;
      return s + unit * qty * (disc / 100);
    }, 0);

    const other_charges = 0; // sau này nếu có logic thu khác thì thay ở đây

    const need_to_pay = Math.max(
      total_items - discount_total + other_charges,
      0,
    );

    // amount_paid vẫn như bạn đang tính
    const amount_due = Math.max(need_to_pay - amount_paid, 0);

    return {
      items_count,
      total_items,
      discount_total,
      other_charges,
      need_to_pay, // <<< ADD
      amount_due,
      amount_paid,
    };
  },

  async onSapphireQuickPay(ev, amount) {
    if (ev) {
      ev.preventDefault();
      ev.stopPropagation();
      ev.stopImmediatePropagation?.();
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

    const add = Number(amount) || 0;
    const cur = Number(line.amount ?? line.payment_amount ?? 0) || 0;
    const next = cur + add;

    // ưu tiên update của record store
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

  formatSapphireNumber(v) {
    try {
      return new Intl.NumberFormat("vi-VN").format(Number(v) || 0);
    } catch {
      return String(Number(v) || 0);
    }
  },

  sppIsToInvoice(order) {
    if (!order) return false;

    // Odoo thường có isToInvoice() hoặc is_to_invoice()
    if (typeof order.isToInvoice === "function") return !!order.isToInvoice();
    if (typeof order.is_to_invoice === "function")
      return !!order.is_to_invoice();

    // store field hay gặp
    if (typeof order.to_invoice === "boolean") return order.to_invoice;
    if (typeof order.toInvoice === "boolean") return order.toInvoice;

    // một số build để trong uiState
    if (order.uiState && typeof order.uiState.to_invoice === "boolean")
      return order.uiState.to_invoice;

    return false;
  },

  async onSapphireToggleInvoice(ev) {
    if (ev) {
      ev.preventDefault();
      ev.stopPropagation();
      ev.stopImmediatePropagation?.();
    }

    const order = this.sppOrder?.() || this.pos?.getOrder?.();
    if (!order) return;

    const next = !this.sppIsToInvoice(order);

    // Ưu tiên setter chuẩn
    if (typeof order.set_to_invoice === "function") {
      order.set_to_invoice(next);
    } else if (typeof order.setToInvoice === "function") {
      order.setToInvoice(next);
    } else if (typeof order.update === "function") {
      // store record
      order.update({ to_invoice: next });
    } else {
      // fallback trực tiếp
      order.to_invoice = next;
      if (order.uiState) order.uiState.to_invoice = next;
    }

    order.trigger?.("change", order);
    this.render?.();
  },

  // -------------------------------------------------
  // PAY button (THANH TOÁN)
  // -------------------------------------------------
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
});
