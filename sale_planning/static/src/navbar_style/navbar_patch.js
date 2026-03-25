/** @odoo-module **/

import { NavBar } from "@web/webclient/navbar/navbar";
import { patch } from "@web/core/utils/patch";

patch(NavBar.prototype, {
    /**
     * Get the icon URL for the currently active application.
     * Icons are usually defined in the menu's webIcon field.
     */
    get currentAppIcon() {
        if (this.currentApp && this.currentApp.webIcon) {
            const parts = this.currentApp.webIcon.split(',');
            if (parts.length === 2) {
                return `/${parts[0]}/${parts[1]}`;
            }
        }
        // Fallback for icons that might be stored directly as data
        if (this.currentApp && this.currentApp.webIconData) {
            return this.currentApp.webIconData;
        }
        return null;
    }
});
