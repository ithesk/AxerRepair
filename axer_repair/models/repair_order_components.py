# -*- coding: utf-8 -*-
from odoo import models, fields, api

class RepairOrder(models.Model):
    _inherit = 'repair.order'
    
    # Campos para componentes reparados
    repaired_component_ids = fields.One2many(
        'repair.order.component.line', 
        'repair_id', 
        string='Repaired components'
    )
    
    repaired_components_summary = fields.Text(
        string='Components summary', 
        compute='_compute_repaired_components_summary',
        store=True
    )
    
    @api.depends('repaired_component_ids.component_id', 'repaired_component_ids.repaired')
    def _compute_repaired_components_summary(self):
        for record in self:
            if record.repaired_component_ids:
                components = record.repaired_component_ids.filtered('repaired').mapped('component_id.name')
                record.repaired_components_summary = ', '.join(components) if components else ''
            else:
                record.repaired_components_summary = ''