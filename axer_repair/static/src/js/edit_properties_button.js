/** @odoo-module **/

import { registry } from "@web/core/registry";
import { standardWidgetProps } from "@web/views/widgets/standard_widget_props";
import { _t } from "@web/core/l10n/translation";
import { Component, xml } from "@odoo/owl";

// Botón visible para añadir/editar los campos configurables de la sucursal.
// Odoo 19 solo ofrece esto desde el engranaje ⚙ → "Editar propiedades", algo
// que los operarios no encuentran. Este botón dispara exactamente el mismo
// evento del bus del modelo ("PROPERTY_FIELD:EDIT") que usa ese menú del
// controlador de formulario, y pone el widget de propiedades en modo edición.
export class AxerEditPropertiesButton extends Component {
    static template = xml`
        <button type="button"
                class="btn btn-secondary btn-sm axer-edit-props-btn"
                t-on-click="onClick"
                t-att-title="title">
            <i class="fa fa-cogs me-1"/>
            <span t-esc="label"/>
        </button>
    `;

    static props = { ...standardWidgetProps };

    get label() {
        return _t("Add / edit intake fields");
    }

    get title() {
        return _t("Add or edit the extra intake fields defined for this branch");
    }

    onClick() {
        // El registro siempre lleva referencia a su modelo; su bus es el mismo
        // que escucha el widget de propiedades. Con env.model como respaldo.
        const bus = this.props.record?.model?.bus || this.env.model?.bus;
        if (!bus) {
            return;
        }
        // El nombre del evento cambió entre versiones: Odoo 19 usa
        // "PROPERTY_FIELD:EDIT" (entra en modo edición) y Odoo 17 usa
        // "PROPERTY_FIELD:ADD_PROPERTY_VALUE" (crea una propiedad). Disparamos
        // ambos: solo el que escucha la versión activa surte efecto, el otro se
        // ignora. Así un único archivo vale para las ramas 17.0 y 19.0.
        bus.trigger("PROPERTY_FIELD:EDIT");
        bus.trigger("PROPERTY_FIELD:ADD_PROPERTY_VALUE");
    }
}

export const axerEditPropertiesButton = {
    component: AxerEditPropertiesButton,
};

registry.category("view_widgets").add("axer_edit_properties", axerEditPropertiesButton);
