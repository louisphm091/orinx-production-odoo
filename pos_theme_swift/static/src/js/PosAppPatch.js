/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { PosStore } from "@point_of_sale/app/services/pos_store";
import { Chrome } from "@point_of_sale/app/pos_app";
import { CashierName } from "@point_of_sale/app/components/navbar/cashier_name/cashier_name";
import { PosOrder } from "@point_of_sale/app/models/pos_order";
import { PosOrderline } from "@point_of_sale/app/models/pos_order_line";
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
        if (this.pos.config?.module_pos_hr) {
            const cashier = this.pos.getCashier();
            if (cashier?.id) {
                return `/web/image/hr.employee.public/${cashier.id}/avatar_128`;
            }
            return "";
        }
        const user_id = this.pos.getCashierUserId();
        const id = user_id ? user_id : -1;
        return `/web/image/res.users/${id}/avatar_128`;
    },
});

patch(PosStore.prototype, {
    swiftIsAdmin: false,
    setSwiftEmployee(user, avatarUrl = "", isAdmin = false) {
        if (this.config?.module_pos_hr) {
            if (!user) {
                return;
            }
            this.setCashier(user);
            this.swiftCashierAvatar = avatarUrl || `/web/image/hr.employee.public/${user.id}/avatar_128`;
            this.swift_cashier_id = user.user_id?.id || user.id;
            this.swift_cashier_name = user.name || "";
            this.swiftIsAdmin = Boolean(isAdmin || user._role === "manager");
            return;
        }
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

patch(PosOrderline.prototype, {
    getUnit() {
        return this.product_id?.uom_id || null;
    },
    getProduct() {
        return this.product_id || null;
    },
    getFullProductName() {
        return this.full_product_name || this.product_id?.display_name || "";
    },
});

patch(PosOrder.prototype, {
    _computeAllPrices(opts = {}) {
        const sourceLines = opts.lines || this.lines || [];
        const validLines = sourceLines.filter((line) => line?.product_id);

        if (validLines.length !== sourceLines.length) {
            console.warn("[Swift POS] Ignoring invalid order lines without product_id", {
                orderUuid: this.uuid,
                invalidCount: sourceLines.length - validLines.length,
            });
        }

        return super._computeAllPrices({
            ...opts,
            lines: validLines,
        });
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
                    title: "Nhập mã xác nhận để truy cập POS",
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
