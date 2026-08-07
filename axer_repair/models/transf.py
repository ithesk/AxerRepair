# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError, UserError
import logging
from datetime import datetime
import subprocess

_logger = logging.getLogger(__name__)

class InternalTransfer(models.Model):
    _name = 'internal.transfer'
    _description = 'Internal device transfer'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'create_date desc'

    name = fields.Char('Reference', default=lambda self: _('New'), readonly=True)
    date = fields.Date('Fecha', default=fields.Date.today, required=True, tracking=True)
    location_origin_id = fields.Many2one('repair.location', string='Source branch', required=True, tracking=True)
    location_dest_id = fields.Many2one('repair.location', string='Destination branch', required=True, tracking=True)
    state = fields.Selection([
        ('draft', 'Draft'),
        ('confirmed', 'Confirmed'),
        ('ready', 'Ready to receive'),
        ('done', 'Realizado'),
        ('cancel', 'Cancelled')
    ], string='State', default='draft', tracking=True)
    transfer_line_ids = fields.One2many('internal.transfer.line', 'transfer_id', string='Transfer lines')
    notes = fields.Text('Notas')
    user_id = fields.Many2one('res.users', string='Responsable', default=lambda self: self.env.user, tracking=True)
    company_id = fields.Many2one('res.company', string='Company', default=lambda self: self.env.company)
    
    # Campos para impresión
    barcode = fields.Char('Barcode', compute='_compute_barcode', store=True)
    
    _sql_constraints = [
        ('name_uniq', 'unique(name)', 'La referencia de transferencia debe ser única!')
    ]
    
    @api.depends('name')
    def _compute_barcode(self):
        for record in self:
            if record.name and record.name != 'New':
                record.barcode = record.name
            else:
                record.barcode = False
    
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code('internal.transfer') or _('New')
        return super(InternalTransfer, self).create(vals_list)
    
    @api.onchange('location_origin_id')
    def _onchange_location_origin_id(self):
        if self.location_origin_id and self.location_dest_id and self.location_origin_id == self.location_dest_id:
            self.location_dest_id = False
            return {'warning': {'title': _('Advertencia'), 'message': _('Source and destination branches cannot be the same.')}}

    @api.onchange('location_dest_id')
    def _onchange_location_dest_id(self):
        if self.location_origin_id and self.location_dest_id and self.location_origin_id == self.location_dest_id:
            self.location_dest_id = False
            return {'warning': {'title': _('Advertencia'), 'message': _('Source and destination branches cannot be the same.')}}
    
    def action_confirm(self):
        for record in self:
            if not record.transfer_line_ids:
                raise UserError(_('You cannot confirm a transfer with no lines.'))
            record.write({'state': 'confirmed'})
        return True
    
    def action_ready_to_receive(self):
        """Marca la transferencia como lista para recibir"""
        for record in self:
            if not record.transfer_line_ids:
                raise UserError(_('You cannot prepare a transfer with no lines.'))
            # Marcar todas las líneas como pendientes de recepción
            for line in record.transfer_line_ids:
                line.write({'receive_state': 'pending'})
            record.write({'state': 'ready'})
        return True
        
    def action_done(self):
        """Completa la transferencia cuando todos los equipos han sido recibidos"""
        for record in self:
            if not record.transfer_line_ids:
                raise UserError(_('You cannot carry out a transfer with no lines.'))
                
            # Verificar si todos los equipos han sido recibidos
            pending_lines = record.transfer_line_ids.filtered(lambda l: l.receive_state == 'pending')
            if pending_lines:
                raise UserError(_('The transfer cannot be completed: %s devices are still awaiting reception.') % len(pending_lines))
                
            # Actualizar la ubicación de los equipos en repair.order
            for line in record.transfer_line_ids:
                if line.repair_order_id:
                    line.repair_order_id.write({
                        'branch_id': record.location_dest_id.id
                    })
            record.write({'state': 'done'})
        return True
        
    def action_scan_receive(self):
        """Abre el wizard para escanear equipos en recepción"""
        return {
            'name': _('Recibir Devices'),
            'type': 'ir.actions.act_window',
            'res_model': 'barcode.receive.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_transfer_id': self.id}
        }
    
    def action_cancel(self):
        for record in self:
            record.write({'state': 'cancel'})
        return True
    
    def action_draft(self):
        for record in self:
            record.write({'state': 'draft'})
        return True
    
    def action_scan_barcode(self):
        return {
            'name': _('Scan barcode'),
            'type': 'ir.actions.act_window',
            'res_model': 'barcode.scan.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_transfer_id': self.id}
        }
    
    def action_print_label(self):
        """Imprime la etiqueta de la transferencia."""
        self.ensure_one()
        origen = self.location_origin_id
        return self.env["repair.printing"].imprimir(
            "axer_repair.action_report_internal_transfer", self,
            impresora=origen.printer_name,
            servidor=origen.cups_server_ip,
        )

    @api.depends("name", "location_origin_id", "location_dest_id")
    def _compute_display_name(self):
        # En Odoo 17 name_get() ya no se llama: el nombre mostrado se calcula
        # con este método, así que antes la transferencia salía sin el origen
        # ni el destino.
        for transfer in self:
            nombre = transfer.name or ""
            if transfer.location_origin_id and transfer.location_dest_id:
                nombre = "%s (%s → %s)" % (nombre,
                                           transfer.location_origin_id.name,
                                           transfer.location_dest_id.name)
            transfer.display_name = nombre

