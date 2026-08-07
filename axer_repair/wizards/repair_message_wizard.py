# models/repair_message_wizard.py
from odoo import models, fields, api

class RepairMessageWizard(models.TransientModel):
    _name = 'repair.message.wizard'
    _description = 'Repair Message'

    message = fields.Text(string='Message', required=True)
    repair_id = fields.Many2one('repair.order', string='Repair Order')

    def action_save_message(self):
        self.ensure_one()
        repair_order = self.repair_id
        if repair_order:
            repair_order._cancel_repair_order(self.message)
        return {'type': 'ir.actions.act_window_close'}