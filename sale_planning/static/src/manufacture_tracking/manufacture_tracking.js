/** @odoo-module **/

import { registry } from "@web/core/registry";
import { Component, onWillStart, useState } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";
import { _t } from "@web/core/l10n/translation";

class ManufactureTracking extends Component {
  static template = "sale_planning.ManufactureTracking";

  static _i18n_strings = [
    _t("MANUFACTURING TRACKING"),
    _t("Loading..."),
    _t("DAILY PROD"),
    _t("WEEKLY PROD"),
    _t("MONTHLY PROD"),
    _t("RATE"),
    _t("PLAN"),
    _t("TARGET"),
    _t("RESULT"),
    _t("Delay Orders"),
    _t("Delayed manufacturing orders"),
    _t("Bottleneck"),
    _t("Critical work center"),
    _t("PRODUCTION PROGRESS BY LINE"),
    _t("No data"),
    _t("No"),
    _t("Line"),
    _t("Product"),
    _t("Delay"),
    _t("Load"),
    _t("Status"),
    _t("On track"),
    _t("Near capacity"),
    _t("Overloaded / delayed"),
  ];

  setup() {
    this._t = _t;
    this.orm = useService("orm");
    this.state = useState({
      kpis: null,
      delay: null,
      bottleneck: null,
      table: [],
      loading: true,
    });

    onWillStart(async () => {
      const [kpis, delay, bottleneck, table] = await Promise.all([
        this.orm.call("sale.planning.manufacture.tracking", "get_kpis", []),
        this.orm.call("sale.planning.manufacture.tracking", "get_delay_orders", []),
        this.orm.call("sale.planning.manufacture.tracking", "get_bottleneck", []),
        this.orm.call("sale.planning.manufacture.tracking", "get_lines_table", []),
      ]);

      this.state.kpis = kpis;
      this.state.delay = delay;
      this.state.bottleneck = bottleneck;
      this.state.table = table?.rows || [];
      this.state.loading = false;
    });
  }
}

registry.category("actions").add("sale_planning.manufacture_tracking", ManufactureTracking);

export default ManufactureTracking;
