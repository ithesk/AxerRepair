/** @odoo-module **/

import { registry } from "@web/core/registry";
import { standardFieldProps } from "@web/views/fields/standard_field_props";
import { formatMonetary } from "@web/views/fields/formatters";
import { Component, xml } from "@odoo/owl";

// Cuánto sube o baja el presupuesto con cada pulsación.
const PASO = 100;

export class QuickBudgetWidget extends Component {
    static template = xml`
        <div class="d-flex align-items-center quick-budget-field"
             t-att-class="{'o_readonly_modifier': props.readonly}">
            <button class="quick-budget-btn quick-budget-btn-minus"
                    t-on-click="decrement"
                    t-att-disabled="props.readonly"
                    title="Reducir el presupuesto">
                <i class="fa fa-minus"/>
            </button>

            <div class="quick-budget-input-container">
                <input type="text"
                       class="o_input quick-budget-input"
                       t-att-value="textoFormateado"
                       t-on-change="onInput"
                       t-att-readonly="props.readonly"
                       placeholder="0"/>
            </div>

            <button class="quick-budget-btn quick-budget-btn-plus"
                    t-on-click="increment"
                    t-att-disabled="props.readonly"
                    title="Aumentar el presupuesto">
                <i class="fa fa-plus"/>
            </button>
        </div>
    `;

    static props = {
        ...standardFieldProps,
        currencyField: { type: String, optional: true },
    };

    // El valor vive en el registro: así el widget refleja los cambios que
    // vengan de otros campos o de un onchange del servidor.
    get valor() {
        return this.props.record.data[this.props.name] || 0;
    }

    get textoFormateado() {
        const campoMoneda = this.props.currencyField || "currency_id";
        const moneda = this.props.record.data[campoMoneda];
        return formatMonetary(this.valor, {
            currencyId: moneda && moneda[0],
            digits: [false, 0],
        });
    }

    guardar(nuevo) {
        this.props.record.update({ [this.props.name]: nuevo });
    }

    increment() {
        this.guardar(Math.round(this.valor) + PASO);
    }

    decrement() {
        this.guardar(Math.max(0, Math.round(this.valor) - PASO));
    }

    onInput(ev) {
        const digitos = (ev.target.value || "").replace(/[^\d]/g, "");
        this.guardar(parseInt(digitos, 10) || 0);
    }
}

export const quickBudgetWidget = {
    component: QuickBudgetWidget,
    displayName: "Presupuesto rápido",
    supportedTypes: ["monetary", "float"],
    extractProps: ({ options }) => ({
        currencyField: options.currency_field,
    }),
};

registry.category("fields").add("quick_budget", quickBudgetWidget);
