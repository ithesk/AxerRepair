# -*- coding: utf-8 -*-
from odoo import models, fields, api

class RepairComponent(models.Model):
    _name = 'repair.component'
    _description = 'Repair Component'
    _order = 'sequence, name'

    name = fields.Char(string='Component name', required=True, translate=True)
    code = fields.Char(string='Code', required=True)
    sequence = fields.Integer(string='Secuencia', default=10)
    active = fields.Boolean(string='Active', default=True)
    category = fields.Selection([
        ('hardware', 'Hardware'),
        ('software', 'Software'),
        ('accessory', 'Accesorio'),
        ('other', 'Otro')
    ], string='Category', default='hardware')
    
    _sql_constraints = [
        ('code_unique', 'UNIQUE(code)', 'The component code must be unique.')
    ]

class RepairOrderComponentLine(models.Model):
    _name = 'repair.order.component.line'
    _description = 'Repaired components'
    _rec_name = 'component_id'
    
    repair_id = fields.Many2one('repair.order', string='Repair order', required=True, ondelete='cascade')
    component_id = fields.Many2one('repair.component', string='Componente', required=True)
    repaired = fields.Boolean(string='Reparado', default=True)
    notes = fields.Text(string='Notas')
    sequence = fields.Integer(related='component_id.sequence', store=True, readonly=True)