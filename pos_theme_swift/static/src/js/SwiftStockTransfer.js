/** @odoo-module **/

import { Component, useState, onMounted } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";
import { registry } from "@web/core/registry";
import { _t } from "@web/core/l10n/translation";


export class StockTransfer extends Component {
    static template = "pos_theme_swift.StockTransfer";
    static _i18n_strings = [
        _t("Outbound"),
        _t("Inbound"),
        _t("Select branch"),
        _t("Status"),
        _t("Draft"),
        _t("Shipped"),
        _t("Received"),
        _t("Time"),
        _t("Today"),
        _t("This Month"),
        _t("Custom"),
        _t("Stock Transfer"),
        _t("Search by transfer code"),
        _t("Transfer Goods"),
        _t("Transfer Code"),
        _t("Type"),
        _t("Transfer Date"),
        _t("Receive Date"),
        _t("From Branch"),
        _t("To Branch"),
        _t("Transfer Value"),
        _t("Loading data..."),
        _t("No transfer records found"),
        _t("Receive Details"),
        _t("Type product name or code"),
        _t("Search products by code or name (F3)"),
        _t("On Hand:"),
        _t("All"),
        _t("Matched"),
        _t("Mismatch"),
        _t("Unreceived"),
        _t("No."),
        _t("Product Code"),
        _t("Product Name"),
        _t("UOM"),
        _t("Stock"),
        _t("Dest Stock"),
        _t("Transfer Qty"),
        _t("Receive Qty"),
        _t("Price"),
        _t("Subtotal"),
        _t("Auto code"),
        _t("Total Transfer Qty"),
        _t("Total Received Qty"),
        _t("Notes"),
        _t("Transfer Completed"),
        _t("Complete"),
        _t("Receive Goods"),
    ];

    setup() {
        this._t = _t;
        this.orm = useService("orm");
        this.notification = useService("notification");

        this.state = useState({
            view: 'list', // 'list', 'form' (sender), 'receive' (receiver)
            loading: true,
            sidebarCollapsed: false,
            records: [],
            locations: [],
            currentConfigId: false,
            currentLocationId: false,
            currentBranchName: _t("Branch"),
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
            await this.loadCurrentConfig();
            await this.loadLocations();
            await this.loadTransfers();
        });
    }

    // ─── data loading ─────────────────────────────────────────────

    _getContextConfigId() {
        const rawConfigId =
            this.props?.action?.context?.pos_config_id ||
            this.env?.config?.pos_config_id ||
            false;
        const configId = parseInt(rawConfigId, 10);
        return Number.isInteger(configId) ? configId : false;
    }

    async loadCurrentConfig() {
        try {
            const configs = await this.orm.searchRead(
                "pos.config",
                [["active", "=", true]],
                ["name"],
                { order: "name asc", limit: 200 }
            );
            const contextConfigId = this._getContextConfigId();
            const selected =
                (configs || []).find((config) => config.id === contextConfigId) ||
                (configs || [])[0] ||
                false;
            this.state.currentConfigId = selected ? selected.id : false;
            this.state.currentBranchName = selected ? selected.name : _t("Branch");
        } catch (e) {
            console.error("Failed to resolve current POS branch", e);
            this.state.currentConfigId = false;
            this.state.currentLocationId = false;
            this.state.currentBranchName = _t("Branch");
        }
    }

    async loadLocations() {
        try {
            this.state.locations = await this.orm.call("pos.dashboard.swift", "get_locations", []);
            const currentLocation = this.state.locations.find((loc) => loc.config_id === this.state.currentConfigId);
            this.state.currentLocationId = currentLocation ? currentLocation.location_id : false;
            if (currentLocation) {
                this.state.currentBranchName = currentLocation.name;
            }
        } catch (e) {
            console.error("Failed to load locations", e);
        }
    }

    async loadTransfers() {
        this.state.loading = true;
        try {
            const filters = {
                states: this.state.filters.states,
                date_range: this.state.filters.date_range,
            };
            this.state.records = await this.orm.call("pos.dashboard.swift", "get_stock_transfers", [filters, false]);
        } catch (e) {
            console.error("Failed to load transfers", e);
            this.notification.add(_t("Error loading stock transfer data"), { type: "danger" });
        } finally {
            this.state.loading = false;
        }
    }

