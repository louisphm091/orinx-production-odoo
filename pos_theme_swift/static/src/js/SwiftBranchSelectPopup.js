/** @odoo-module **/

import { Component, onWillStart, useState } from "@odoo/owl";
import { Dialog } from "@web/core/dialog/dialog";
import { _t } from "@web/core/l10n/translation";
import { useService } from "@web/core/utils/hooks";

const SWIFT_BRANCH_SELECT_TRANSLATION_TERMS = [
    _t("Select POS branch"),
    _t("Loading branches..."),
    _t("No POS branch available."),
    _t("Choose this branch"),
    _t("Current branch"),
    _t("Please select the branch you want to open."),
    _t("Branch"),
    _t("Back"),
];

void SWIFT_BRANCH_SELECT_TRANSLATION_TERMS;

class CustomDialog extends Dialog {
    onEscape() {}
}

export class SwiftBranchSelectPopup extends Component {
    static template = "pos_theme_swift.SwiftBranchSelectPopup";
    static components = { Dialog: CustomDialog };
    static props = {
        currentBranchId: { type: Number, optional: true },
        currentBranchName: { type: String, optional: true },
        onSelect: Function,
        close: Function,
    };

    setup() {
        this._t = _t;
        this.orm = useService("orm");
        this.state = useState({
            loading: true,
            branches: [],
            error: "",
        });

        onWillStart(async () => {
            await this.loadBranches();
        });
    }

    async loadBranches() {
        this.state.loading = true;
        this.state.error = "";
        try {
            const res = await this.orm.call("pos.dashboard.swift", "get_employee_branch_options", []);
            this.state.branches = res.rows || [];
        } catch (error) {
            console.error(error);
            this.state.error = this._t("No POS branch available.");
            this.state.branches = [];
        } finally {
            this.state.loading = false;
        }
    }

    selectBranch(branch) {
        this.props.onSelect?.(branch);
        this.props.close();
    }
}
