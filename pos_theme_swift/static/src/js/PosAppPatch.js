/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { PosStore } from "@point_of_sale/app/services/pos_store";

patch(PosStore.prototype, {
    get defaultPage() {
        return {
            page: "PaymentScreen",
            params: {
                orderUuid: this.openOrder.uuid,
            },
        };
    },
    navigateToOrderScreen(order) {
        this.ticket_screen_mobile_pane = "left";
        this.navigate("PaymentScreen", {
            orderUuid: order.uuid,
        });
    }
});
