/** @odoo-module **/

import { registry } from "@web/core/registry";
import { standardFieldProps } from "@web/views/fields/standard_field_props";

import { Component, useState, onWillStart } from "@odoo/owl";

export class DeliveryDatePicker extends Component {
    setup() {
        // Inicializar el estado
        this.state = useState({
            showPicker: false,
            selectedDay: null,
            selectedTime: null,
            value: '',
            initialized: false
        });

        // Horarios disponibles
        this.timeSlots = [
            { label: '09:00', value: '09:00:00' },
            { label: '09:30', value: '09:30:00' },
            { label: '10:00', value: '10:00:00' },
            { label: '10:30', value: '10:30:00' },
            { label: '11:00', value: '11:00:00' },
            { label: '11:30', value: '11:30:00' },
            { label: '14:00', value: '14:00:00' },
            { label: '14:30', value: '14:30:00' },
            { label: '15:00', value: '15:00:00' },
            { label: '15:30', value: '15:30:00' },
            { label: '16:00', value: '16:00:00' },
            { label: '16:30', value: '16:30:00' },
            { label: '17:00', value: '17:00:00' },
            { label: '17:30', value: '17:30:00' },
            { label: '18:00', value: '18:00:00' },
            { label: '18:30', value: '18:30:00' }
        ];

        // Inicializar con el valor existente si hay uno
        onWillStart(() => {
            const actual = this.valorActual;
            if (actual) {
                this.state.value = actual;
                this.initializeFromValue(actual);
            }
            this.state.initialized = true;
        });
    }

    // En Odoo 17 el valor se lee y se escribe a través del registro
    get valorActual() {
        return this.props.record.data[this.props.name] || "";
    }

    initializeFromValue(value) {
        try {
            const date = new Date(value.replace(' ', 'T'));
            if (!isNaN(date.getTime())) {
                const availableDays = this.getAvailableDays();
                const dayValue = this.formatDateValue(date);
                const matchingDay = availableDays.find(day => day.value === dayValue);

                if (matchingDay) {
                    this.state.selectedDay = matchingDay;
                    const timeValue = `${date.getHours().toString().padStart(2, '0')}:${date.getMinutes().toString().padStart(2, '0')}:00`;
                    const matchingTime = this.timeSlots.find(slot => slot.value === timeValue);
                    if (matchingTime) {
                        this.state.selectedTime = matchingTime;
                    }
                }
            }
        } catch (error) {
            console.warn('Error al inicializar valor:', error);
        }
    }

    getAvailableDays() {
        const days = [];
        const today = new Date();
        today.setHours(0, 0, 0, 0);

        for (let i = 0; i < 7; i++) {
            const date = new Date(today);
            date.setDate(today.getDate() + i);
            
            if (date.getDay() !== 0 && date >= today) {
                days.push({
                    label: i === 0 ? 'Hoy' :
                           i === 1 ? 'Mañana' :
                           this.formatDate(date),
                    value: this.formatDateValue(date),
                    isToday: i === 0,
                    date: new Date(date)
                });
            }
        }
        return days;
    }

    togglePicker(ev) {
        if (!this.props.readonly) {
            ev.preventDefault();
            ev.stopPropagation();
            this.state.showPicker = !this.state.showPicker;
        }
    }

    selectDay(day, ev) {
        ev.preventDefault();
        ev.stopPropagation();
        this.state.selectedDay = day;
    }

    selectTime(time, ev) {
        ev.preventDefault();
        ev.stopPropagation();
        
        if (!this.state.selectedDay) return;

        try {
            const selectedDate = new Date(this.state.selectedDay.date);
            const [hours, minutes] = time.value.split(':');
            selectedDate.setHours(parseInt(hours), parseInt(minutes), 0, 0);

            const formattedDate = this.formatToOdooDateTime(selectedDate);
            
            this.state.selectedTime = time;
            this.state.value = formattedDate;
            this.props.record.update({ [this.props.name]: formattedDate });
            this.state.showPicker = false;
        } catch (error) {
            console.warn('Error al seleccionar hora:', error);
        }
    }

    formatDate(date) {
        return date.toLocaleDateString('es-ES', {
            weekday: 'long',
            day: 'numeric'
        });
    }

    formatDateValue(date) {
        return date.toISOString().split('T')[0];
    }

    formatToOdooDateTime(date) {
        return `${date.getFullYear()}-${
            String(date.getMonth() + 1).padStart(2, '0')}-${
            String(date.getDate()).padStart(2, '0')} ${
            String(date.getHours()).padStart(2, '0')}:${
            String(date.getMinutes()).padStart(2, '0')}:00`;
    }

    formatDisplayValue() {
        if (!this.state.value) return '';
        try {
            const date = new Date(this.state.value.replace(' ', 'T'));
            return date.toLocaleString('es-ES', {
                weekday: 'long',
                day: 'numeric',
                month: 'long',
                hour: '2-digit',
                minute: '2-digit'
            });
        } catch (error) {
            console.warn('Error al formatear valor:', error);
            return this.state.value;
        }
    }

    isTimeAvailable(time, day) {
        if (day.isToday) {
            const now = new Date();
            const [hours, minutes] = time.value.split(':').map(Number);
            const timeDate = new Date(day.date);
            timeDate.setHours(hours, minutes, 0, 0);
            return timeDate > now;
        }
        return true;
    }
}

DeliveryDatePicker.template = "axer_repair.DeliveryDatePicker";
DeliveryDatePicker.props = { ...standardFieldProps };

export const deliveryDatePicker = {
    component: DeliveryDatePicker,
    displayName: "Fecha de entrega",
    supportedTypes: ["char"],
};

registry.category("fields").add("delivery_date_picker", deliveryDatePicker);