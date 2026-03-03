/** @odoo-module **/

import { registry } from "@web/core/registry";
import { Component, useState, onMounted, onWillUnmount } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";

export class SwiftShiftManagement extends Component {
    static template = "pos_theme_swift.SwiftShiftManagement";

    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");

        this.state = useState({
            status: 'idle', // 'idle', 'active'
            checkInTime: null,
            elapsedTime: '00:00:00',
            recentShifts: [],
            note: '',
            loading: true,
            userName: "đang tải...",
            branchName: "đang tải...",
            stats: { today: 0, week: 0 },
        });

        this.timer = null;

        onMounted(async () => {
            await this.loadInitData();
            await this.fetchShifts();
        });

        onWillUnmount(() => {
            this.stopTimer();
        });
    }

    async loadInitData() {
        try {
            const data = await this.orm.call("pos.dashboard.swift", "get_shift_init_data", []);
            this.state.userName = data.user_name || "Nhân viên";
            this.state.branchName = data.branch_name || "Chi nhánh";
            this.state.stats = data.stats || { today: 0, week: 0 };

            const res = data.status;
            if (res && res.state === 'active') {
                this.state.status = 'active';
                this.state.checkInTime = new Date(res.check_in + 'Z');
                this.startTimer();
            }
        } catch (e) {
            console.error("Failed to load init data", e);
        } finally {
            this.state.loading = false;
        }
    }

    async loadStatus() {
        try {
            const res = await this.orm.call("pos.dashboard.swift", "get_shift_status", []);
            if (res && res.state === 'active') {
                this.state.status = 'active';
                this.state.checkInTime = new Date(res.check_in + 'Z');
                this.startTimer();
            }
        } catch (e) {
            console.error("Failed to load shift status", e);
        } finally {
            this.state.loading = false;
        }
    }

    async fetchShifts() {
        try {
            const res = await this.orm.call("pos.dashboard.swift", "get_recent_shifts", []);
            this.state.recentShifts = res || [];
        } catch (e) {
            console.error("Failed to fetch recent shifts", e);
        }
    }

    formatDateTime(dtStr) {
        if (!dtStr) return "";
        let d;
        if (typeof dtStr === 'string') {
            d = new Date(dtStr + 'Z');
        } else {
            d = dtStr;
        }
        const pad = (v) => String(v).padStart(2, "0");
        return `${pad(d.getDate())}/${pad(d.getMonth() + 1)} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
    }

    formatDuration(hours) {
        if (!hours) return "0h";
        const totalMinutes = Math.round(hours * 60);
        const h = Math.floor(totalMinutes / 60);
        const m = totalMinutes % 60;
        return h > 0 ? `${h}h ${m}m` : `${m}m`;
    }

    startTimer() {
        this.stopTimer();
        this.timer = setInterval(() => {
            if (!this.state.checkInTime) return;
            const now = new Date();
            const diff = now - this.state.checkInTime;
            const hours = Math.floor(diff / 3600000);
            const minutes = Math.floor((diff % 3600000) / 60000);
            const seconds = Math.floor((diff % 60000) / 1000);
            this.state.elapsedTime =
                `${String(hours).padStart(2, '0')}:${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}`;
        }, 1000);
    }

    stopTimer() {
        if (this.timer) {
            clearInterval(this.timer);
            this.timer = null;
        }
    }

    async toggleShift() {
        try {
            const res = await this.orm.call("pos.dashboard.swift", "action_shift_toggle", [], {
                note: this.state.note
            });
            if (res.state === 'active') {
                this.state.status = 'active';
                this.state.checkInTime = new Date(res.check_in + 'Z');
                this.startTimer();
                this.notification.add("Đã bắt đầu ca làm việc", { type: "success" });
            } else {
                this.state.status = 'idle';
                this.state.checkInTime = null;
                this.state.elapsedTime = '00:00:00';
                this.state.note = '';
                this.stopTimer();
                this.notification.add("Đã kết thúc ca làm việc", { type: "success" });
            }
            await this.fetchShifts();
            await this.updateStats();
        } catch (e) {
            console.error("Shift toggle failed", e);
            this.notification.add("Lỗi khi thực hiện thao tác", { type: "danger" });
        }
    }

    async updateStats() {
        try {
            const stats = await this.orm.call("pos.dashboard.swift", "get_shift_stats", []);
            this.state.stats = stats || { today: 0, week: 0 };
        } catch (e) {
            console.error("Failed to update stats", e);
        }
    }
}

registry.category("actions").add("pos_theme_swift.swift_pos_shift_management", SwiftShiftManagement);
