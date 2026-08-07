/** @odoo-module **/

import { registry } from "@web/core/registry";
import { standardFieldProps } from "@web/views/fields/standard_field_props";
import { Component, onMounted, useState, useRef } from "@odoo/owl";

// Averías más frecuentes del taller. Se ofrecen como sugerencias mientras se
// escribe la descripción de la reparación.
const AVERIAS_HABITUALES = [
    "No Carga",
    "No Enciende",
    "NO Señal",
    "Cambio Conectores",
    "Revivar Bateria",
    "Revisar Pantalla",
    "Revisar Touch",
    "Revisar Botones",
    "Revisar Camara",
    "Revisar Bocina",
    "Revisar Microfono",
    "Revisar Vibrador",
    "Poca senal Wifi",
    "Revision de Antenas",
    "Cambio de Pantalla",
    "Pantalla en Blanco",
    "sonido distorsionado",
    "No se escucha",
    "Software",
    "Cuenta google",
    "Cambio de Touch",
    "Cambio de Bateria",
    "Cambio de Camara",
    "Cambio de Parlante",
    "Cambio de Microfono",
    "Cambio de Vibrador",
    "Cambio de Wifi",
    "Cambio de Bluetooth",
    "Cambio de Red Movil",
    "Batería se descarga rápido",
    "Reemplazo de tapa y cristal de la cámara",
    "Chequeo general",
    "Reparación del pin de carga",
    "Reparación de la placa base",
    "Reparación de la Tapa Trasera",
];

export class CommonIssuesWidget extends Component {
    static template = "axer_repair.CommonIssuesWidget";
    static props = { ...standardFieldProps };

    setup() {
        this.state = useState({
            query: this.valorActual,
            suggestions: [],
        });
        this.inputFieldRef = useRef("inputField");

        onMounted(() => {
            if (this.inputFieldRef.el) {
                this.inputFieldRef.el.value = this.state.query;
            }
        });
    }

    // En Odoo 17 el valor de un campo se lee del registro, no de props.value
    get valorActual() {
        return this.props.record.data[this.props.name] || "";
    }

    guardar(valor) {
        this.props.record.update({ [this.props.name]: valor });
    }

    onInput(ev) {
        const query = ev.target.value;
        const busqueda = query.toLowerCase();
        this.state.query = query;
        this.guardar(query);

        if (!busqueda) {
            this.state.suggestions = [];
            return;
        }
        this.state.suggestions = AVERIAS_HABITUALES
            .filter((s) => s.toLowerCase().includes(busqueda))
            .sort((a, b) => a.toLowerCase().indexOf(busqueda) - b.toLowerCase().indexOf(busqueda));
    }

    onSuggestionClick(sugerencia) {
        this.state.query = sugerencia;
        this.state.suggestions = [];
        if (this.inputFieldRef.el) {
            this.inputFieldRef.el.value = sugerencia;
        }
        this.guardar(sugerencia);
    }
}

export const commonIssuesWidget = {
    component: CommonIssuesWidget,
    displayName: "Averías frecuentes",
    supportedTypes: ["char", "text"],
};

registry.category("fields").add("common_issues", commonIssuesWidget);
