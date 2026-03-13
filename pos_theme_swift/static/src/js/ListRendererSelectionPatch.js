/** @odoo-module **/

import { ListRenderer } from "@web/views/list/list_renderer";
import { patch } from "@web/core/utils/patch";

patch(ListRenderer.prototype, {
    /**
     * Toggles selection for all records in a group.
     * @param {Object} group
     */
    onGroupSelectorClick(group) {
        const records = [];
        const collectRecords = (g) => {
            if (g.list) {
                for (const record of g.list.records) {
                    records.push(record);
                }
            }
            if (g.groups) {
                for (const childGroup of g.groups) {
                    collectRecords(childGroup);
                }
            }
        };
        collectRecords(group);

        if (records.length === 0) return;

        const allSelected = records.every(r => r.selected);
        const shouldSelect = !allSelected;

        for (const record of records) {
            if (record.selected !== shouldSelect) {
                record.toggleSelection();
            }
        }
    },

    /**
     * Checks if all visible/loaded records in a group are selected.
     * @param {Object} group
     * @returns {boolean}
     */
    isGroupSelected(group) {
        const records = [];
        const collectRecords = (g) => {
            if (g.list) {
                for (const record of g.list.records) {
                    records.push(record);
                }
            }
            if (g.groups) {
                for (const childGroup of g.groups) {
                    collectRecords(childGroup);
                }
            }
        };
        collectRecords(group);
        if (records.length === 0) return false;
        return records.every(r => r.selected);
    }
});
