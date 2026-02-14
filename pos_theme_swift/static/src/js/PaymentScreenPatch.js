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

/**
 * Extra helpers for your navbar + left menu list
 */
patch(PaymentScreen.prototype, {
  getOrderTabs() {
    const orders = this.pos.getOpenOrders().filter((o) => !o.table_id);
    return orders.map((order, idx) => ({
      order,
      key: order.cid || order.uid || order.name || idx,
      label: `Hóa đơn ${idx + 1}`,
    }));
  },

  get orderCount() {
    return this.pos.getOpenOrders().filter((o) => !o.table_id).length;
  },

  onTicketButtonClick() {
    this.pos.showScreen("TicketScreen");
  },

  onCashMoveButtonClick() {
    this.pos.showPopup("CashMovePopup");
  },

  getPaymentLines() {
    const order = this.pos.getOrder();
    const lines = order?.get_orderlines?.() || [];

    return lines.map((line) => {
      const product = line.product;
      const qty = line.get_quantity?.() ?? line.quantity ?? 0;

      const total =
        this.env.utils?.formatCurrency?.(
          line.get_display_price?.() ?? line.get_price_with_tax?.() ?? 0
        ) || `${line.get_display_price?.() ?? ""}`;

      const unitPrice =
        this.env.utils?.formatCurrency?.(line.get_unit_price?.() ?? 0) || "";

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
