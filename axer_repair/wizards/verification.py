from odoo import models, fields, api
from odoo.exceptions import UserError
from odoo.tools.translate import _

class RepairEndWizard(models.TransientModel):
    _name = 'repair.end.wizard'
    _description = 'Repair End Wizard'

    repair_id = fields.Many2one('repair.order', string='Repair Order', required=True)
    faceid = fields.Boolean(string='Face ID')
    wifi = fields.Boolean(string='Wifi')
    signal = fields.Boolean(string='Signal')
    screen = fields.Boolean(string='Screen')
    camera = fields.Boolean(string='Camera')
    speaker = fields.Boolean(string='Speaker')
    microphone = fields.Boolean(string='Microphone')
    charging = fields.Boolean(string='Charging')
    buttons = fields.Boolean(string='Buttons')
    touch = fields.Boolean(string='Touch')
    camerafront = fields.Boolean(string='Front Camera')
    truetone = fields.Boolean(string='True Tone')
    screw = fields.Boolean(string='Screw')
    earphone = fields.Boolean(string='Earphone')
    flash = fields.Boolean(string='Flash')
    # Agrega los demás campos necesarios

    fields_to_check = [
           'wifi', 'signal', 'screen', 'camera', 'speaker', 'microphone', 
           'charging', 'buttons', 'touch', 'camerafront', 'truetone', 
           'screw', 'earphone', 'flash', 'faceid'
         ]
    
    bypass_checks = fields.Boolean(string='Bypass Checks', default=False)
    note = fields.Text(string='Nota Adicional')

    # NUEVOS CAMPOS PARA COMPONENTES - ENFOQUE SIMPLIFICADO
    # En lugar de One2many, usamos campos Many2many que es más simple para wizards
    selected_component_ids = fields.Many2many(
        'repair.component', 
        string='Repaired components',
        help='Select the components that were repaired'
    )
    
    component_notes = fields.Text(
        string='Component notes',
        help='Additional notes about the repaired components'
    )
    
    # Campo para control de pasos del wizard
    wizard_step = fields.Selection([
        ('components', 'Componentes'),
        ('verification', 'Verification')
    ], string='Wizard step', default='components')

    @api.model
    def default_get(self, fields):
        res = super(RepairEndWizard, self).default_get(fields)
        repair = self.env['repair.order'].browse(self._context.get('active_id'))
        
        res.update({
            'repair_id': repair.id,
            # Los componentes se cargarán automáticamente en la vista
        })
        return res

    # REMOVER EL MÉTODO CREATE - ya no lo necesitamos

    def verificar_coincidencia_completa(self, repair):
        for field in self.fields_to_check:
            valor_self = getattr(self, field, None)
            valor_repair = getattr(repair, field, None)
            if valor_self != valor_repair:
               return False
        return True
    
    def action_confirm(self):
        self.ensure_one()
        repair = self.repair_id
        
        # PRIMERO: Guardar componentes reparados
        self._save_repaired_components()

        # Verificar si el bypass está activado
        if self.bypass_checks:
            campos_marcados = [field for field in self.fields_to_check if getattr(self, field)]
            mensaje = _("The following fields were ticked on completion: %s") % ", ".join(campos_marcados)
            if self.note:
                mensaje += _("\nNota adicional: %s") % self.note
            
            # Add información de componentes
            components_msg = self._get_components_message()
            if components_msg:
                mensaje += _("\n\nComponentes reparados: %s") % components_msg
                
            self.repair_id.message_post(body=mensaje, subtype_xmlid="mail.mt_note")
            self.repair_id.action_repair_end_confirmed()
            return
            
        # Verificar si al menos un campo está marcado como True
        if not any(getattr(self, field) for field in self.fields_to_check):
            raise UserError(_("Tick at least one field before confirming the repair."))
    
        if self.verificar_coincidencia_completa(repair):
        # Si todos los campos coinciden, confirmar la reparación
           self.repair_id.action_repair_end_confirmed()

        # Crear un mensaje con los campos marcados como True
           campos_marcados = [field for field in self.fields_to_check if getattr(self, field)]
           mensaje = _("The following fields were ticked on completion: %s") % ", ".join(campos_marcados)
           
           # Add información de componentes
           components_msg = self._get_components_message()
           if components_msg:
               mensaje += _("\n\nComponentes reparados: %s") % components_msg

        # Publicar el mensaje en el chatter
           self.repair_id.message_post(body=mensaje, subtype_xmlid="mail.mt_note")
        else:
            raise UserError(_("The fields ticked as repaired do not match the values on the repair order. Please review them and try again."))

    def _save_repaired_components(self):
        """Guardar componentes seleccionados en la orden de reparación"""
        self.ensure_one()
        
        # Limpiar componentes existentes
        self.repair_id.repaired_component_ids.unlink()
        
        # Crear nuevos registros para cada componente seleccionado
        for component in self.selected_component_ids:
            self.env['repair.order.component.line'].create({
                'repair_id': self.repair_id.id,
                'component_id': component.id,
                'repaired': True,
                'notes': self.component_notes or '',
            })
    
    def _get_components_message(self):
        """Obtener mensaje de componentes para el chatter"""
        if self.selected_component_ids:
            component_names = self.selected_component_ids.mapped('name')
            return ', '.join(component_names)
        return ''

    def action_next_step(self):
        """Avanzar al siguiente paso del wizard"""
        self.ensure_one()
        if self.wizard_step == 'components':
            # Validar que al menos un componente esté seleccionado
            if not self.selected_component_ids:
                raise UserError(_("Select at least one component that was repaired."))
            
            self.wizard_step = 'verification'
            return {
                'type': 'ir.actions.act_window',
                'res_model': 'repair.end.wizard',
                'res_id': self.id,
                'view_mode': 'form',
                'target': 'new',
                'context': self._context,
            }
    
    def action_previous_step(self):
        """Regresar al paso anterior"""
        self.ensure_one()
        if self.wizard_step == 'verification':
            self.wizard_step = 'components'
            return {
                'type': 'ir.actions.act_window',
                'res_model': 'repair.end.wizard',
                'res_id': self.id,
                'view_mode': 'form',
                'target': 'new',
                'context': self._context,
            }


# CLASE ELIMINADA - Ya no necesitamos RepairEndWizardComponentLine