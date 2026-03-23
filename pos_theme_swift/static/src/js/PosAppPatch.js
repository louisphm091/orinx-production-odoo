/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { PosStore } from "@point_of_sale/app/services/pos_store";
import { Chrome } from "@point_of_sale/app/pos_app";
import { CashierName } from "@point_of_sale/app/components/navbar/cashier_name/cashier_name";
import { SwiftVerifyPinPopup } from "./SwiftVerifyPinPopup";
import { onMounted } from "@odoo/owl";

const SWIFT_RETURN_URL_KEY = "pos_theme_swift.return_url";

function buildSwiftCashierUser(user, fallbackName = "") {
    if (!user) {
        return false;
    }
    if (user.id && user.name) {
        return user;
    }
    const userId = Number(user.id || 0) || false;
    if (!userId) {
        return false;
    }
    const name = user.name || fallbackName || "";
    return {
        id: userId,
        name,
        role: user.role || "cashier",
        raw: user.raw || { role: user.role || "cashier" },
    };
}

patch(CashierName.prototype, {
    get avatar() {
        if (this.pos.swiftCashierAvatar) {
            return this.pos.swiftCashierAvatar;
        }
        const user_id = this.pos.getCashierUserId();
        const id = user_id ? user_id : -1;
        return `/web/image/res.users/${id}/avatar_128`;
    },
});

patch(PosStore.prototype, {
    swiftIsAdmin: false,
    setSwiftEmployee(user, avatarUrl = "", isAdmin = false) {
        const cashierUser = buildSwiftCashierUser(user);
        if (!cashierUser) {
            return;
        }
        this.user = cashierUser;
        this.setCashier(cashierUser);
        this.swiftCashierAvatar = avatarUrl || "";
        this.swift_cashier_id = cashierUser.id;
        this.swift_cashier_name = cashierUser.name;
        this.swiftIsAdmin = Boolean(isAdmin);
    },
});

patch(Chrome.prototype, {
    setup() {
        super.setup(...arguments);
        onMounted(() => {
            if (this.pos.dialog) {
                if (!sessionStorage.getItem(SWIFT_RETURN_URL_KEY) && document.referrer) {
                    try {
                        const referrerUrl = new URL(document.referrer);
                        if (referrerUrl.origin === window.location.origin && !referrerUrl.pathname.startsWith("/pos/ui")) {
                            sessionStorage.setItem(SWIFT_RETURN_URL_KEY, document.referrer);
                        }
                    } catch {
                        // Ignore invalid referrer URLs.
                    }
                }
                this.pos.dialog.add(SwiftVerifyPinPopup, {
                    title: "Nhập mã PIN để truy cập POS",
                    branchId: this.pos.config.id,
                    branchName: this.pos.config.display_name || this.pos.config.name || "",
                });
            }
        });
    }
});

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