    _buildRecordFromDetail(detail) {
        return {
            id: detail.id,
            name: detail.name,
            date_transfer: detail.date_transfer || "",
            date_receive: detail.date_receive || "",
            loc_src: detail.loc_src || "",
            loc_src_id: detail.loc_src_id || false,
            loc_src_config_id: detail.loc_src_config_id || false,
            loc_dest: detail.loc_dest || "",
            loc_dest_id: detail.loc_dest_id || false,
            loc_dest_config_id: detail.loc_dest_config_id || false,
            total_value: detail.total_value || 0,
            state: detail.state || "draft",
            direction: detail.direction || "other",
            can_receive: !!detail.can_receive,
        };
    }

    get displayRecords() {
        let records = [...this.state.records];
        const sourceConfigId = parseInt(this.state.filters.loc_src, 10) || false;
        const destConfigId = parseInt(this.state.filters.loc_dest, 10) || false;
        const sourceLocation = sourceConfigId
            ? (this.state.locations.find((loc) => loc.config_id === sourceConfigId) || false)
            : false;
        const destLocation = destConfigId
            ? (this.state.locations.find((loc) => loc.config_id === destConfigId) || false)
            : false;
        const sourceLocationId = sourceLocation ? sourceLocation.location_id : false;
        const destLocationId = destLocation ? destLocation.location_id : false;
        const sourceBranchName = (sourceLocation?.name || "").trim().toLowerCase();
        const destBranchName = (destLocation?.name || "").trim().toLowerCase();

        if (sourceConfigId || sourceLocationId) {
            records = records.filter((record) =>
                record.loc_src_config_id === sourceConfigId ||
                (sourceLocationId && record.loc_src_id === sourceLocationId) ||
                (sourceBranchName && (record.loc_src || "").trim().toLowerCase() === sourceBranchName)
            );
        }
        if (destConfigId || destLocationId) {
            records = records.filter((record) =>
                record.loc_dest_config_id === destConfigId ||
                (destLocationId && record.loc_dest_id === destLocationId) ||
                (destBranchName && (record.loc_dest || "").trim().toLowerCase() === destBranchName)
            );
        }
        return records.map((record) => ({
            ...record,
            direction: this.getDisplayDirection(record),
        }));
    }

    getDisplayDirection(record) {
        const sourceConfigId = parseInt(this.state.filters.loc_src, 10) || false;
        const destConfigId = parseInt(this.state.filters.loc_dest, 10) || false;
        if (destConfigId && record.loc_dest_config_id === destConfigId) {
            return "inbound";
        }
        if (sourceConfigId && record.loc_src_config_id === sourceConfigId) {
            return "outbound";
        }
        if (destConfigId && (record.loc_dest || "").trim().toLowerCase() === ((this.state.locations.find((loc) => loc.config_id === destConfigId)?.name || "").trim().toLowerCase())) {
            return "inbound";
        }
        if (sourceConfigId && (record.loc_src || "").trim().toLowerCase() === ((this.state.locations.find((loc) => loc.config_id === sourceConfigId)?.name || "").trim().toLowerCase())) {
            return "outbound";
        }
        if (this.state.currentConfigId && record.loc_dest_config_id === this.state.currentConfigId) {
            return "inbound";
        }
        if (this.state.currentConfigId && record.loc_src_config_id === this.state.currentConfigId) {
            return "outbound";
        }
        return record.direction || "other";
    }

    getPerspectiveConfigId(record) {
        const sourceConfigId = parseInt(this.state.filters.loc_src, 10) || false;
        const destConfigId = parseInt(this.state.filters.loc_dest, 10) || false;
        if (destConfigId && record.loc_dest_config_id === destConfigId) {
            return destConfigId;
        }
        if (sourceConfigId && record.loc_src_config_id === sourceConfigId) {
            return sourceConfigId;
        }
        if (this.state.currentConfigId && record.loc_dest_config_id === this.state.currentConfigId) {
            return this.state.currentConfigId;
        }
        if (this.state.currentConfigId && record.loc_src_config_id === this.state.currentConfigId) {
            return this.state.currentConfigId;
        }
        return record.loc_dest_config_id || record.loc_src_config_id || false;
    }

