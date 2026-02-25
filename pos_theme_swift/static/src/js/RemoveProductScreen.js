/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { useService } from "@web/core/utils/hooks";
import { ProductScreen } from "@point_of_sale/app/screens/product_screen/product_screen";

patch(ProductScreen.prototype, {
  setup() {
    super.setup(...arguments);
    const pos = this.pos || this.env?.services?.pos;
    if (pos?.navigate) {
      pos.navigate("PaymentScreen");
    } else if (pos?.showScreen) {
      pos.showScreen("PaymentScreen");
    } else if (pos && "mainScreen" in pos) {
      pos.mainScreen = "PaymentScreen";
    }
  },
});
