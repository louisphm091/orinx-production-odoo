/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { useService } from "@web/core/utils/hooks";
import { ProductScreen } from "@point_of_sale/app/screens/product_screen/product_screen";

/**
 * 1) Chặn mọi click / hotkey / flow nào gọi ProductScreen
 * => redirect qua PaymentScreen
 */
patch(ProductScreen.prototype, {
  setup() {
    super.setup(...arguments);
    // vừa mount ProductScreen là đá sang PaymentScreen luôn
    const pos = this.pos || this.env?.services?.pos;
    // một số build dùng navigate, một số build dùng showScreen
    if (pos?.navigate) {
      pos.navigate("PaymentScreen");
    } else if (pos?.showScreen) {
      pos.showScreen("PaymentScreen");
    } else if (pos && "mainScreen" in pos) {
      pos.mainScreen = "PaymentScreen";
    }
  },
});
