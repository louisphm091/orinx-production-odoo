/** @odoo-module **/

import { Component, useState } from "@odoo/owl";
import { Dialog } from "@web/core/dialog/dialog";
import { _t } from "@web/core/l10n/translation";
import { useService } from "@web/core/utils/hooks";

const SWIFT_RETURN_URL_KEY = "pos_theme_swift.return_url";

const SWIFT_VERIFY_PIN_TRANSLATION_TERMS = [
    _t("User login successfully"),
    _t("Quay lại"),
    _t("Vui lòng nhập mã PIN"),
    _t("Mã PIN không hợp lệ"),
    _t("Lỗi kết nối"),
    _t("Nhân viên này thuộc chi nhánh '%s' và không thể mở POS '%s'."),
    _t("Chưa gán"),
    _t("Không xác định"),
    _t("Nhập mã PIN của bạn"),
];

void SWIFT_VERIFY_PIN_TRANSLATION_TERMS;

class CustomDialog extends Dialog {
    onEscape() {}
}

export class SwiftVerifyPinPopup extends Component {
    static template = "pos_theme_swift.SwiftVerifyPinPopup";
    static components = { Dialog: CustomDialog };
    static props = {
        title: { type: String, optional: true },
        branchId: { type: Number, optional: true },
        branchName: { type: String, optional: true },
        onBack: { type: Function, optional: true },
        getPayload: { type: Function, optional: true },
        close: Function,
    };

    setup() {
        this._t = _t;
        this.orm = useService("orm");
        this.pos = useService("pos");
        this.notification = useService("notification");
        this.state = useState({
            pin: "",
            error: "",
            loading: false,
        });
    }

    appendChar(char) {
        this.state.error = "";
        this.state.pin += char;
    }

    deleteChar() {
        this.state.error = "";
        this.state.pin = this.state.pin.slice(0, -1);
    }

    goBack() {
        this.props.close();
        const returnUrl = sessionStorage.getItem(SWIFT_RETURN_URL_KEY);
        if (returnUrl) {
            sessionStorage.removeItem(SWIFT_RETURN_URL_KEY);
            window.location.href = returnUrl;
            return;
        }
        window.history.back();
    }

    formatBranchMismatchMessage(result) {
        const template = _t("Nhân viên này thuộc chi nhánh '%s' và không thể mở POS '%s'.");
        return template
            .replace("%s", result.employee_branch || _t("Chưa gán"))
            .replace("%s", result.session_branch || _t("Không xác định"));
    }

    async confirm() {
        if (!this.state.pin) {
            this.state.error = _t("Vui lòng nhập mã PIN");
            return;
        }
        this.state.loading = true;
        this.state.error = "";
        try {
            const branchId = this.props.branchId || (this.pos.config ? this.pos.config.id : false);
            const result = await this.orm.call("pos.dashboard.swift", "verify_employee_pin", [this.state.pin, branchId]);
            if (result && result.ok) {
                const cashierUser =
                    this.pos.models?.["res.users"]?.get(result.user_id) || {
                        id: result.user_id,
                        name: result.user_name || "",
                        role: "cashier",
                        raw: { role: "cashier" },
                };
                this.pos.setSwiftEmployee(cashierUser, result.avatarUrl || "", Boolean(result.is_admin));
                sessionStorage.removeItem(SWIFT_RETURN_URL_KEY);
                this.notification.add(_t("User login successfully"), { type: "success" });
                this.props.getPayload?.(result);
                this.props.close();
            } else {
                if (result && result.code === "branch_mismatch") {
                    this.state.error = this.formatBranchMismatchMessage(result);
                } else {
                    this.state.error = result ? result.message : _t("Mã PIN không hợp lệ");
                }
                this.state.pin = "";
            }
        } catch (error) {
            console.error(error);
            this.state.error = _t("Lỗi kết nối");
        } finally {
            this.state.loading = false;
        }
    }
}
