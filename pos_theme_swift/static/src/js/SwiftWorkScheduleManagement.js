/** @odoo-module **/

import { registry } from "@web/core/registry";
import { Component, onMounted, useState } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";
import { _t } from "@web/core/l10n/translation";

export class SwiftWorkScheduleManagement extends Component {
    static template = "pos_theme_swift.SwiftWorkScheduleManagement";

    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");

        this.state = useState({
            loading: true,
            keyword: "",
            weekOffset: 0,
            weekLabel: "",
            weekStart: "",
            weekEnd: "",
            days: [],
            rows: [],
            templates: [],
            showScheduleModal: false,
            scheduleTarget: null,
            selectedTemplateIds: [],
            applyWeekly: true,
            selectedWeekdays: [1],
            copyToOthers: false,
            copyEmployeeKeyword: "",
            selectedCopyEmployeeIds: [],
            showShiftModal: false,
            shiftForm: {
                name: "",
                start_hour: "07:00",
                end_hour: "11:00",
                checkin_start_hour: "04:00",
                checkin_end_hour: "14:00",
                branch_name: "Chi nhánh trung tâm",
                color: "blue",
            },
        });

        this._searchTimer = null;

        this.loadData = this.loadData.bind(this);
        this.onSearchInput = this.onSearchInput.bind(this);
        this.prevWeek = this.prevWeek.bind(this);
        this.nextWeek = this.nextWeek.bind(this);
        this.openScheduleModal = this.openScheduleModal.bind(this);
        this.closeScheduleModal = this.closeScheduleModal.bind(this);
        this.toggleTemplate = this.toggleTemplate.bind(this);
        this.toggleWeekday = this.toggleWeekday.bind(this);
        this.toggleCopyEmployee = this.toggleCopyEmployee.bind(this);
        this.saveSchedule = this.saveSchedule.bind(this);
        this.openShiftModal = this.openShiftModal.bind(this);
        this.closeShiftModal = this.closeShiftModal.bind(this);
        this.saveShiftTemplate = this.saveShiftTemplate.bind(this);

