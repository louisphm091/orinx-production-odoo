/** @odoo-module **/

import { registry } from "@web/core/registry";
import { Component, onMounted, useState } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";
import { _t } from "@web/core/l10n/translation";

export class SwiftAttendanceManagement extends Component {
    static template = "pos_theme_swift.SwiftAttendanceManagement";

    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");

        this.state = useState({
            loading: true,
            approving: false,
            keyword: "",
            weekOffset: 0,
            weekLabel: "",
            weekStart: "",
            weekEnd: "",
            rows: [],
            showDetail: false,
            detail: null,
            detailLoading: false,
        });

        this._searchTimer = null;
        this.loadOverview = this.loadOverview.bind(this);
        this.onSearchInput = this.onSearchInput.bind(this);
        this.prevWeek = this.prevWeek.bind(this);
        this.nextWeek = this.nextWeek.bind(this);
        this.openDetail = this.openDetail.bind(this);
        this.closeDetail = this.closeDetail.bind(this);
        this.approveAttendance = this.approveAttendance.bind(this);

        onMounted(async () => {
            await this.loadOverview();
        });
    }

    formatHours(h) {
        return `${Number(h || 0).toLocaleString("vi-VN")} giờ`;
    }

    formatDays(d) {
        return `${Number(d || 0).toLocaleString("vi-VN")} ngày`;
    }

    async loadOverview() {
        this.state.loading = true;
        try {
            const data = await this.orm.call(
                "pos.dashboard.swift",
                "get_attendance_overview",
                [this.state.weekOffset, this.state.keyword || ""]
            );
            this.state.weekLabel = data.weekLabel || "";
            this.state.weekStart = data.weekStart || "";
            this.state.weekEnd = data.weekEnd || "";
            this.state.rows = data.rows || [];
        } catch (e) {
            console.error("loadOverview failed", e);
            this.notification.add(_t("Cannot load attendance data"), { type: "danger" });
        } finally {
            this.state.loading = false;
        }
    }

    onSearchInput(ev) {
        this.state.keyword = ev.target.value;
        clearTimeout(this._searchTimer);
        this._searchTimer = setTimeout(() => this.loadOverview(), 250);
    }

    async prevWeek() {
        this.state.weekOffset -= 1;
        await this.loadOverview();
    }

    async nextWeek() {
        this.state.weekOffset += 1;
        await this.loadOverview();
    }

    async approveAttendance() {
        if (!this.state.weekStart || !this.state.weekEnd) {
            return;
        }
        this.state.approving = true;
        try {
            const res = await this.orm.call(
                "pos.dashboard.swift",
                "action_approve_attendance",
                [this.state.weekStart, this.state.weekEnd, false]
            );
            if (!res || !res.ok) {
                this.notification.add(_t("Attendance approval failed"), { type: "danger" });
                return;
            }
            if (!res.count && res.already_count) {
                this.notification.add(_t("Attendance was already approved") + `: ${res.already_count}`, { type: "info" });
            } else if (!res.count) {
                this.notification.add(_t("No attendance records to approve"), { type: "info" });
            } else {
                this.notification.add(_t("Attendance approved: %s record(s)") + ` ${res.count}`, { type: "success" });
            }
            await this.loadOverview();
        } catch (e) {
            console.error("approveAttendance failed", e);
            this.notification.add(_t("Attendance approval failed"), { type: "danger" });
        } finally {
            this.state.approving = false;
        }
    }

    async openDetail(row) {
        this.state.showDetail = true;
        this.state.detailLoading = true;
        this.state.detail = null;
        try {
            const data = await this.orm.call(
                "pos.dashboard.swift",
                "get_attendance_employee_detail",
                [row.userId, this.state.weekStart, this.state.weekEnd]
            );
            if (!data || !data.ok) {
                this.notification.add((data && data.message) || _t("Cannot load employee attendance detail"), { type: "warning" });
                this.state.showDetail = false;
                return;
            }
            this.state.detail = data;
        } catch (e) {
            console.error("openDetail failed", e);
            this.notification.add(_t("Cannot load employee attendance detail"), { type: "danger" });
            this.state.showDetail = false;
        } finally {
            this.state.detailLoading = false;
        }
    }

    closeDetail() {
        this.state.showDetail = false;
        this.state.detail = null;
    }
}

registry.category("actions").add("pos_theme_swift.swift_pos_attendance_management", SwiftAttendanceManagement);
