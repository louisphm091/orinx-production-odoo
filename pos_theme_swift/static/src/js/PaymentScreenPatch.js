/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { PaymentScreen } from "@point_of_sale/app/screens/payment_screen/payment_screen";
import { CashierName } from "@point_of_sale/app/components/navbar/cashier_name/cashier_name";

/**
 * Register CashierName for PaymentScreen template
 */
patch(PaymentScreen, {
  components: {
    ...(PaymentScreen.components || {}),
    CashierName,
  },
});

patch(PaymentScreen.prototype, {
  // =========================================================
  // 0) Order / Lines safe getters
  // =========================================================
  sppOrder() {
    return this.pos?.getOrder?.() || this.pos?.get_order?.() || null;
  },

  sppOrderlines(order) {
    return (
      order?.get_orderlines?.() ||
      order?.getOrderlines?.() ||
      order?.lines ||
      []
    );
  },

  sppLineKey(line, i) {
    // tránh duplicate key "/" hoặc object toString
    return (
      line?.uuid ||
      line?.uid ||
      line?.id ||
      line?.cid ||
      (line?.product?.id ? `p-${line.product.id}-${i}` : `l-${i}`)
    );
  },

  sppIndexOf(line) {
    const order = this.sppOrder();
    const lines = this.sppOrderlines(order);
    const idx = lines.indexOf(line);
    return idx >= 0 ? idx : 0;
  },

  // =========================================================
  // 1) Line fields helpers
  // =========================================================
  sppLineQty(line) {
    const q =
      (line?.get_quantity && line.get_quantity()) ??
      line?.quantity ??
      line?.qty ??
      0;
    const n = Number(q);
    return Number.isFinite(n) ? n : 0;
  },

  sppLineUnitPrice(line) {
    const u =
      (line?.get_unit_price && line.get_unit_price()) ??
      line?.price_unit ??
      line?.unit_price ??
      0;
    const n = Number(u);
    return Number.isFinite(n) ? n : 0;
  },

  sppLineTotal(line) {
    // ưu tiên subtotal/tax theo chuẩn
    const v =
      (line?.get_display_price && line.get_display_price()) ??
      (line?.get_price_with_tax && line.get_price_with_tax()) ??
      line?.price_subtotal_incl ??
      line?.price_subtotal ??
      this.sppLineQty(line) * this.sppLineUnitPrice(line);

    const n = Number(v);
    return Number.isFinite(n) ? n : 0;
  },

  sppLineName(line) {
    return (
      line?.full_product_name ||
      (line?.getFullProductName && line.getFullProductName()) ||
      (line?.get_full_product_name && line.get_full_product_name()) ||
      line?.product?.display_name ||
      line?.product?.name ||
      "Item"
    );
  },

  sppLineBarcode(line) {
    return line?.product?.barcode || line?.product?.default_code || "";
  },

  // =========================================================
  // 2) Actions: select / qty / remove / more
  // =========================================================
  onSppSelectLine(ev, line) {
    ev?.preventDefault?.();
    ev?.stopPropagation?.();
    ev?.stopImmediatePropagation?.();

    const order = this.sppOrder();
    if (!order || !line) return;

    if (typeof order.select_orderline === "function") {
      order.select_orderline(line);
    } else if (typeof order.set_selected_orderline === "function") {
      order.set_selected_orderline(line);
    }

    order.trigger?.("change", order);
    this.render?.();
  },

  onSppRemoveLine(ev, line) {
    ev?.preventDefault?.();
    ev?.stopPropagation?.();
    ev?.stopImmediatePropagation?.();

    const order = this.sppOrder();
    if (!order || !line) return;

    if (typeof order.remove_orderline === "function") {
      order.remove_orderline(line);
    } else if (typeof order.removeOrderline === "function") {
      order.removeOrderline(line);
    } else if (typeof line.delete === "function") {
      line.delete();
    } else {
      // fallback: set qty 0
      line.set_quantity?.(0);
    }

    order.trigger?.("change", order);
    this.render?.();
  },

  onSppIncLine(ev, line) {
    ev?.preventDefault?.();
    ev?.stopPropagation?.();
    ev?.stopImmediatePropagation?.();

    const order = this.sppOrder();
    if (!order || !line) return;

    const next = this.sppLineQty(line) + 1;
    if (typeof line.set_quantity === "function") line.set_quantity(next);
    else if (typeof line.setQuantity === "function") line.setQuantity(next);
    else line.qty = next;

    line.trigger?.("change", line);
    order.trigger?.("change", order);
    this.render?.();
  },

  onSppDecLine(ev, line) {
    ev?.preventDefault?.();
    ev?.stopPropagation?.();
    ev?.stopImmediatePropagation?.();

    const order = this.sppOrder();
    if (!order || !line) return;

    const cur = this.sppLineQty(line);
    const next = Math.max(cur - 1, 0);

    if (next <= 0) {
      this.onSppRemoveLine(null, line);
      return;
    }

    if (typeof line.set_quantity === "function") line.set_quantity(next);
    else if (typeof line.setQuantity === "function") line.setQuantity(next);
    else line.qty = next;

    line.trigger?.("change", line);
    order.trigger?.("change", order);
    this.render?.();
  },

  onSppOpenLineMore(ev, line) {
    ev?.preventDefault?.();
    ev?.stopPropagation?.();
    ev?.stopImmediatePropagation?.();
    console.log("[Sapphire] more line:", line);
  },

  // =========================================================
  // 3) Navbar: Tabs + Search (giữ pos.searchProductWord)
  // =========================================================
  getOrderTabs() {
    const orders = this.pos.getOpenOrders().filter((o) => !o.table_id);
    return orders.map((order, idx) => ({
      order,
      key: order.cid || order.uid || order.name || idx,
      label: `Hóa đơn ${idx + 1}`,
    }));
  },

  onSapphireSearchInput(ev) {
    const v = ev?.target?.value ?? "";
    this.pos.searchProductWord = v;
  },

  onSapphireSearchKeydown(ev) {
    // Enter => back ProductScreen để search
    if (ev?.key === "Enter") {
      ev.preventDefault();
      ev.stopPropagation();
      ev.stopImmediatePropagation?.();
      this.pos.showScreen("ProductScreen");
      return;
    }

    // F3 => focus search
    if (ev?.key === "F3") {
      ev.preventDefault();
      ev.stopPropagation();
      ev.stopImmediatePropagation?.();
      ev.target?.focus?.();
    }
  },

  // alias để tương thích XML cũ
  sppLineUnit(line) {
    return this.sppLineUnitPrice(line);
  },
  sppLineUnitPriceValue(line) {
    return this.sppLineUnitPrice(line);
  },

  sppIncQty(line) {
    const order = this.sppOrder();
    if (!order || !line) return;

    const qty = this.sppLineQty(line) + 1;

    if (typeof line.set_quantity === "function") {
      line.set_quantity(qty);
    } else if (typeof line.setQuantity === "function") {
      line.setQuantity(qty);
    } else {
      line.qty = qty;
    }

    order.trigger?.("change", order);
    this.render?.();
  },

    sppDecQty(line) {
    const order = this.sppOrder();
    if (!order || !line) return;

    const current = this.sppLineQty(line);

    // 🔥 Nếu còn 1 thì xoá luôn
    if (current <= 1) {
        this.sppRemoveLine(line);
        return;
    }

    const newQty = current - 1;

    if (typeof line.set_quantity === "function") {
        line.set_quantity(newQty);
    } else if (typeof line.setQuantity === "function") {
        line.setQuantity(newQty);
    } else {
        line.qty = newQty;
    }

    order.trigger?.("change", order);
    this.render?.();
    },

    sppRemoveLine(line) {
    const order = this.sppOrder();
    if (!order || !line) return;

    // Odoo classic
    if (order.remove_orderline) {
      order.remove_orderline(line);
    } else if (line.delete) {
      line.delete();
    } else if (line.set_quantity) {
      line.set_quantity(0);
    }

    order.trigger?.("change", order);
    this.render?.();
  },

  // =========================================================
  // 4) Optional: mapping list món (nếu bạn đang dùng chỗ khác)
  // =========================================================
  getPaymentLines() {
    const order = this.sppOrder();
    const lines = this.sppOrderlines(order);

    return (lines || []).map((line) => {
      const product = line.product;
      const qty = this.sppLineQty(line);

      const total =
        this.env.utils?.formatCurrency?.(this.sppLineTotal(line)) ||
        `${this.sppLineTotal(line)}`;

      const unitPrice =
        this.env.utils?.formatCurrency?.(this.sppLineUnitPrice(line)) || "";

      const imageUrl = product?.image_128
        ? `data:image/png;base64,${product.image_128}`
        : null;

      return {
        id: line.uid || line.id || `${product?.id}-${Math.random()}`,
        name: product?.display_name || product?.name || "Item",
        qty,
        unitPrice,
        total,
        imageUrl,
        _line: line,
      };
    });
  },
});