    async openTransfer(record) {
        this.state.loading = true;
        try {
            const detail = await this.orm.call(
                "pos.dashboard.swift",
                "get_transfer_detail",
                [record.id, this.getPerspectiveConfigId(record)]
            );
            if (detail) {
                this.state.currentTransfer = detail;
                this.state.view = detail.direction === 'inbound' ? 'receive' : 'form';
            }
        } catch (e) {
            console.error("Failed to load detail", e);
        } finally {
            this.state.loading = false;
        }
    }

    // ─── Sender Form Handlers ─────────────────────────────────────

    async createNewTransfer() {
        const sourceConfigId = this.state.currentConfigId || false;
        const sourceLocation = this.state.locations.find((loc) => loc.config_id === sourceConfigId) || false;
        this.state.currentTransfer = {
            id: false,
            loc_src: sourceLocation ? sourceLocation.name : this.state.currentBranchName,
            loc_src_id: sourceLocation ? sourceLocation.location_id : (this.state.currentLocationId || false),
            loc_src_config_id: sourceConfigId,
            loc_dest_id: false,
            loc_dest_config_id: false,
            loc_dest: "",
            note: "",
            lines: [],
            state: 'draft',
            date_transfer: new Date().toLocaleString('vi-VN'),
        };
        this.state.view = 'form';
    }

    get sourceLocations() {
        return this.state.locations;
    }

    get destinationLocations() {
        const sourceConfigId = parseInt(this.state.currentTransfer?.loc_src_config_id, 10) || false;
        return this.state.locations.filter((loc) => loc.config_id !== sourceConfigId);
    }

    async onSourceChange(ev) {
        const sourceConfigId = parseInt(ev.target.value, 10) || false;
        const source = this.state.locations.find((loc) => loc.config_id === sourceConfigId) || false;
        this.state.currentTransfer.loc_src_config_id = sourceConfigId;
        this.state.currentTransfer.loc_src_id = source ? source.location_id : false;
        this.state.currentTransfer.loc_src = source ? source.name : "";
        if (sourceConfigId && parseInt(this.state.currentTransfer.loc_dest_config_id, 10) === sourceConfigId) {
            this.state.currentTransfer.loc_dest_config_id = false;
            this.state.currentTransfer.loc_dest_id = false;
            this.state.currentTransfer.loc_dest = "";
        }
        await this.refreshSourceStock();
        await this._refreshDestinationStock();
    }

    onDestinationChange(ev) {
        const destinationConfigId = parseInt(ev.target.value, 10) || false;
        this.state.currentTransfer.loc_dest_config_id = destinationConfigId;
        const destination = this.state.locations.find((loc) => loc.config_id === destinationConfigId);
        this.state.currentTransfer.loc_dest_id = destination ? destination.location_id : false;
        this.state.currentTransfer.loc_dest = destination ? destination.name : "";
        this._refreshDestinationStock().catch((error) => {
            console.error("Failed to refresh destination stock", error);
        });
    }

    async refreshSourceStock() {
        if (!this.state.currentTransfer || !this.state.currentTransfer.lines?.length) {
            return;
        }
        const sourceLocationId = parseInt(this.state.currentTransfer.loc_src_id, 10) || false;
        if (!sourceLocationId) {
            for (const line of this.state.currentTransfer.lines) {
                line.qty_on_hand = 0;
            }
            return;
        }
        const productIds = this.state.currentTransfer.lines.map((line) => line.product_id);
        const stockByProduct = await this.orm.call("pos.dashboard.swift", "get_location_stock", [productIds, sourceLocationId]);
        for (const line of this.state.currentTransfer.lines) {
            line.qty_on_hand = stockByProduct[line.product_id] || 0;
        }
    }

