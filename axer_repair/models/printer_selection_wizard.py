# -*- coding: utf-8 -*-
"""Elección de impresora antes de imprimir una reparación."""

import logging

from odoo import _, api, fields, models

_logger = logging.getLogger(__name__)


class PrinterSelectionWizard(models.TransientModel):
    _name = 'repair.printer.selection.wizard'
    _description = 'Printer selection'

    printer_type = fields.Selection([
        ('label', 'Label'),
        ('receipt', 'Receipt'),
        ('both', 'Both'),
    ], string='What to print', required=True, default='both')

    printer_location = fields.Selection([
        ('current_branch', 'Branch of the repair'),
        ('other_branch', 'Another branch'),
        ('custom', 'Enter the printer'),
    ], string='Where to print', required=True, default='current_branch')

    branch_id = fields.Many2one(
        'repair.location', string='Branch',
        help='Branch whose printers will be used.')

    custom_cups_server_ip = fields.Char('CUPS server')
    custom_label_printer = fields.Char('Label printer')
    custom_receipt_printer = fields.Char('Receipt printer')

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        reparacion = self._reparacion()
        if reparacion and reparacion.branch_id:
            sucursal = reparacion.branch_id
            res.update({
                'branch_id': sucursal.id,
                'custom_cups_server_ip': sucursal.cups_server_ip or '',
                'custom_label_printer': sucursal.printer_name or '',
                'custom_receipt_printer': sucursal.receipt_printer_name or '',
            })
        return res

    def _reparacion(self):
        """Reparación desde la que se abrió el asistente."""
        repair_id = self.env.context.get('active_id')
        return self.env['repair.order'].browse(repair_id) if repair_id else self.env['repair.order']

    @api.onchange('branch_id')
    def _onchange_branch_id(self):
        if self.branch_id:
            self.custom_cups_server_ip = self.branch_id.cups_server_ip or ''
            self.custom_label_printer = self.branch_id.printer_name or ''
            self.custom_receipt_printer = self.branch_id.receipt_printer_name or ''

    def _impresoras(self, reparacion):
        """Devuelve (servidor, impresora de etiquetas, impresora de recibos)."""
        if self.printer_location == 'current_branch':
            sucursal = reparacion.branch_id
        elif self.printer_location == 'other_branch':
            sucursal = self.branch_id
        else:
            return (self.custom_cups_server_ip or '',
                    self.custom_label_printer or '',
                    self.custom_receipt_printer or '')
        return (sucursal.cups_server_ip or '',
                sucursal.printer_name or '',
                sucursal.receipt_printer_name or '')

    def action_print(self):
        self.ensure_one()
        reparacion = self._reparacion()
        if not reparacion:
            return {'type': 'ir.actions.act_window_close'}

        servidor, etiqueta, recibo = self._impresoras(reparacion)
        impresion = self.env['repair.printing']
        hay_cups = impresion._cups_disponible()
        resultado = None

        if self.printer_type in ('label', 'both'):
            resultado = impresion.imprimir(
                'axer_repair.action_report_repair_order4', reparacion,
                impresora=etiqueta, servidor=servidor)
        if self.printer_type in ('receipt', 'both'):
            recibo_res = impresion.imprimir(
                'axer_repair.action_report_repair_order', reparacion,
                impresora=recibo, servidor=servidor)
            # Sin CUPS solo puede descargarse un documento a la vez; con
            # 'Both' se ofrece el recibo, que es el que se entrega al cliente.
            if not hay_cups or self.printer_type == 'receipt':
                resultado = recibo_res

        # Cuando no hay impresora, 'imprimir' devuelve la acción de descarga
        # del PDF; se propaga para que el usuario lo imprima desde el navegador.
        if isinstance(resultado, dict):
            return resultado
        return {'type': 'ir.actions.act_window_close'}
