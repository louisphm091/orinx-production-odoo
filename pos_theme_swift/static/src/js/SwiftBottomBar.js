/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { PaymentScreen } from "@point_of_sale/app/screens/payment_screen/payment_screen";
import { ProductScreen } from "@point_of_sale/app/screens/product_screen/product_screen";

const BottomBarMixin = {
  _sppGetPos() {
    return this.pos || this.env?.services?.pos;
  },

  sppOrder() {
    const pos = this._sppGetPos();
    if (!pos) return null;
    if (typeof pos.getOrder === "function") return pos.getOrder();
    if (typeof pos.get_order === "function") return pos.get_order();
    return null;
  },

  sppCustomerLabel() {
    const order = this.sppOrder();
    const partner =
      order?.get_partner?.() ||
      order?.partner ||
      order?.partner_id ||
      null;

    const name =
      partner?.name ||
      (Array.isArray(partner) ? partner[1] : null) ||
      null;

    return name || "Khách lẻ";
  },

  _sppSaleModeKey() {
    return this._sppGetPos();
  },

  getSppSaleMode() {
    const pos = this._sppSaleModeKey();
    if (!pos) return "quick";
    if (!pos.__sppSaleMode) pos.__sppSaleMode = "quick";
    return pos.__sppSaleMode;
  },

  isSppSaleMode(mode) {
    return this.getSppSaleMode() === mode;
  },

  onSppSetSaleMode(ev, mode) {
    if (ev) {
      ev.preventDefault();
      ev.stopPropagation();
      ev.stopImmediatePropagation?.();
    }
    const pos = this._sppSaleModeKey();
    if (!pos) return;
    pos.__sppSaleMode = mode;
    this.render?.();
  },

  _sppFindNativeCustomerButton() {
    const selectors = [
      ".pos .payment-screen .partner-button",
      ".pos .payment-screen .button.customer",
      ".pos .payment-screen button.customer",
      ".pos .payment-screen .js_customer",
      ".pos .payment-screen .js_set_customer",
      ".pos .payment-screen .set-partner",

      ".pos .product-screen .set-partner",
      ".pos .product-screen .clientlist-button",
      ".pos .product-screen .partner-button",
      ".pos .product-screen .js_customer",
      ".pos .product-screen .js_set_customer",
    ];

    for (const s of selectors) {
      const el = document.querySelector(s);
      if (el) return el;
    }
    return null;
  },

  async onSppOpenCustomer(ev) {
    if (ev) {
      ev.preventDefault();
      ev.stopPropagation();
      ev.stopImmediatePropagation?.();
    }

    console.log("[SapphireBottomBar] click customer");

    const nativeBtn = this._sppFindNativeCustomerButton();
    if (nativeBtn) {
      console.log("[SapphireBottomBar] trigger native customer button:", nativeBtn);
      nativeBtn.click();
      return;
    }

    if (typeof this.onClickPartner === "function") {
      console.log("[SapphireBottomBar] using this.onClickPartner()");
      await this.onClickPartner();
      return;
    }
    if (typeof this.selectPartner === "function") {
      console.log("[SapphireBottomBar] using this.selectPartner()");
      await this.selectPartner();
      return;
    }

    if (typeof this.showTempScreen === "function") {
      console.log("[SapphireBottomBar] using showTempScreen(PartnerListScreen)");
      const order = this.sppOrder();
      const currentPartner = order?.get_partner?.() || null;

      const { confirmed, payload } = await this.showTempScreen("PartnerListScreen", {
        partner: currentPartner,
      });

      if (confirmed && payload && order?.set_partner) {
        order.set_partner(payload);
        order.trigger?.("change", order);
        this.render?.();
      }
      return;
    }

    if (typeof this.showScreen === "function") {
      console.log("[SapphireBottomBar] using showScreen(PartnerListScreen)");
      await this.showScreen("PartnerListScreen");
      return;
    }

    console.warn("[SapphireBottomBar] Cannot open customer list (no native button / handler / showScreen).");
  },
};

patch(PaymentScreen.prototype, BottomBarMixin);
patch(ProductScreen.prototype, BottomBarMixin);