    async _refreshDestinationStock() {
        if (!this.state.currentTransfer || !this.state.currentTransfer.lines?.length) {
            return;
        }
        const locationId = this.state.currentTransfer.loc_dest_id;
        if (!locationId) {
            for (const line of this.state.currentTransfer.lines) {
                line.qty_dest = 0;
            }
            return;
        }
        const productIds = this.state.currentTransfer.lines.map((line) => line.product_id);
        const stock = await this.orm.call("pos.dashboard.swift", "get_location_stock", [productIds, locationId]);
        for (const line of this.state.currentTransfer.lines) {
            line.qty_dest = stock[line.product_id] || 0;
        }
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
            const sourceConfigId = parseInt(this.state.currentTransfer?.loc_src_config_id, 10) || false;
            if (!sourceConfigId) {
                this.state.productSearchResults = [];
                this.state.showProductDropdown = false;
                return;
            }
            const results = await this.orm.call("pos.dashboard.swift", "get_inventory_products", [keyword, sourceConfigId]);
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
        if (!this.state.currentTransfer.loc_src_config_id) {
            this.notification.add(_t("Please select source branch"), { type: "warning" });
            return;
        }
        if (!this.state.currentTransfer.loc_dest_id) {
            this.notification.add(_t("Please select receiving branch"), { type: "warning" });
            return;
        }
        if (parseInt(this.state.currentTransfer.loc_dest_config_id, 10) === parseInt(this.state.currentTransfer.loc_src_config_id, 10)) {
            this.notification.add(_t("Destination branch must be different from source branch."), { type: "warning" });
            return;
        }
        if (this.state.currentTransfer.lines.length === 0) {
            this.notification.add(_t("Please add products"), { type: "warning" });
            return;
        }

        try {
            const vals = {
                id: this.state.currentTransfer.id,
                config_id: this.state.currentTransfer.loc_src_config_id || false,
                dest_config_id: this.state.currentTransfer.loc_dest_config_id || false,
                loc_src_id: this.state.currentTransfer.loc_src_id || false,
                loc_dest_id: parseInt(this.state.currentTransfer.loc_dest_id) || false,
                note: this.state.currentTransfer.note,
                state: isDone ? 'shipped' : 'draft',
                lines: this.state.currentTransfer.lines.map(l => ({
                    product_id: parseInt(l.product_id),
                    qty: parseFloat(l.qty) || 0,
                    price: parseFloat(l.price) || 0,
                })),
            };
            const result = await this.orm.call("pos.dashboard.swift", "create_or_update_transfer", [vals]);
            this.state.view = 'list';
            await this.loadTransfers();
            const createdId = result?.id || false;
            const createdName = result?.name || "";
            const visible = createdId ? this.displayRecords.some((record) => record.id === createdId) : false;
            const message = createdName
                ? (isDone ? _t("Stock transfer request sent: %s", createdName) : _t("Draft saved: %s", createdName))
                : (isDone ? _t("Stock transfer request sent") : _t("Draft saved"));
            this.notification.add(message, { type: "success" });
            if (createdId && !this.state.records.some((record) => record.id === createdId)) {
                const hiddenDetail = await this.orm.call(
                    "pos.dashboard.swift",
                    "get_transfer_detail",
                    [createdId, this.state.currentConfigId || false]
                );
                if (hiddenDetail && !this.state.records.some((record) => record.id === createdId)) {
                    this.state.records.unshift(this._buildRecordFromDetail(hiddenDetail));
                }
            }
            if (createdId && !visible && (this.state.filters.loc_src || this.state.filters.loc_dest)) {
                this.notification.add(
                    _t("Transfer %s was created but is hidden by the current branch/filter view.", createdName || createdId),
                    { type: "warning", title: _t("Filter notice") }
                );
            }
        } catch (e) {
            console.error("Save failed", e);
            const message =
                e?.data?.message ||
                e?.data?.debug ||
                e?.message ||
                _t("Error saving data");
            this.notification.add(message, { type: "danger", title: _t("Save failed") });
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
            const message =
                e?.data?.message ||
                e?.data?.debug ||
                e?.message ||
                _t("Error receiving goods");
            this.notification.add(message, { type: "danger", title: _t("Receive failed") });
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

    getEffectiveConfigId() {
        return this.state.filters.loc_dest || this.state.filters.loc_src || this.state.currentConfigId || false;
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
