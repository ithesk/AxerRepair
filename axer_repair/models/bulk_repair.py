# -*- coding: utf-8 -*-
from odoo import models, fields, api

from .repair_order import ORIGENES_CLIENTE
from odoo.exceptions import UserError
import re
import logging
import subprocess
import pytz

_logger = logging.getLogger(__name__)

class BulkRepairWizard(models.TransientModel):
    _name = 'bulk.repair.wizard'
    _description = 'Bulk repair creation wizard'

    partner_id = fields.Many2one('res.partner', string='Customer', required=True)
    branch_id = fields.Many2one(
        'repair.location', string='Branch', required=True,
        default=lambda self: self.env['repair.location']._sucursal_por_defecto())
    lead_source = fields.Selection(
        ORIGENES_CLIENTE, string='How did you hear about us?', default='local', required=True)
    
    # Campos para escaneo rápido
    quick_scan_imei = fields.Char(string='Quick IMEI/SN scan')
    default_equipment_type = fields.Selection([
        ('cell', 'Celular'),
        ('tablet', 'Tablet'),
        ('smartwatch', 'SmartWatch'),
    ], string='Default device type', default='cell')
    default_description = fields.Char(string='Problema predeterminado', default='Revisión general')
    bulk_scan_text = fields.Text(string='Bulk IMEI/SN scan', 
                             help='Paste several IMEI/SN here, separated by spaces, commas or line breaks')
    
    # Devices to repair
    repair_line_ids = fields.One2many('bulk.repair.line', 'wizard_id', string='Devices to repair')
    
    
    # Opciones adicionales
    auto_print_labels = fields.Boolean(string='Print labels automatically', default=True)
    auto_whatsapp = fields.Boolean(string='Send WhatsApp automatically', default=True)
    
    def action_quick_scan(self):
        """Añade un nuevo equipo a la lista usando el IMEI escaneado"""
        _logger.info(f"========== INICIANDO ACTION_QUICK_SCAN con IMEI: {self.quick_scan_imei} ==========")
        
        if not self.quick_scan_imei:
            _logger.warning("No se proporcionó IMEI/SN")
            raise UserError("Scan or type an IMEI/SN.")
        
        # Verificar si el IMEI ya existe en las líneas
        existing_line = self.repair_line_ids.filtered(lambda l: l.imei == self.quick_scan_imei)
        if existing_line:
            _logger.warning(f"IMEI duplicado: {self.quick_scan_imei}")
            raise UserError(f"Este IMEI/SN ({self.quick_scan_imei}) ya existe en la lista.")
        
        # Intentar buscar información del producto usando la API
        product_id = False
        try:
            repair_obj = self.env['repair.order']
            _logger.info(f"Obteniendo objeto repair.order: {repair_obj}")
            
            _logger.info(f"Formateando IMEI: {self.quick_scan_imei}")
            try:
                imei_formateado = repair_obj.formatear_imei(self.quick_scan_imei)
                _logger.info(f"IMEI formateado correctamente: {imei_formateado}")
            except Exception as e:
                _logger.error(f"Error al formatear IMEI: {str(e)}")
                _logger.error(f"Traceback completo:", exc_info=True)
                imei_formateado = self.quick_scan_imei
            
            _logger.info(f"Validando IMEI: {imei_formateado}")
            is_valid = False
            try:
                is_valid = repair_obj.es_imei_valido(imei_formateado)
                _logger.info(f"Resultado de validación de IMEI: {is_valid}")
            except Exception as e:
                _logger.error(f"Error al validar IMEI: {str(e)}")
                _logger.error(f"Traceback completo:", exc_info=True)
            
            if is_valid:
                _logger.info(f"IMEI válido, consultando API con parámetros: service=demo, format=beta")
                try:
                    resultado = repair_obj._query_imei_info(imei_formateado, service="demo", format="beta")
                    _logger.info(f"Respuesta API recibida: {resultado}")
                    
                    if resultado and 'result' in resultado:
                        _logger.info(f"Datos de resultado: {resultado['result']}")
                        product_description = resultado['result'].get('Model Name')
                        manufacturer_name = resultado['result'].get('Manufacturer')
                        _logger.info(f"Model encontrado: {product_description}, Fabricante: {manufacturer_name}")
                        
                        if product_description:
                            _logger.info(f"Buscando producto con nombre: {product_description}")
                            product = self.env['product.product'].search([('name', '=', product_description)], limit=1)
                            if product:
                                product_id = product.id
                                _logger.info(f"Producto encontrado en BD: {product.name} (ID: {product_id})")
                            else:
                                _logger.warning(f"Producto no encontrado en BD, intentando crear: {product_description}")
                                # Intentar crear el producto
                                try:
                                    # Buscar o crear el fabricante
                                    manufacturer = None
                                    if manufacturer_name:
                                        manufacturer = self.env['product.manufacturer'].search([('name', '=', manufacturer_name)], limit=1)
                                        if not manufacturer:
                                            manufacturer = self.env['product.manufacturer'].create({
                                                'name': manufacturer_name,
                                                'country': 'Desconocido'
                                            })
                                            _logger.info(f"Fabricante creado: {manufacturer.name}")
                                    
                                    # Crear el producto
                                    product = self.env['product.product'].create({
                                        'name': product_description,
                                        'type': 'product',
                                        'categ_id': self.env.ref('product.product_category_all').id,
                                        'manufacturer_id': manufacturer.id if manufacturer else False,
                                    })
                                    _logger.info(f"Producto creado: {product.name} (ID: {product.id})")
                                    product_id = product.id
                                except Exception as e:
                                    _logger.error(f"Error al crear producto: {str(e)}")
                                    _logger.error(f"Traceback completo:", exc_info=True)
                    else:
                        _logger.warning(f"API no devolvió información útil o formato incorrecto: {resultado}")
                except Exception as e:
                    _logger.error(f"Error al consultar API: {str(e)}")
                    _logger.error(f"Traceback completo:", exc_info=True)
            else:
                _logger.warning(f"IMEI no válido o no se pudo validar: {imei_formateado}")
        except Exception as e:
            _logger.error(f"Error general en el proceso: {str(e)}")
            _logger.error(f"Traceback completo:", exc_info=True)
        
        # Crear la nueva línea
        _logger.info(f"Creando línea con valores finales:")
        _logger.info(f"  - IMEI: {self.quick_scan_imei}")
        _logger.info(f"  - Tipo: {self.default_equipment_type}")
        _logger.info(f"  - Description: {self.default_description}")
        _logger.info(f"  - Producto ID: {product_id}")
        
        try:
            new_line = self.env['bulk.repair.line'].create({
                'wizard_id': self.id,
                'imei': self.quick_scan_imei,
                'equipment_type': self.default_equipment_type,
                'description': self.default_description,
                'product_id': product_id,
            })
            _logger.info(f"Línea creada correctamente: {new_line}")
        except Exception as e:
            _logger.error(f"Error al crear línea: {str(e)}")
            _logger.error(f"Traceback completo:", exc_info=True)
            raise UserError(f"Error al crear línea: {str(e)}")
        
        # Limpiar el campo para el siguiente escaneo
        _logger.info("Limpiando campo de escaneo para siguiente entrada")
        self.quick_scan_imei = False
        
        _logger.info("========== FINALIZANDO ACTION_QUICK_SCAN ==========")
        
        # Devolver una acción válida - recarga el formulario actual
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'bulk.repair.wizard',
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
            'flags': {'mode': 'edit'},
        }
        
    def action_create_repairs(self):
        """Procesa las líneas y crea las órdenes de reparación"""
        repairs_created = []
        
        if not self.repair_line_ids:
            raise UserError("Add at least one device to create repair orders.")
        
        # Verificar si todos los equipos tienen la casilla de SIM marcada
        lines_without_sim_check = self.repair_line_ids.filtered(lambda l: not l.sim)
        if lines_without_sim_check:
            # Crear una lista de IMEIs con la casilla sin marcar
            imeis_list = ", ".join([l.imei or "Sin IMEI" for l in lines_without_sim_check])
            raise UserError(f"Asegúrese de que los equipos no tengan SIM o tarjeta SD antes de continuar. "
                            f"Marque la casilla 'No SIM/SD' para los siguientes equipos: {imeis_list}")
        
        for line in self.repair_line_ids:
            if not line.imei and not line.serial:
                raise UserError("Every device needs an IMEI or serial number.")
            
            # Preparar valores para la orden de reparación
            repair_vals = {
                'partner_id': self.partner_id.id,
                'branch_id': self.branch_id.id,
                'lead_source': self.lead_source,
                'imei': line.imei,
                'serial': line.serial,
                'description': line.description,
                'condition': line.condition,
                'typerepair': line.equipment_type,
                'statecell': 'in',
                'product_id': line.product_id.id if line.product_id else False,
                
                # Establecer los valores booleanos basados en los problemas seleccionados
                'screen': 'screen' in line.repair_issues,
                'charging': 'charging' in line.repair_issues,
                'battery': 50 if 'battery' in line.repair_issues else 100,  # Valor arbitrario para batería
                'touch': 'touch' in line.repair_issues,
                'camera': 'camera' in line.repair_issues,
                'backglass': 'backglass' in line.repair_issues,
                'wifi': 'wifi' in line.repair_issues,
                'signal': 'signal' in line.repair_issues,
                'speaker': 'speaker' in line.repair_issues,
                'microphone': 'microphone' in line.repair_issues,
                'buttons': 'buttons' in line.repair_issues,
                'sim': True,
                'created_from_wizard': True,
                'whatsapp_sent': self.auto_whatsapp,  # Marcar como enviado si auto_whatsapp está activo
            }
            
            # Siempre evitamos la impresión automática y el envío de WhatsApp al crear
            # para manejarlos de forma centralizada después
            ctx = {'skip_auto_print': True, 'skip_whatsapp': True}
            repair = self.env['repair.order'].with_context(ctx).create(repair_vals)
            
            # Generar token de acceso
            repair.get_access_token()
            
            repairs_created.append(repair.id)
            
            _logger.info(f"Repair order creada: {repair.name} para IMEI/SN: {line.imei or line.serial}")
        
        # Obtener todas las órdenes creadas como recordset
        created_repairs = self.env['repair.order'].browse(repairs_created)
        
        # Tags: se delega en el servicio de impresión, que ya sabe qué
        # hacer si la sucursal no tiene impresora configurada.
        if self.auto_print_labels and created_repairs:
            created_repairs._print_simple_labels(created_repairs)

        # Si está marcada la opción de enviar WhatsApp automáticamente
        if self.auto_whatsapp and created_repairs:
            try:
                # Enviar un solo mensaje con acceso al portal
                self._send_portal_access_whatsapp(created_repairs)
            except Exception as e:
                _logger.error(f"Error al enviar WhatsApp con acceso al portal: {str(e)}")
        
        # Devolver acción para ver las órdenes creadas
        return {
            'name': 'Órdenes de reparación creadas',
            'type': 'ir.actions.act_window',
            'res_model': 'repair.order',
            'view_mode': 'tree,form',
            'domain': [('id', 'in', repairs_created)],
            'target': 'current',
        }

    def _send_portal_access_whatsapp(self, repairs):
        """Envía un solo mensaje de WhatsApp con el acceso al portal"""
        if not self.partner_id or not self.partner_id.phone:
            raise UserError("The customer has no phone number on record.")
        
        # Asegurarse de que el cliente tenga un token
        token = self.partner_id._generate_portal_token()
        
        # Generar URL del portal
        portal_url = self.partner_id.get_portal_url()
        
        # Obtener información sobre las reparaciones
        repair_count = len(repairs)
        repair_info = ""
        
        for repair in repairs:
            product_name = repair.product_id.name or "Device"
            description = repair.description or "Sin descripción"
            repair_info += f"• {product_name}: {description}\n"
        
        # Preparar el mensaje de WhatsApp
        phone_number = self.partner_id.phone.replace(" ","").replace("-", "").replace("+", "")
        company_name = self.env.company.name
        
        message = f"""Hola {self.partner_id.name},

    Hemos registrado {repair_count} {('equipo' if repair_count == 1 else 'equipos')} para reparación:

    {repair_info}
    Puedes seguir el estado de {('tu reparación' if repair_count == 1 else 'tus reparaciones')} en tiempo real a través del siguiente enlace:
    {portal_url}

    Gracias por confiar en {company_name}.
    """
        
        # Enviar mensaje por WhatsApp
        try:
            url = self.env['repair.integration']._param('whatsapp_url')
            data = {
                "phone": phone_number,
                "message": message,
                "mediaUrl": ""
            }
            
            import requests
            response = requests.post(url, json=data, timeout=20)
            response.raise_for_status()
            
            _logger.info(f"Mensaje de acceso al portal enviado a {self.partner_id.name}")
            
        except Exception as e:
            _logger.error(f"Error al enviar WhatsApp: {str(e)}")
            raise UserError(f"Error al enviar WhatsApp: {str(e)}")

    def action_scan_multiple(self):
        """Procesa múltiples IMEIs/SNs de una vez"""
        self.ensure_one()
        
        if not self.bulk_scan_text:
            raise UserError("Enter the IMEI/SN you want to process.")
        
        # Extraer todos los posibles IMEIs/SNs del texto
        # Dividimos por líneas, espacios y comas para ser flexibles
        lines = self.bulk_scan_text.split('\n')
        candidates = []
        
        for line in lines:
            # Dividir por comas o espacios
            items = re.split(r'[,\s]+', line)
            for item in items:
                item = item.strip()
                if item:  # Si no está vacío
                    candidates.append(item)
        
        if not candidates:
            raise UserError("No valid IMEI/SN was found in the text entered.")
        
        # Procesar cada candidato encontrado
        added_count = 0
        errors = []
        
        for candidate in candidates:
            try:
                # Verificar si ya existe en las líneas actuales
                existing_line = self.repair_line_ids.filtered(lambda l: l.imei == candidate)
                if existing_line:
                    errors.append(f"IMEI {candidate} ya existe en la lista")
                    continue
                
                # Intentar buscar información del producto usando el API
                product_id = False
                try:
                    # Intentamos formatear y validar el IMEI
                    repair_obj = self.env['repair.order']
                    imei_formateado = repair_obj.formatear_imei(candidate)
                    is_valid = repair_obj.es_imei_valido(imei_formateado)
                    
                    # Si es válido, consultamos la API
                    if is_valid:
                        resultado = repair_obj._query_imei_info(imei_formateado, service="demo", format="beta")
                        if resultado and 'result' in resultado:
                            product_description = resultado['result'].get('Model Name')
                            manufacturer_name = resultado['result'].get('Manufacturer')
                            
                            if product_description:
                                product = self.env['product.product'].search([('name', '=', product_description)], limit=1)
                                if product:
                                    product_id = product.id
                                else:
                                    # Intentar crear el producto
                                    manufacturer = None
                                    if manufacturer_name:
                                        manufacturer = self.env['product.manufacturer'].search([('name', '=', manufacturer_name)], limit=1)
                                        if not manufacturer:
                                            manufacturer = self.env['product.manufacturer'].create({
                                                'name': manufacturer_name,
                                                'country': 'Desconocido'
                                            })
                                    
                                    # Crear el producto
                                    product = self.env['product.product'].create({
                                        'name': product_description,
                                        'type': 'product',
                                        'categ_id': self.env.ref('product.product_category_all').id,
                                        'manufacturer_id': manufacturer.id if manufacturer else False,
                                    })
                                    product_id = product.id
                except Exception as e:
                    _logger.warning(f"Error al procesar IMEI con la API: {str(e)}")
                
                # Crear la línea
                self.env['bulk.repair.line'].create({
                    'wizard_id': self.id,
                    'imei': candidate,
                    'equipment_type': self.default_equipment_type,
                    'description': self.default_description,
                    'product_id': product_id,
                    'sim': True,  # Marcamos como predeterminado
                })
                added_count += 1
                
            except Exception as e:
                errors.append(f"Error al procesar IMEI {candidate}: {str(e)}")
        
        # Limpiar el campo después de procesarlo
        self.bulk_scan_text = False
        
        # Mensaje de resultado
        if added_count > 0:
            message = f"Se añadieron {added_count} equipos correctamente."
            if errors:
                message += f"\n\nErrores ({len(errors)}): {', '.join(errors)}"
            
            # Primero mostramos la notificación
            self.env['bus.bus']._sendone(self.env.user.partner_id, 'notification', {
                'type': 'success',
                'title': 'Procesamiento completado',
                'message': message,
                'sticky': True if errors else False,
            })
            
            # Luego recargamos el formulario para mostrar las líneas añadidas
            return {
                'type': 'ir.actions.act_window',
                'res_model': 'bulk.repair.wizard',
                'res_id': self.id,
                'view_mode': 'form',
                'target': 'new',
                'flags': {'mode': 'edit'},
            }
        else:
            error_msg = "No se pudo añadir ningún equipo."
            if errors:
                error_msg += f"\n\nErrores: {', '.join(errors)}"
            
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Error en el procesamiento',
                    'message': error_msg,
                    'sticky': True,
                    'type': 'danger',
                }
            }

