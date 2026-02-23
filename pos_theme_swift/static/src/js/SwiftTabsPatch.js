/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { ProductScreen } from "@point_of_sale/app/screens/product_screen/product_screen";

const _keyByOrder = new WeakMap();
let _seq = 0;

function stableKey(order) {
  if (!order) return `null_${++_seq}`;
  if (!_keyByOrder.has(order)) {
    _keyByOrder.set(order, `ord_${++_seq}`);
  }
  return _keyByOrder.get(order);
}

patch(ProductScreen.prototype, {
  getOrderTabs() {
    const orders = (this.pos.getOpenOrders?.() || [])
      .filter((o) => o && !o.table_id);

    return orders.map((order, idx) => ({
      order,
      key: stableKey(order),
      label: `Hóa đơn ${idx + 1}`,
    }));
  },
});
