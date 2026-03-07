/** @odoo-module **/

import { Component, useState, onMounted } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";
import { registry } from "@web/core/registry";
import { _t } from "@web/core/l10n/translation";

export class StockTransfer extends Component {
    static template = "pos_theme_swift.StockTransfer";

    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");

        this.state = useState({
            view: 'list', // 'list', 'form' (sender), 'receive' (receiver)
            loading: true,
            sidebarCollapsed: false,
            records: [],
            locations: [],
            filters: {
                loc_src: false,
                loc_dest: false,
                states: ['draft', 'shipped', 'done'],
                date_range: 'this_month',
                mismatch: 'all',
            },
            searchKeyword: "",

            // Shared Detail/Form state
            currentTransfer: null,
            productSearchResults: [],
            searchProductKeyword: "",
            showProductDropdown: false,

            // Receiver View specific
            receiveTab: 'all', // 'all', 'match', 'mismatch', 'unreceived'
        });

        onMounted(async () => {
            await this.loadLocations();
            await this.loadTransfers();
        });
    }

    // ─── data loading ─────────────────────────────────────────────

    async loadLocations() {
        try {
            this.state.locations = await this.orm.call("pos.dashboard.swift", "get_locations", []);
        } catch (e) {
            console.error("Failed to load locations", e);
        }
    }

    async loadTransfers() {
        this.state.loading = true;
        try {
            const filters = {
                loc_src: this.state.filters.loc_src,
                loc_dest: this.state.filters.loc_dest,
                states: this.state.filters.states,
                date_range: this.state.filters.date_range,
            };
            this.state.records = await this.orm.call("pos.dashboard.swift", "get_stock_transfers", [filters]);
        } catch (e) {
            console.error("Failed to load transfers", e);
            this.notification.add(_t("Error loading stock transfer data"), { type: "danger" });
        } finally {
            this.state.loading = false;
        }
    }

    async openTransfer(record) {
        this.state.loading = true;
        try {
            const detail = await this.orm.call("pos.dashboard.swift", "get_transfer_detail", [record.id]);
            if (detail) {
                this.state.currentTransfer = detail;

                // Logic to decide View: Form or Receive
                // For simplicity: if state is shipped/done AND user is "receiver" (mocked by checking loc_dest)
                // In real app, we check if the current user/branch is the destination
                // For this demo, let's assume if it's not 'draft', we show the Receive/Detail view
                if (detail.state !== 'draft') {
                    this.state.view = 'receive';
                } else {
                    this.state.view = 'form';
                }
            }
        } catch (e) {
            console.error("Failed to load detail", e);
        } finally {
            this.state.loading = false;
        }
    }

    // ─── Sender Form Handlers ─────────────────────────────────────

    async createNewTransfer() {
        this.state.currentTransfer = {
            id: false,
            loc_dest_id: false,
            note: "",
            lines: [],
            state: 'draft',
            date: new Date().toLocaleString('vi-VN'),
        };
        this.state.view = 'form';
    }

    async onProductSearch(ev) {
        const keyword = ev.target.value;
        this.state.searchProductKeyword = keyword;
        if (keyword.length < 1) {
            this.state.productSearchResults = [];
            this.state.showProductDropdown = false;
            return;
        }

        try {
            const results = await this.orm.call("pos.dashboard.swift", "get_inventory_products", [keyword]);
            this.state.productSearchResults = results;
            this.state.showProductDropdown = true;
        } catch (e) {
            console.error("Product search failed", e);
        }
    }

    async addProduct(product) {
        const existing = this.state.currentTransfer.lines.find(l => l.product_id === product.id);
        if (existing) {
            existing.qty += 1;
        } else {
            let qty_dest = 0;
            if (this.state.currentTransfer.loc_dest_id) {
                const stock = await this.orm.call("pos.dashboard.swift", "get_location_stock", [[product.id], this.state.currentTransfer.loc_dest_id]);
                qty_dest = stock[product.id] || 0;
            }

            this.state.currentTransfer.lines.push({
                product_id: product.id,
                product_code: product.barcode || product.id,
                product_name: product.name,
                uom: product.uom,
                qty_on_hand: product.qty_on_hand,
                qty_dest: qty_dest,
                qty: 1,
                received_qty: 0,
                price: product.price || 0,
            });
        }
        this.state.showProductDropdown = false;
        this.state.searchProductKeyword = "";
    }

    removeLine(idx) {
        this.state.currentTransfer.lines.splice(idx, 1);
    }

    async saveTransfer(isDone = false) {
        if (!this.state.currentTransfer.loc_dest_id) {
            this.notification.add(_t("Please select receiving branch"), { type: "warning" });
            return;
        }
        if (this.state.currentTransfer.lines.length === 0) {
            this.notification.add(_t("Please add products"), { type: "warning" });
            return;
        }

        try {
            const vals = {
                id: this.state.currentTransfer.id,
                loc_dest_id: parseInt(this.state.currentTransfer.loc_dest_id) || false,
                note: this.state.currentTransfer.note,
                state: isDone ? 'shipped' : 'draft',
                lines: this.state.currentTransfer.lines.map(l => ({
                    product_id: parseInt(l.product_id),
                    qty: parseFloat(l.qty) || 0,
                    price: parseFloat(l.price) || 0,
                })),
            };
            await this.orm.call("pos.dashboard.swift", "create_or_update_transfer", [vals]);
            this.notification.add(isDone ? _t("Stock transfer request sent") : _t("Draft saved"), { type: "success" });
            this.state.view = 'list';
            await this.loadTransfers();
        } catch (e) {
            console.error("Save failed", e);
            this.notification.add(_t("Error saving data"), { type: "danger" });
        }
    }

    // ─── Receiver Handlers ────────────────────────────────────────

    get filteredReceiveLines() {
        if (!this.state.currentTransfer) return [];
        const lines = this.state.currentTransfer.lines;
        if (this.state.receiveTab === 'match') return lines.filter(l => l.qty === l.received_qty);
        if (this.state.receiveTab === 'mismatch') return lines.filter(l => l.qty !== l.received_qty && l.received_qty > 0);
        if (this.state.receiveTab === 'unreceived') return lines.filter(l => l.received_qty === 0);
        return lines;
    }

    async receiveTransfer() {
        try {
            const lines = this.state.currentTransfer.lines.map(l => ({
                id: l.id,
                received_qty: l.received_qty,
            }));
            await this.orm.call("pos.dashboard.swift", "action_receive_transfer", [this.state.currentTransfer.id, lines]);
            this.notification.add(_t("Goods receipt completed"), { type: "success" });
            this.state.view = 'list';
            await this.loadTransfers();
        } catch (e) {
            console.error("Receive failed", e);
            this.notification.add(_t("Error receiving goods"), { type: "danger" });
        }
    }

    // ─── filter handlers ──────────────────────────────────────────

    async onFilterChange(type, value) {
        if (type === 'state') {
            const idx = this.state.filters.states.indexOf(value);
            if (idx > -1) {
                this.state.filters.states.splice(idx, 1);
            } else {
                this.state.filters.states.push(value);
            }
        } else {
            this.state.filters[type] = value;
        }
        await this.loadTransfers();
    }

    onSearchInput(ev) {
        this.state.searchKeyword = ev.target.value;
    }

    toggleSidebar() {
        this.state.sidebarCollapsed = !this.state.sidebarCollapsed;
    }

    formatNumber(val) {
        if (!val) return "0";
        return new Intl.NumberFormat('vi-VN').format(val);
    }

    getStatusLabel(state) {
        const labels = {
            'draft': _t('Draft'),
            'shipped': _t('Shipping'),
            'done': _t('Received')
        };
        return labels[state] || state;
    }
}

registry.category("actions").add("pos_theme_swift.swift_pos_stock_transfer", StockTransfer);