class InternalTransferLine(models.Model):
    _name = 'internal.transfer.line'
    _description = 'Internal transfer line'
    _order = 'sequence, id'
    
    sequence = fields.Integer('Secuencia', default=10)
    transfer_id = fields.Many2one('internal.transfer', string='Transferencia', ondelete='cascade', required=True)
    repair_order_id = fields.Many2one('repair.order', string='Device', required=True)
    product_id = fields.Many2one('product.product', string='Producto', related='repair_order_id.product_id', store=True)
    quantity = fields.Integer('Cantidad', default=1)
    imei = fields.Char('IMEI / Serial number', related='repair_order_id.imei', store=True)
    description = fields.Char('Description', related='repair_order_id.description', store=True)
    state = fields.Selection([
        ('draft', 'Draft'),
        ('confirmed', 'Confirmed'),
        ('ready', 'Ready to receive'),
        ('done', 'Realizado'),
        ('cancel', 'Cancelled')
    ], string='State', related='transfer_id.state', store=True)
    receive_state = fields.Selection([
        ('pending', 'Pending'),
        ('received', 'Received')
    ], string='Reception status', default='pending', copy=False)
    received_date = fields.Datetime('Reception date', copy=False, readonly=True)
    received_by = fields.Many2one('res.users', string='Received by', copy=False, readonly=True)
    company_id = fields.Many2one('res.company', related='transfer_id.company_id', store=True)
    
    def action_receive(self):
        """Marca una línea como recibida"""
        self.ensure_one()
        if self.transfer_id.state != 'ready':
            raise UserError(_('The transfer must be in state "Ready to receive".'))
        
        self.write({
            'receive_state': 'received',
            'received_date': fields.Datetime.now(),
            'received_by': self.env.user.id
        })
        
        # Verificar si todas las líneas han sido recibidas
        all_received = all(line.receive_state == 'received' for line in self.transfer_id.transfer_line_ids)
        if all_received:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Completed'),
                    'message': _('Todos los equipos han sido recibidos. Puede finalizar la transferencia.'),
                    'sticky': False,
                    'type': 'success',
                }
            }
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Device Received'),
                'message': _('Device %s marcado como recibido.') % self.repair_order_id.name,
                'sticky': False,
                'type': 'success',
            }
        }
    
    @api.constrains('repair_order_id', 'transfer_id')
    def _check_duplicate_repair_order(self):
        for line in self:
            duplicate = self.search([
                ('transfer_id', '=', line.transfer_id.id),
                ('repair_order_id', '=', line.repair_order_id.id),
                ('id', '!=', line.id)
            ], limit=1)
            if duplicate:
                raise ValidationError(_('Device %s is already part of this transfer.') % line.repair_order_id.name)

    @api.onchange('repair_order_id')
    def _onchange_repair_order_id(self):
        if self.repair_order_id:
            # Check que el equipo esté en la ubicación de origen
            if self.repair_order_id.branch_id.id != self.transfer_id.location_origin_id.id:
                warning = {
                    'title': _('Advertencia'),
                    'message': _('The selected device is not at the source branch.')
                }
                self.repair_order_id = False
                return {'warning': warning}
                
    @api.model_create_multi
    def create(self, vals_list):
        # Check que el equipo esté en la ubicación de origen
        for vals in vals_list:
            if vals.get('repair_order_id') and vals.get('transfer_id'):
                transfer = self.env['internal.transfer'].browse(vals['transfer_id'])
                repair_order = self.env['repair.order'].browse(vals['repair_order_id'])
                if repair_order.branch_id.id != transfer.location_origin_id.id:
                    raise ValidationError(_('Device %s is not at the source branch %s.') %
                                         (repair_order.name, transfer.location_origin_id.name))
        return super().create(vals_list)