        onMounted(async () => {
            await this.loadData();
        });
    }

    formatMoney(v) {
        return Number(v || 0).toLocaleString("vi-VN");
    }

    formatHourRange(s) {
        const pad = (n) => String(n).padStart(2, "0");
        const h = Math.floor(Number(s || 0));
        const m = Math.round((Number(s || 0) - h) * 60);
        return `${pad(h)}:${pad(m)}`;
    }

    _toHourFloat(hhmm) {
        const [h, m] = String(hhmm || "0:0").split(":").map((x) => parseInt(x || "0", 10));
        return (h || 0) + ((m || 0) / 60.0);
    }

    getWeekdayButtons() {
        return [
            { idx: 0, label: "Thứ 2" },
            { idx: 1, label: "Thứ 3" },
            { idx: 2, label: "Thứ 4" },
            { idx: 3, label: "Thứ 5" },
            { idx: 4, label: "Thứ 6" },
            { idx: 5, label: "Thứ 7" },
            { idx: 6, label: "Chủ nhật" },
        ];
    }

    getFilteredCopyEmployees() {
        const kw = (this.state.copyEmployeeKeyword || "").trim().toLowerCase();
        return this.state.rows.filter((r) => {
            if (!this.state.scheduleTarget || r.userId === this.state.scheduleTarget.userId) {
                return false;
            }
            if (!kw) {
                return true;
            }
            return (
                (r.employeeName || "").toLowerCase().includes(kw)
                || (r.employeeCode || "").toLowerCase().includes(kw)
            );
        });
    }

    async loadData() {
        this.state.loading = true;
        try {
            const data = await this.orm.call(
                "pos.dashboard.swift",
                "get_work_schedule_overview",
                [this.state.weekOffset, this.state.keyword || ""]
            );
            this.state.weekLabel = data.weekLabel || "";
            this.state.weekStart = data.weekStart || "";
            this.state.weekEnd = data.weekEnd || "";
            this.state.days = data.days || [];
            this.state.rows = data.rows || [];
            this.state.templates = data.templates || [];
        } catch (e) {
            console.error("loadData work schedule failed", e);
            this.notification.add(_t("Cannot load work schedule data"), { type: "danger" });
        } finally {
            this.state.loading = false;
        }
    }

    onSearchInput(ev) {
        this.state.keyword = ev.target.value;
        clearTimeout(this._searchTimer);
        this._searchTimer = setTimeout(() => this.loadData(), 250);
    }

    async prevWeek() {
        this.state.weekOffset -= 1;
        await this.loadData();
    }

    async nextWeek() {
        this.state.weekOffset += 1;
        await this.loadData();
    }

    async goCurrentWeek() {
        this.state.weekOffset = 0;
        await this.loadData();
    }

    openScheduleModal(row, day) {
        this.state.scheduleTarget = {
            userId: row.userId,
            employeeName: row.employeeName,
            employeeCode: row.employeeCode,
            date: day.date,
            weekdayIndex: day.weekdayIndex,
        };
        this.state.showScheduleModal = true;
        this.state.selectedTemplateIds = [];
        this.state.applyWeekly = true;
        this.state.selectedWeekdays = [day.weekdayIndex];
        this.state.copyToOthers = false;
        this.state.copyEmployeeKeyword = "";
        this.state.selectedCopyEmployeeIds = [];
    }

    closeScheduleModal() {
        this.state.showScheduleModal = false;
        this.state.scheduleTarget = null;
    }

    toggleTemplate(id) {
        const x = this.state.selectedTemplateIds;
        if (x.includes(id)) {
            this.state.selectedTemplateIds = x.filter((i) => i !== id);
        } else {
            this.state.selectedTemplateIds = [...x, id];
        }
    }

    toggleWeekday(idx) {
        const x = this.state.selectedWeekdays;
        if (x.includes(idx)) {
            this.state.selectedWeekdays = x.filter((i) => i !== idx);
        } else {
            this.state.selectedWeekdays = [...x, idx];
        }
    }

    toggleCopyEmployee(id) {
        const x = this.state.selectedCopyEmployeeIds;
        if (x.includes(id)) {
            this.state.selectedCopyEmployeeIds = x.filter((i) => i !== id);
        } else {
            this.state.selectedCopyEmployeeIds = [...x, id];
        }
    }

    async saveSchedule() {
        if (!this.state.scheduleTarget) {
            return;
        }
        if (!this.state.selectedTemplateIds.length) {
            this.notification.add(_t("Please select at least one shift"), { type: "warning" });
            return;
        }
        try {
            const copyIds = this.state.copyToOthers ? this.state.selectedCopyEmployeeIds : [];
            await this.orm.call(
                "pos.dashboard.swift",
                "save_work_schedule",
                [
                    this.state.scheduleTarget.userId,
                    this.state.scheduleTarget.date,
                    this.state.selectedTemplateIds,
                    this.state.applyWeekly,
                    this.state.selectedWeekdays,
                    copyIds,
                ]
            );
            this.notification.add(_t("Work schedule saved"), { type: "success" });
            this.closeScheduleModal();
            await this.loadData();
        } catch (e) {
            console.error("saveSchedule failed", e);
            this.notification.add(_t("Cannot save work schedule"), { type: "danger" });
        }
    }

    openShiftModal() {
        this.state.showShiftModal = true;
    }

    closeShiftModal() {
        this.state.showShiftModal = false;
    }

    async saveShiftTemplate() {
        if (!this.state.shiftForm.name) {
            this.notification.add(_t("Shift name is required"), { type: "warning" });
            return;
        }
        try {
            await this.orm.call("pos.dashboard.swift", "create_work_shift_template", [{
                name: this.state.shiftForm.name,
                start_hour: this._toHourFloat(this.state.shiftForm.start_hour),
                end_hour: this._toHourFloat(this.state.shiftForm.end_hour),
                checkin_start_hour: this._toHourFloat(this.state.shiftForm.checkin_start_hour),
                checkin_end_hour: this._toHourFloat(this.state.shiftForm.checkin_end_hour),
                branch_name: this.state.shiftForm.branch_name,
                color: this.state.shiftForm.color,
            }]);
            this.notification.add(_t("Shift created"), { type: "success" });
            this.state.showShiftModal = false;
            await this.loadData();
        } catch (e) {
            console.error("saveShiftTemplate failed", e);
            this.notification.add(_t("Cannot create shift"), { type: "danger" });
        }
    }
}

registry.category("actions").add("pos_theme_swift.swift_pos_work_schedule_management", SwiftWorkScheduleManagement);