class BulkRepairLine(models.TransientModel):
    _name = 'bulk.repair.line'
    _description = 'Bulk repair line'

    wizard_id = fields.Many2one('bulk.repair.wizard', string='Wizard principal')
    
    # Información del equipo
    imei = fields.Char(string='IMEI / Serial number', help='Scan or type the IMEI or serial number')
    serial = fields.Char(string='Serial number')
    equipment_type = fields.Selection([
        ('cell', 'Celular'),
        ('tablet', 'Tablet'),
        ('smartwatch', 'SmartWatch'),
    ], string='Device type', default='cell', required=True)
    
    description = fields.Char(string='Description', required=True)
    condition = fields.Char(string='Device condition')
    sim = fields.Boolean(string='No SIM/SD', help='Tick if the device was checked and has neither SIM nor SD card', default=True)
    
    # Common faults (usamos tags para selección múltiple)
    repair_issues = fields.Many2many(
        'repair.issue.tag', 
        string='Problemas a reparar',
        help='Select every fault the device shows'
    )
    
    # Producto relacionado (se llenará automáticamente al validar el IMEI)
    product_id = fields.Many2one('product.product', string='Model')
    
    # Validar IMEI y buscar información del producto
    @api.onchange('imei')
    def _onchange_imei(self):
        if self.imei:
            try:
                # Usar la misma lógica de validación que en RepairP
                repair_obj = self.env['repair.order']
                try:
                    imei_formateado = repair_obj.formatear_imei(self.imei)
                    if not repair_obj.es_imei_valido(imei_formateado):
                        return {'warning': {'title': 'IMEI no válido', 'message': 'El IMEI ingresado no cumple con el formato estándar o no es válido.'}}
                    
                    # Consultar información del producto usando el servicio "demo"
                    resultado = repair_obj._query_imei_info(imei_formateado, service="demo", format="beta")
                    
                    if resultado and 'result' in resultado:
                        product_description = resultado['result'].get('Model Name')
                        manufacturer_name = resultado['result'].get('Manufacturer')
                        
                        if product_description:
                            # Buscar si el producto ya existe
                            product = self.env['product.product'].search([('name', '=', product_description)], limit=1)
                            if product:
                                self.product_id = product.id
                                return {'info': {'title': 'Producto encontrado', 'message': f'Se encontró el modelo: {product_description}'}}
                except Exception as e:
                    _logger.warning(f"Error al procesar IMEI: {str(e)}")
                    pass
            except Exception as e:
                _logger.error(f"Error al procesar IMEI: {str(e)}")
                pass