class BarcodeScanWizard(models.TransientModel):
    _name = 'barcode.scan.wizard'
    _description = 'Barcode scanning wizard'
    
    transfer_id = fields.Many2one('internal.transfer', string='Transferencia')
    barcode = fields.Char('Barcode', help='Scan or type the device barcode')
    message = fields.Char('Mensaje', readonly=True)
    
    @api.onchange('barcode')
    def _onchange_barcode(self):
        if self.barcode:
            # Buscar la orden de reparación por código de barras, IMEI o nombre
            repair_order = self.env['repair.order'].search([
                '|', '|',
                ('name', '=', self.barcode),
                ('imei', '=', self.barcode),
                ('serial', '=', self.barcode)
            ], limit=1)
            
            if repair_order:
                # Verificar si el equipo está en la ubicación de origen
                if repair_order.branch_id.id != self.transfer_id.location_origin_id.id:
                    self.message = _('Device %s is not at the source branch %s.') % (repair_order.name, self.transfer_id.location_origin_id.name)
                    return
                
                # Verificar si el equipo ya está en la transferencia
                duplicate = self.env['internal.transfer.line'].search([
                    ('transfer_id', '=', self.transfer_id.id),
                    ('repair_order_id', '=', repair_order.id)
                ], limit=1)
                
                if duplicate:
                    self.message = _('Device %s is already part of this transfer.') % repair_order.name
                    return
                
                # Add el equipo a la transferencia
                self.env['internal.transfer.line'].create({
                    'transfer_id': self.transfer_id.id,
                    'repair_order_id': repair_order.id,
                    'quantity': 1
                })
                
                self.message = _('Device %s added to the transfer.') % repair_order.name
                self.barcode = False
            else:
                self.message = _('No device found with code %s.') % self.barcode

class BarcodeReceiveWizard(models.TransientModel):
    _name = 'barcode.receive.wizard'
    _description = 'Device reception wizard'
    
    transfer_id = fields.Many2one('internal.transfer', string='Transferencia')
    barcode = fields.Char('Barcode', help='Scan or type the barcode of the device or the transfer')
    message = fields.Char('Mensaje', readonly=True)
    state = fields.Selection([
        ('transfer', 'Escanear Transferencia'),
        ('items', 'Escanear Devices')
    ], string='State', default='transfer')
    transfer_scanned = fields.Boolean('Transferencia Escaneada', default=False)
    items_received = fields.Integer('Devices Receiveds', default=0, readonly=True)
    items_total = fields.Integer('Total devices', compute='_compute_items_total')
    
    @api.depends('transfer_id')
    def _compute_items_total(self):
        for wizard in self:
            wizard.items_total = len(wizard.transfer_id.transfer_line_ids) if wizard.transfer_id else 0
    
    @api.onchange('barcode')
    def _onchange_barcode(self):
        if not self.barcode:
            return
            
        # Si estamos en el estado de escanear la transferencia
        if self.state == 'transfer':
            # Verificar si el código corresponde a la transferencia actual
            if self.barcode == self.transfer_id.name:
                self.transfer_scanned = True
                self.state = 'items'
                self.message = _('Transfer %s verified. Now scan the devices.') % self.transfer_id.name
                self.barcode = False
                return
            else:
                # Buscar si es otra transferencia
                transfer = self.env['internal.transfer'].search([('name', '=', self.barcode)], limit=1)
                if transfer:
                    self.message = _('Ha escaneado la transferencia %s, pero la transferencia actual es %s. Por favor, escanee la transferencia correcta.') % (self.barcode, self.transfer_id.name)
                else:
                    self.message = _('El código %s no corresponde a la transferencia %s. Por favor, escanee la transferencia correcta.') % (self.barcode, self.transfer_id.name)
                self.barcode = False
                return
        
        # Si estamos en el estado de escanear equipos
        elif self.state == 'items':
            # Buscar la línea de transferencia con el equipo correspondiente
            repair_order = self.env['repair.order'].search([
                '|', '|',
                ('name', '=', self.barcode),
                ('imei', '=', self.barcode),
                ('serial', '=', self.barcode)
            ], limit=1)
            
            if repair_order:
                # Buscar en las líneas de la transferencia
                transfer_line = self.env['internal.transfer.line'].search([
                    ('transfer_id', '=', self.transfer_id.id),
                    ('repair_order_id', '=', repair_order.id)
                ], limit=1)
                
                if transfer_line:
                    if transfer_line.receive_state == 'received':
                        self.message = _('Device %s was already received.') % repair_order.name
                    else:
                        # Marcar el equipo como recibido
                        transfer_line.action_receive()
                        self.items_received += 1
                        self.message = _('Device %s marked as received (%s of %s).') % (
                            repair_order.name, 
                            self.items_received, 
                            self.items_total
                        )
                else:
                    self.message = _('Device %s is not part of this transfer.') % repair_order.name
            else:
                self.message = _('No device found with code %s.') % self.barcode
            
            self.barcode = False