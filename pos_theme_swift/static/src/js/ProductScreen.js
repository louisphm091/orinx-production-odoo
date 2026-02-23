/** @odoo-module **/
import { ProductScreen } from "@point_of_sale/app/screens/product_screen/product_screen";
import { useService } from "@web/core/utils/hooks";
import { _t } from "@web/core/l10n/translation";
import { patch } from "@web/core/utils/patch";

import { ProxyStatus } from "@point_of_sale/app/components/navbar/proxy_status/proxy_status";
import { ClosePosPopup } from "@point_of_sale/app/components/popups/closing_popup/closing_popup";
import { SaleDetailsButton } from "@point_of_sale/app/components/navbar/sale_details_button/sale_details_button";
import { CashMovePopup } from "@point_of_sale/app/components/popups/cash_move_popup/cash_move_popup";
import { BackButton } from "@point_of_sale/app/screens/product_screen/action_pad/back_button/back_button";
import { CashierName } from "@point_of_sale/app/components/navbar/cashier_name/cashier_name";
import { CategorySelector } from "@point_of_sale/app/components/category_selector/category_selector";
import { OrderTabs } from "@point_of_sale/app/components/order_tabs/order_tabs";
import { user } from "@web/core/user";

ProductScreen.components = {
  ...ProductScreen.components,
  ProxyStatus,
  SaleDetailsButton,
  BackButton,
  CashierName,
  CategorySelector,
  OrderTabs,
};

patch(ProductScreen, {
  props: {
    ...(ProductScreen.props || {}),
    id: { type: String, optional: true },
  },
});

patch(ProductScreen.prototype, {
  setup() {
    super.setup(...arguments);
    this.hardwareProxy = useService("hardware_proxy");
    this.onCategorySelected = this.onCategorySelected.bind(this);
  },
onOpenSapphireReport(ev) {
  ev?.preventDefault?.();
  ev?.stopPropagation?.();
  ev?.stopImmediatePropagation?.();

  const pos = this.pos || this.env?.services?.pos;

  // ✅ KHÔNG truyền params (id/orderUuid/...)
  pos.navigate("SwiftReportScreen");
},

  getOrderTabs() {
    const orders = (this.pos.getOpenOrders?.() || []).filter(
      (o) => o && !o.table_id,
    );
    return orders.map((order, idx) => ({
      order,
      key: order.uuid || order.uid || order.cid || order.name || `o-${idx}`,
      label: `Hóa đơn ${idx + 1}`,
    }));
  },

  get orderCount() {
    const orders = this.pos.getOpenOrders?.() || this.pos.get_orders?.() || [];
    return orders.filter((o) => o && !o.table_id).length;
  },

  onCategorySelected({ categoryId }) {
    this.pos.setSelectedCategory(categoryId);
    this.render(true);
  },

  async closeSession() {
    const info = await this.pos.getClosePosInfo();
    this.dialog.add(ClosePosPopup, info);
  },

  onCashMoveButtonClick() {
    this.hardwareProxy.openCashbox(_t("Cash in / out"));
    this.dialog.add(CashMovePopup);
  },
});

patch(CashierName.prototype, {
  setup() {
    super.setup(...arguments);
    this.username = user.name;
    this.email = user.email;
  },
});
