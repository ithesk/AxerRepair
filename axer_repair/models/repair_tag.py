# -*- coding: utf-8 -*-
from odoo import models, fields, api

class RepairIssueTag(models.Model):
    _name = 'repair.issue.tag'
    _description = 'Common repair issue tags'

    name = fields.Char(string='Name', required=True)
    code = fields.Char(string='Code', required=True)
    color = fields.Integer(string='Color')
    description = fields.Text(string='Description')
    icon = fields.Char(string='Icono', help='Font Awesome icon code')
    
    # Si el problema está relacionado con algún campo específico en repair.order
    related_field = fields.Char(
        string='Campo relacionado', 
        help='Boolean field on repair.order to tick when this issue is selected'
    )
    
    _sql_constraints = [
        ('code_uniq', 'unique (code)', 'The code must be unique.'),
    ]