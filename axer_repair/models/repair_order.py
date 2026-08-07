# -*- coding: utf-8 -*-
import logging
import re
import subprocess
import time
from collections import defaultdict
from datetime import datetime, timedelta

import pytz
import requests
from babel.dates import format_datetime, get_day_names
from dateutil import parser

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError, UserError
from odoo.osv import expression

# La conexión con servicios externos (WhatsApp, firma, IA y el Odoo remoto)
# se hace a través del modelo 'repair.integration', que lee sus credenciales
# de Ajustes. Nunca se abre una conexión al importar el módulo.

_logger = logging.getLogger(__name__)

# Cómo ha llegado el cliente al taller. Se define una sola vez porque la
# usan tanto la reparación como el asistente de creación masiva.
ORIGENES_CLIENTE = [
    ('recomendacion', '👥 Word of mouth'),
    ('instagram', '📱 Instagram'),
    ('facebook', '📘 Facebook'),
    ('local', '🏪 Walk-in'),
    ('google maps', '📢 Google Maps'),
    ('tiktok', '📌 TikTok'),
    ('otro', '📝 Other'),
]



class RepairLocation(models.Model):
    _name = 'repair.location'
    _description = 'Repair branch'
    _inherit = ['mail.thread']

    name = fields.Char('Name', required=True, tracking=True)
    address = fields.Text('Address', tracking=True)
    phone = fields.Char('Phone', tracking=True)
    active = fields.Boolean('Active', default=True, tracking=True)
    printer_ip = fields.Char('Printer IP', tracking=True)
    cups_server_ip = fields.Char(
        'CUPS server',
        help="Address of the print server. If left empty, documents are downloaded as PDF instead of printed.")
    # 'printer_name' estaba declarado dos veces, y las dos con la impresora de
    # un taller concreto por defecto. Ahora es un solo campo y sin valor
    # previo: cada taller pone el nombre de su cola de CUPS.
    printer_name = fields.Char(
        'Label printer', tracking=True,
        help='Name of the CUPS queue, for example Brother_QL_810W.')
    receipt_printer_name = fields.Char(
        'Receipt printer', tracking=True,
        help='Name of the CUPS queue of the receipt printer.')

    repair_count = fields.Integer(
        string='Number of repairs',
        compute='_compute_repair_count'
    )

    @api.model
    def _sucursal_por_defecto(self):
        """Branch que se propone al crear una reparación.

        El módulo instala una ('Taller principal') para que este campo, que es
        obligatorio, nunca quede sin valor en una instalación recién hecha.
        """
        return self.search([], limit=1)

class ProductTemplate(models.Model):
    _inherit = 'product.template'

    manufacturer_id = fields.Many2one(
        related='product_variant_ids.manufacturer_id',
        string='Fabricante',
        store=True,
        readonly=False
    )
    model_code = fields.Char(
        related='product_variant_ids.model_code',
        string='Model code',
        store=True,
        readonly=False
    )


class ProductManufacturer(models.Model):
    _name = 'product.manufacturer'
    _description = 'Product manufacturer'

    name = fields.Char(string='Manufacturer name', required=True)
    country = fields.Char(string='Country of origin')  # Puedes añadir más campos según sea necesario

# Extender el modelo 'product.product' para agregar los campos 'manufacturer_id' y 'model_code'
class ProductProduct(models.Model):
    _inherit = 'product.product'

    manufacturer_id = fields.Many2one('product.manufacturer', string='Fabricante')
    model_code = fields.Char(string='Model code')  # Nuevo campo para almacenar el código del modelo


####buscar por imei en la base de datos de odoo####
class ResPartner(models.Model):
    _inherit = 'res.partner'
    
    # Este modelo lo usa Odoo entero: proveedores, empleados, bancos. El
    # módulo no le impone ni que el phone sea obligatorio ni que sea único
    # en toda la base — una empresa y su persona de contacto comparten número
    # a menudo, y una restricción global impediría guardarlos, además de no
    # poder crearse siquiera en instalaciones que ya tengan repetidos.
    # La comprobación se limita a los clientes del taller, que es donde el
    # phone se usa para localizar la reparación.


    def action_share_bulk_repair_portal(self):
        """Comparte el portal de reparaciones con el cliente por WhatsApp"""
        self.ensure_one()
        if not self.phone:
            raise UserError("The customer has no phone number on record.")
        
        # Asegurarse de que el cliente tenga un token
        token = self._generate_portal_token()
        
        # Generar URL del portal
        portal_url = self.get_portal_url()
        
        # Preparar el mensaje de WhatsApp
        phone_number = self.phone.replace(" ","").replace("-", "").replace("+", "")
        company_name = self.env.company.name
        message = f"""Hola {self.name},
        
    Puedes acceder al portal de seguimiento de tus reparaciones en {company_name} a través del siguiente enlace:
    {portal_url}

    Desde aquí podrás ver el estado de todas tus reparaciones en tiempo real.
    """
        
        # Enviar el mensaje por WhatsApp a través de la API
        try:
            url = self.env['repair.integration']._param('whatsapp_url')
            data = {
                "phone": phone_number,
                "message": message,
                "mediaUrl": ""
            }
            
            response = requests.post(url, json=data, timeout=20)
            response.raise_for_status()
            
            # Registrar que se ha compartido el enlace
            self.message_post(
                body=f"Se ha compartido el portal de reparaciones con el cliente por WhatsApp.",
                subject="Portal compartido"
            )
            
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Éxito',
                    'message': f'Se ha enviado el enlace del portal a {self.name} por WhatsApp.',
                    'type': 'success',
                    'sticky': False,
                }
            }
            
        except requests.exceptions.RequestException as e:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Error',
                    'message': f'No se pudo enviar el mensaje: {str(e)}',
                    'type': 'danger',
                    'sticky': True,
                }
            }

    ######normalizar el numero de telefono######
    @api.model
    def normalize_phone_numbers(self):
        partners = self.search([])
        _logger.info(f'Found {len(partners)} partners to normalize')
        for partner in partners:
            if partner.phone:
                _logger.info(f'Normalizing phone for partner {partner.id}: {partner.phone}')
                normalized_phone = partner.phone.replace(" ","").replace("-", "").replace("+", "")
                _logger.info(f'Normalized phone: {normalized_phone}')
                partner.write({'phone': normalized_phone})
                _logger.info(f'Updated phone for partner {partner.id}')

    #########fin #####

    ####la forma que se grabe el telefono en la base de datos####

    def _rw_formato_telefono(self, telefono):
        """Deja el phone en el formato que espera la pasarela de WhatsApp:
        sólo dígitos y con prefijo internacional.

        El prefijo se toma del país del contacto, o del de la compañía si el
        contacto no tiene ninguno; así el módulo no depende de un país concreto.
        """
        if not telefono:
            return telefono
        limpio = "".join(c for c in telefono if c.isdigit())
        if not limpio:
            return telefono
        pais = self.country_id or self.env.company.country_id
        prefijo = str(pais.phone_code or "")
        if prefijo and not limpio.startswith(prefijo):
            limpio = prefijo + limpio
        return limpio

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('phone'):
                vals['phone'] = self._rw_formato_telefono(vals['phone'])
        return super().create(vals_list)

    def write(self, vals):
        if vals.get('phone'):
            vals['phone'] = self._rw_formato_telefono(vals['phone'])
        return super().write(vals)

    #####fin de la funcion de grabar el telefono en la base de datos####

    @api.model
    def merge_duplicate_contacts(self):
        _logger.info("Iniciando la fusión de contactos duplicados.")

        # Buscar contactos duplicados basados en el número de phone que no estén vinculados a un usuario
        self._cr.execute("""
            SELECT
                phone, COUNT(*)
            FROM
                res_partner
            WHERE
                user_id IS NULL
            GROUP BY
                phone
            HAVING
                COUNT(*) > 1
        """)
        duplicates = self._cr.fetchall()
        _logger.info(f"Se encontraron {len(duplicates)} grupos de contactos duplicados.")

        for phone, count in duplicates:
            _logger.info(f"Procesando duplicados para el phone: {phone}")

            # Encontrar todos los contactos duplicados que no estén vinculados a un usuario
            contacts = self.search([('phone', '=', phone), ('user_id', '=', False)])
            if len(contacts) < 2:
                _logger.warning(f"Menos de 2 contactos encontrados para el phone: {phone}. Saltando.")
                continue

            # Seleccionar el contacto principal
            main_contact = contacts[0]
            duplicate_contacts = contacts[1:]
            _logger.info(f"Seleccionado contacto principal ID: {main_contact.id} para el phone: {phone}")

            # Actualizar las relaciones de repair_order
            for contact in duplicate_contacts:
                self._cr.execute("""
                    UPDATE repair_order
                    SET partner_id = %s
                    WHERE partner_id = %s
                """, (main_contact.id, contact.id))
                _logger.info(f"Actualizada relación de repair_order para el contacto ID: {contact.id}")

            # Eliminar el número de phone de los contactos duplicados
            for contact in duplicate_contacts:
                contact.write({'phone': False})
                _logger.info(f"Eliminado número de phone del contacto ID: {contact.id}")

        _logger.info("Fusión de contactos duplicados completada.")
        return True
 
##################################funcion para conctaos dubplicados####################    

   

###Funcion para blouear duplicacion de contactos###



    # Longitud admitida por el estándar internacional E.164, para no atarse
    # a la numeración de un país concreto.
    _FORMATO_TELEFONO = re.compile(r'^\d{7,15}$')

    @api.constrains('phone', 'mobile')
    def _check_unique_phone_mobile(self):
        for record in self:
            # Solo se vigilan los clientes: en el resto de contactos de Odoo
            # el módulo no tiene por qué entrometerse.
            if not record.customer_rank:
                continue
            for campo, etiqueta in (('phone', _('phone')), ('mobile', _('mobile'))):
                valor = record[campo]
                if not valor:
                    continue
                if not self._FORMATO_TELEFONO.match(valor):
                    raise ValidationError(
                        _('El número de %s sólo puede contener dígitos, entre 7 y 15, '
                          'sin espacios ni símbolos (ej: 18092742666).') % etiqueta
                    )
                if self.search_count([(campo, '=', valor),
                                      ('id', '!=', record.id),
                                      ('customer_rank', '>', 0)]):
                    raise ValidationError(
                        _('Another customer already has that %s.') % etiqueta
                    )

    # Permite localizar al cliente escribiendo su phone en el buscador de
    # contactos. Desde Odoo 17 esto se declara así en lugar de reescribir
    # _name_search, cuya firma cambió.
    _rec_names_search = ['complete_name', 'email', 'ref', 'vat',
                         'company_registry', 'phone', 'mobile']


    def _generate_portal_token(self):
        """Genera un token seguro para acceso al portal"""
        self.ensure_one()
        # Usamos el mismo método que usa Odoo internamente para generar signup_token
        if not self.signup_token:
            # Generamos un token nuevo
            import uuid
            token = uuid.uuid4().hex
            self.signup_token = token
        return self.signup_token
    
    def get_portal_url(self):
        """Genera la URL para acceder al portal de reparaciones"""
        self.ensure_one()
        base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url')
        token = self._generate_portal_token()
        return f"{base_url}/repair/bulk/{self.id}/{token}"    

############Clase app###############

# En Odoo 17 el modelo 'repair.line' desapareció: las operaciones de una
# reparación son ahora movimientos de stock ('stock.move') accesibles desde
# repair.order.move_ids. La antigua clase Repairlines solo añadía campos que
# no se usaban en ninguna vista ni método, por lo que se ha eliminado.


class RepairP(models.Model):
    _inherit = 'repair.order'

    @api.model
    def _datos_taller(self, compania=None):
        """Workshop identity para recibos, etiquetas y avisos.

        El nombre, el logotipo y los datos de contacto salen de la ficha de la
        compañía; los enlaces propios, de Ajustes → Repair Workshop. Así
        el módulo no lleva dentro la marca de ningún taller concreto.
        """
        parametro = self.env['repair.integration']._param
        compania = compania or self.env.company
        return {
            'nombre': compania.name or '',
            'firma': parametro('message_signature') or compania.name or '',
            'garantia': parametro('warranty_url') or '',
            'comunidad': parametro('community_url') or '',
            'redes': parametro('social_url') or '',
            'dias_abandono': int(parametro('abandoned_days') or 0),
            'telefono': compania.phone or '',
            'web': compania.website or '',
            'correo': compania.email or '',
        }

    description = fields.Char(string='Description')
    imei = fields.Char(string='IMEI / Serial number')
    serial = fields.Char(string='Serial number')
    passcode = fields.Char(string='Unlock code')
    battery = fields.Integer(string='Battery (%)', help='Remaining battery life, as a percentage.')
    faceid = fields.Boolean(string='Face ID')
    wifi = fields.Boolean(string='Wifi')
    signal = fields.Boolean(string='Signal')
    screen = fields.Boolean(string='Screen')
    camera = fields.Boolean(string='Rear camera')
    speaker = fields.Boolean(string='Speaker')
    microphone = fields.Boolean(string='Microphone')
    charging = fields.Boolean(string='Charging')
    buttons = fields.Boolean(string='Buttons')
    touch = fields.Boolean(string='Touch')
    sim = fields.Boolean(string='SIM')
    sd = fields.Boolean(string='SD')
    camerafront = fields.Boolean(string='Front camera')
    truetone = fields.Boolean(string='True Tone')
    panic = fields.Boolean(string='Panic button')
    screw = fields.Boolean(string='Screws')
    earphone = fields.Boolean(string='Earpiece')
    flash = fields.Boolean(string='Flash')
    powerstate = fields.Boolean(string='Powers on')
    name2 = fields.Char(string='name3', related='name')
    olddata = fields.Char(compute="_compute_olddata", string='Legacy record')
    product_exist = fields.Char(compute="_apiproductexistexist", string='Product exists')
    cover = fields.Boolean(string='Back cover')
    accessories = fields.Boolean(string='Accessories')
    done = fields.Boolean(string='Hecho')
    bands = fields.Boolean(string='Strap')
    whatsapp_sent = fields.Boolean(string='WhatsApp sent')
    last_whatsapp_state = fields.Char(string="Last notified state", default="draft")

    statecell = fields.Selection(string="Device condition" ,
                                 selection=[('in', 'In'), ('out', 'Out')]    )    

    partner1_phone = fields.Char(string='Customer phone', related='partner_id.phone')
    company_phone = fields.Char(string='Company phone', related='company_id.phone')
    partner1_email = fields.Char(string='Customer email', related='company_id.email')
    company_name = fields.Char(string='Empresa', related='company_id.name')
    address = fields.Char(string='Address', related='company_id.street')
    website1 = fields.Char(string='Sitio web', related='company_id.website')
    condition = fields.Char(string='Device condition')
    classific = fields.Char(compute="_compute_classific", string='Classification')
    evaluation = fields.Char(compute="_compute_evaluation", string='Condition rating')
    send_api_whatsapp = fields.Char(compute="send_watsapp", string='Send WhatsApp')
    typerepair = fields.Selection([('cell', 'Mobile phone'),
                                   ('tablet', 'Tablet'),
                                   ('smartwatch', 'Smartwatch'),
                                   ('laptop', 'Laptop'),
                                    ], string='Device type', default="cell")
                                    
    sizewatch = fields.Selection([('38', '38mm'),
                                   ('40', '40mm'),
                                   ('41', '41mm'),
                                   ('42', '42mm'),
                                   ('44', '44mm'),
                                   ('45', '45mm'),
                                   ('49', '49mm'),
                                    ], string='Strap size', default="40")
    
    state = fields.Selection([
        ('draft', 'Quotation'),
        ('confirmed', 'Confirmed'),
        ('ready', 'Ready to Repair'),
        ('under_repair', 'Under Repair'),
        ('2binvoiced', 'To be Invoiced'),
        ('done', 'Repaired'),
        ('test', 'Test'),
        ('cancel', 'Cancelled'),
        ('handover', 'Handed over'),
        ('guarantee', 'Guarantee')],  string='Status',
        copy=False, default='draft', readonly=True, tracking=True,
        help="* The \'Draft\' status is used when a user is encoding a new and unconfirmed repair order.\n* The \'Confirmed\' status is used when a user confirms the repair order.\n* The \'Ready to Repair\' status is used to start to repairing, user can start repairing only after repair order is confirmed.\n* The \'Under Repair\' status is used when the repair is ongoing.\n* The \'To be Invoiced\' status is used to generate the invoice before or after repairing done.\n* The \'Done\' status is set when repairing is completed.\n* The \'Test\' status is used when the equipment is under test.\n* The \'Cancelled\' status is used when user cancel repair order.* The \'Handed over\' status is used when the equipment is delivered to the customer.\n* The \'Guarantee\' status is used when the equipment is under guarantee.\n")
    
    guarantee_limit = fields.Date('Warranty expiry')
    # En Odoo 17 'amount_total' desapareció de repair.order: la facturación
    # pasó al pedido de venta. Se recompone aquí para los avisos al cliente y
    # el documento de firma.
    amount_total = fields.Monetary(
        string='Total amount', currency_field='currency_id',
        compute='_compute_amount_total',
        help="Total of the linked sales order. If there is no order yet, the estimated quotation is used.")

    @api.depends('sale_order_id.amount_total', 'estimated_budget')
    def _compute_amount_total(self):
        for orden in self:
            orden.amount_total = (
                orden.sale_order_id.amount_total or orden.estimated_budget or 0.0)

    warranty_fields = fields.Integer('Warranty (days)', default=15,
        help='Days of warranty the workshop grants on the repair.')
    signing_urlshow = fields.Char(string="Signature link")
    progress_percentage = fields.Integer(string="Progress", compute='_compute_progress_percentage')
    full_description = fields.Text(string='Full description')
    complete_description = fields.Text(string='Full history')
    historia_check = fields.Boolean(string='Add history')
    ####crear field para saber el tiempo de respuesta de la reparacion
    create_date_w = fields.Datetime(string='Creation date', default=fields.Datetime.now, readonly=True)
    done_date_w = fields.Datetime(string='Completion date', readonly=True)
    # Los campos almacenados se calculan con permisos elevados; al compartir
    # método con uno no almacenado, hay que igualar 'compute_sudo' en ambos.
    elapsed_time_w = fields.Char(
        string='Elapsed time (hours)', compute='_compute_elapsed_time',
        compute_sudo=True, readonly=True)
    elapsed_time_hours = fields.Float(
        compute='_compute_elapsed_time', compute_sudo=True, store=True)
    amount_paid = fields.Float(string='Amount paid')
    ncf_invoice_related = fields.Char(string='Tax receipt')
    pos_created = fields.Datetime(string='Created in POS')
    pos_url = fields.Char(string='POS link')
    backglass = fields.Boolean(string='Back glass', help='Back glass problems')

        # Campos para rastrear origen y estados
    created_from_wizard = fields.Boolean(string='Created from bulk wizard', default=False)
    label_printed = fields.Boolean(string='Label printed', default=False)
    whatsapp_notification_sent = fields.Boolean(string='WhatsApp notification sent', default=False)



    lead_source = fields.Selection(
        ORIGENES_CLIENTE, string='How did you hear about us?', tracking=True, required=True, default='otro')


    estimated_budget = fields.Monetary(
    string='Estimated quotation',
    currency_field='currency_id',
    tracking=True
)
    # Estaba declarado pero nunca se rellenaba, así que los importes salían
    # sin símbolo y el recibo fallaba al formatear el presupuesto.
    currency_id = fields.Many2one(
        'res.currency', string='Currency',
        related='company_id.currency_id', readonly=True)
    branch_id = fields.Many2one(
        'repair.location', string='Branch',
        default=lambda self: self.env['repair.location']._sucursal_por_defecto())
    

###############para compatir el enlace de seguimiento por whatsapp######################
    def action_abrir_portal(self):
        """Abre en otra pestaña el seguimiento que ve el cliente."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_url',
            'url': self.get_portal_url(),
            'target': 'new',
        }

    def action_share_tracking_url(self):
        """Comparte el enlace de seguimiento con el cliente por WhatsApp"""
        self.ensure_one()
        if not self.partner_id or not self.partner_id.phone:
            raise UserError("The customer has no phone number on record.")
        
        # Asegurarse de que la reparación tenga un token
        access_token = self.get_access_token()
        
        # Generar URL de seguimiento
        tracking_url = self.get_portal_url()
        
        # Preparar el mensaje de WhatsApp
        phone_number = self.partner_id.phone.replace(" ","").replace("-", "").replace("+", "")
        product_name = self.product_id.name or "tu equipo"
        
        message = f"""Hola {self.partner_id.name},
        
    Puedes seguir el estado de tu reparación {self.name} ({product_name}) a través del siguiente enlace:
    {tracking_url}

    Desde aquí podrás ver todos los detalles y el progreso en tiempo real.
    """
        
        # Enviar el mensaje por WhatsApp a través de la API
        try:
            url = self.env['repair.integration']._param('whatsapp_url')
            data = {
                "phone": phone_number,
                "message": message,
                "mediaUrl": ""
            }
            
            response = requests.post(url, json=data, timeout=20)
            response.raise_for_status()
            
            # Registrar que se ha compartido el enlace
            self.message_post(
                body=f"Se ha compartido el enlace de seguimiento con el cliente por WhatsApp.",
                subject="Enlace compartido"
            )
            
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Éxito',
                    'message': f'Se ha enviado el enlace de seguimiento a {self.partner_id.name} por WhatsApp.',
                    'type': 'success',
                    'sticky': False,
                }
            }
            
        except requests.exceptions.RequestException as e:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Error',
                    'message': f'No se pudo enviar el mensaje: {str(e)}',
                    'type': 'danger',
                    'sticky': True,
                }
            }    
    #####convertir hora para que sea mas amigable es una prueba a ver como funciona 

 # Campo char para almacenar la selección del usuario
    schedule_date_str = fields.Char(string='Delivery date (picker)')
    
    # Campo datetime computado
    schedule_date = fields.Datetime(
        string='Delivery date',
        compute='_compute_schedule_date',
        store=True
    )

    @api.onchange('schedule_date_str')
    def _onchange_schedule_date_str(self):
        _logger.info(">>> ONCHANGE: El campo schedule_date_str cambió")
        _logger.info(f">>> ONCHANGE: Nuevo valor = {self.schedule_date_str}")
          # Forzar la actualización del campo computado
        self._compute_schedule_date()
        _logger.info(f">>> ONCHANGE: Después del compute, schedule_date = {self.schedule_date}")

        # Probar el formato amigable
        if self.schedule_date:
            friendly_date = self.friendly_date_format(self.schedule_date)
            _logger.info(f">>> ONCHANGE: Formato amigable = {friendly_date}")
            _logger.info(f">>> ONCHANGE: Zona horaria actual = {self.env.user.tz}")


    @api.depends('schedule_date_str')
    def _compute_schedule_date(self):
        _logger.info(">>> COMPUTE: Iniciando _compute_schedule_date")
        for record in self:
            _logger.info(f">>> COMPUTE: schedule_date_str = {record.schedule_date_str}")
            if record.schedule_date_str:
                try:
                    date_obj = datetime.strptime(record.schedule_date_str, '%Y-%m-%d %H:%M:%S')
                    _logger.info(f">>> COMPUTE: date_obj convertido = {date_obj}")
                    record.schedule_date = date_obj
                except ValueError as e:
                    _logger.error(f">>> ERROR: Error al convertir fecha: {str(e)}")
                    record.schedule_date = False
            else:
                record.schedule_date = False


##########fin de la logica 

    # Método para las estadísticas en el dashboard
    @api.model
    def get_source_statistics(self):
        self.env.cr.execute("""
            SELECT 
                lead_source,
                COUNT(*) as total,
                COUNT(*) filter (where state = 'done') as completed
            FROM repair_order
            WHERE create_date >= CURRENT_DATE - INTERVAL '30 days'
            GROUP BY lead_source
        """)
        return self.env.cr.dictfetchall()
    
    @api.model
    def action_update_missing_lead_sources(self):
        repairs_without_source = self.env['repair.order'].search([('lead_source', '=', False)])
        for repair in repairs_without_source:
            repair.write({'lead_source': 'otro'})
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Actualización Completada',
                'message': f'Se actualizaron {len(repairs_without_source)} órdenes',
                'type': 'success',
                'sticky': False,
            }
        }  

#######Funcion para consulta de imei por api y creacion de modelo auto #########

    @api.onchange('imei')
    def _onchange_imei(self):
        if self.imei:
            try:
                imei_formateado = self.formatear_imei(self.imei)
                if not self.es_imei_valido(imei_formateado):
                    _logger.warning("El IMEI ingresado no es válido. No se hará la consulta.")
                    return
            except UserError as e:
                _logger.warning(f"Error al formatear IMEI: {str(e)}")
                return

            # Hacemos la consulta a la API usando el servicio "demo" para obtener el nombre del producto
            resultado = None
            try:
                resultado = self._query_imei_info(imei_formateado, service="demo", format="beta")
                _logger.info(f"Resultado de la consulta IMEI: {resultado}")
            except UserError as e:
                _logger.warning(f"API no disponible o error durante la consulta: {str(e)}")
                # Continuar sin detener la operación

            if resultado and 'result' in resultado:
                product_description = resultado['result'].get('Model Name')
                manufacturer_name = resultado['result'].get('Manufacturer')
                model_code = resultado['result'].get('Model Code')
                _logger.info(f"Description del modelo: {product_description}, Fabricante: {manufacturer_name}, Model code: {model_code}")
                             # Buscar o crear el fabricante
                manufacturer = None
                if manufacturer_name:
                    manufacturer = self.env['product.manufacturer'].search([('name', '=', manufacturer_name)], limit=1)
                    if not manufacturer:
                        manufacturer = self.env['product.manufacturer'].create({
                            'name': manufacturer_name,
                            'country': 'Desconocido'  # Puedes modificar esto según los datos que tengas disponibles
                        })
                        _logger.info(f"Fabricante creado: {manufacturer.name}")

                if product_description:
                    # Buscar si el producto ya existe
                    product = self.env['product.product'].search([('name', '=', product_description)], limit=1)

                    if not product:
                        # Si no existe, creamos el producto y asignamos el fabricante y el código del modelo
                        product = self.env['product.product'].create({
                            'name': product_description,
                            'type': 'product',
                            'categ_id': self.env.ref('product.product_category_all').id,
                            'manufacturer_id': manufacturer.id if manufacturer else False,
                            'model_code': model_code or "Desconocido",  # Guardar el código del modelo
                        })
                        _logger.info(f"Producto creado: {product.name} con fabricante: {manufacturer_name} y código del modelo: {model_code}")


                    self.product_id = product.id
                else:
                    _logger.info(f"No se encontró descripción del modelo en la respuesta para IMEI {self.imei}")
            else:
                _logger.warning(f"No se pudo obtener información del IMEI: {self.imei} o no hubo respuesta válida")

#353967815610269

    def formatear_imei(self, imei):
        match = re.search(r'\d{14,15}', imei)
        if match:
            imei = match.group(0)
            if len(imei) == 15:
                return imei
            else:
                raise UserError("The IMEI must be 15 digits long.")
        else:
            raise UserError("No valid IMEI or MEID was found in the text provided.")



    def es_imei_valido(self, imei):
        if len(imei) != 15 or not imei.isdigit():
            return False

        suma_total = 0
        for i in range(len(imei)):
            digito = int(imei[-(i + 1)])  # Empezamos desde la derecha
            if i % 2 == 1:
                digito *= 2
                if digito > 9:
                    digito -= 9
            suma_total += digito

        return suma_total % 10 == 0


    def _query_imei_info(self, imei, service, format):
        integracion = self.env['repair.integration']
        if not integracion._activo('imei'):
            raise UserError(_(
                "La consulta de IMEI no está activada. Configúrala en "
                "Ajustes → Repair Workshop."))
        api_key = integracion._param('imei_key')
        api_url = integracion._param('imei_url') or "https://sickw.com/api.php"
        if not api_key:
            raise UserError(_("The IMEI service API key is missing."))

        params = {
            "format": format,
            "key": api_key,
            "imei": imei,
            "service": service
        }

        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.3',
                'Accept-Language': 'en-US,en;q=0.8',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            }
            response = requests.get(api_url, params=params, headers=headers, timeout=20)
            if response.status_code == 200:
                data = response.json()
                return data
            else:
                raise UserError(f"Error al consultar el IMEI: {response.status_code} - {response.text}")

        except requests.exceptions.RequestException as e:
            raise UserError(f"Error al consultar el IMEI: {str(e)}")


    def button_query_imei_service_103(self):
        if self.imei:
            try:
                imei_formateado = self.formatear_imei(self.imei)
            except UserError as e:
                _logger.warning(f"Error al formatear IMEI: {str(e)}")
                return

            # Hacemos la consulta usando el servicio "103"
            resultado = None
            try:
                resultado = self._query_imei_info(imei_formateado, service="103", format="json")
            except UserError as e:
                _logger.warning(f"API no disponible o error durante la consulta: {str(e)}")
                return

            if resultado:
                # Formateamos el resultado para publicarlo en el chatter
              
                self.message_post(body=f"Resultado de la consulta IMEI (Servicio 103): {resultado}", subtype_xmlid="mail.mt_comment")
               
            else:
                _logger.warning("No se pudo obtener información para el IMEI usando el servicio 103.")



                            # Hacemos la consulta usando el servicio "103"
                            # Hacemos la consulta usando el servicio "103"



#####NUeva funcion para eleigir donde imprimir por boton ####   
# En el modelo repair.order existente, añade estos métodos

    def action_print_select_printer(self):
        """Abre el wizard para seleccionar impresora"""
        return {
            'name': 'Select printer',
            'type': 'ir.actions.act_window',
            'res_model': 'repair.printer.selection.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'active_id': self.id}
        }

    def print_label(self):
        """Imprime la etiqueta del equipo."""
        self.ensure_one()
        sucursal = self.branch_id
        return self.env["repair.printing"].imprimir(
            "axer_repair.action_report_repair_order4", self,
            impresora=self.env.context.get("printer_name") or sucursal.printer_name,
            servidor=self.env.context.get("cups_server_ip") or sucursal.cups_server_ip,
        )

    def print_receipt(self):
        """Imprime el recibo de entrada for the customer."""
        self.ensure_one()
        sucursal = self.branch_id
        return self.env["repair.printing"].imprimir(
            "axer_repair.action_report_repair_order", self,
            impresora=self.env.context.get("printer_name") or sucursal.receipt_printer_name,
            servidor=self.env.context.get("cups_server_ip") or sucursal.cups_server_ip,
        )


    # funcion para acceso al portal con token
    
    def generate_tokens_for_existing_repairs(self):
        """Genera tokens de acceso para reparaciones existentes que no tienen uno"""
        repairs_without_token = self.env['repair.order'].search([
            '|',
            ('access_token', '=', False),
            ('access_token', '=', '')
        ])
        
        count = 0
        for repair in repairs_without_token:
            repair.get_access_token()  # Esto generará y asignará un token
            count += 1
            
            # Opcional: Procesar en lotes para evitar problemas de memoria
            if count % 100 == 0:
                self.env.cr.commit()
                
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Tokens generados',
                'message': f'Se han generado tokens para {count} reparaciones',
                'type': 'success',
            }
        }


    @api.model_create_multi
    def create(self, vals_list):
        """Genera el token de acceso al portal de cada nueva reparación."""
        registros = super().create(vals_list)
        for registro in registros:
            registro.get_access_token()
        return registros

    access_token = fields.Char('Access token', copy=False, readonly=True)
    
    def _generate_access_token(self):
        """Genera un token seguro basado en UUID"""
        self.ensure_one()
        import uuid
        return uuid.uuid4().hex
    
    def get_access_token(self):
        """Obtiene o genera el token de acceso"""
        self.ensure_one()
        if not self.access_token:
            self.access_token = self._generate_access_token()
        return self.access_token
    
    def get_portal_url(self):
        """Retorna la URL para el seguimiento de esta reparación"""
        self.ensure_one()
        base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url')
        access_token = self.get_access_token()
        return f"{base_url}/repair/track/{self.id}/{access_token}"


##Fin de funcion #
##Fin de funcion #
    # Añade el campo branch_id
    def _print_simple_labels(self, repairs):
        """Imprime la etiqueta QR de cada reparación recién creada.

        Va en silencio: forma parte de un alta masiva y no debe interrumpirla
        si una impresora falla; el aviso queda en el registro.
        """
        impresion = self.env["repair.printing"]
        for reparacion in repairs:
            correcto = impresion.imprimir(
                "axer_repair.action_report_repair_order_qr_simple", reparacion,
                impresora=reparacion.branch_id.printer_name,
                servidor=reparacion.branch_id.cups_server_ip,
                silencioso=True)
            if correcto:
                reparacion.label_printed = True

    # ------------------------------------------------------------------
    def action_print_via_cups(self):
        """Imprime la etiqueta y, a continuación, el recibo."""
        self.ensure_one()
        self.print_label()
        return self.print_receipt()

    def action_print_via_cups_recepit(self):
        """Imprime solo el recibo."""
        return self.print_receipt()


    ####funcion para saber las ordernes de reparacion por usuario###
    def cron_publish_responsible_repair_points(self):
        # Obtener la fecha actual
        current_date = datetime.now()
        start_date = current_date.replace(day=1)  # Primer día del mes
        first_day_of_last_month = (start_date - timedelta(days=1)).replace(day=1)
        last_day_of_last_month = start_date - timedelta(days=1)
        end_date = current_date

        # Filtrar reparaciones por `state`, `user_id` y fecha de este mes
        repairs = self.env['repair.order'].search([
            ('state', 'in', ['done', 'handover']),
            ('user_id', '!=', False),
            ('create_date', '>=', first_day_of_last_month),
            ('create_date', '<=', last_day_of_last_month)
        ])

        # Crear un diccionario para almacenar los puntos por responsable
        points_per_user = defaultdict(lambda: {'repairs': 0, 'shared_repairs': 0, 'points': 0})

        
        

        for repair in repairs:
            responsible_user = repair.user_id
            collaborators = repair.user_ids 

            # Incrementar el conteo de reparaciones
            points_per_user[responsible_user]['repairs'] += 1 # Dividir entre colaboradores + responsable

            if collaborators:
            # Si hay colaboradores, se divide el punto entre el número de colaboradores
                points_per_user[responsible_user]['shared_repairs'] += 1
                total_participants = len(collaborators) + 1
                points_per_participant = 1 / total_participants
                points_per_user[responsible_user]['points'] += points_per_participant
                for collaborator in collaborators:
                    points_per_user[collaborator]['points'] += points_per_participant
            else:
            # Si no hay colaboradores, suma 1 punto
                points_per_user[responsible_user]['points'] += 1

        # Crear un mensaje con el resultado
        table_rows = []
        for user, data in points_per_user.items():
            repairs_count = data['repairs']
            shared_repairs_count = data['shared_repairs']
            points = data['points']
            division_of_points = len(collaborators) + 1 if collaborators else 1

            table_rows.append(f"""
                <tr>
                   <td>{user.name}</td>
                   <td>{repairs_count}</td>
                   <td>{shared_repairs_count}</td>
                   <td>{points:.2f}</td>
                   <td>{division_of_points}</td>
                </tr>
            """)

        table_html = f"""
            <table border="1" cellpadding="5" cellspacing="0">
               <tr>
                   <th>👤 Responsable</th>
                   <th>🔧 Repairs</th>
                   <th>🤝 Repairs Compartidas</th>
                   <th>⭐ Puntos</th>
                   <th>➗ División/puntos</th>
               </tr>
               {"".join(table_rows)}
            </table>
       """
        self._publish_message(table_html)

    def _publish_message(self, message):
        # Lógica para publicar el mensaje, por ejemplo en un canal de chatter
        channel = self.env['mail.channel'].search([('id', '=', '33')], limit=1)
        if channel:
              # Publicar el mensaje en el canal
           channel.message_post(
                 body=message,
                 subtype_xmlid="mail.mt_comment",
                 message_type="comment"
             )

   

   ##funcion para calcular el tiempo que tiene en la tienda el equipo##
    # Campo calculado para los días transcurridos
    days_elapsed = fields.Integer(string='Days elapsed', compute='_compute_days_elapsed', store=True)

    ###############fin de la creacion del campo####################

    @api.depends('create_date', 'done_date_w', 'state')
    def _compute_days_elapsed(self):
        """Days que el equipo lleva —o llevó— en el taller.

        Depender solo de 'create_date', que nunca cambia, dejaba el campo
        congelado en el cero del día del alta: como está almacenado, no se
        recalculaba nunca. Ahora se cierra con la fecha de finalización y, en
        las que siguen abiertas, lo refresca cada noche la tarea programada.
        """
        ahora = fields.Datetime.now()
        cerradas = ('done', 'handover', 'guarantee')
        for record in self:
            if not record.create_date:
                record.days_elapsed = 0
                continue
            fin = ahora
            if record.state in cerradas and record.done_date_w:
                fin = record.done_date_w
            # Nunca negativo: una fecha de finalización anterior a la de entrada
            # es un dato incoherente, no un número de días.
            record.days_elapsed = max(0, (fin - record.create_date).days)

    @api.model
    def cron_actualizar_dias_en_taller(self):
        """Refresca los días en taller de las reparaciones aún abiertas."""
        abiertas = self.search([
            ('state', 'not in', ('done', 'handover', 'guarantee', 'cancel')),
        ])
        if abiertas:
            self.env.add_to_compute(self._fields['days_elapsed'], abiertas)
            abiertas.flush_recordset(['days_elapsed'])
        _logger.info("Days in workshop actualizados en %d reparaciones", len(abiertas))
        return True
   


   #####Tarea que publica todas las reparaciones pendiente en el chatter########
    def cron_publish_pending_orders(self):
        # Obtener la fecha de inicio del mes actual
        today = datetime.today()
        start_of_month = today.replace(month=9, day=1)
        
        # Filtrar las órdenes en los estados deseados y creadas a partir del mes en curso
        orders = self.env['repair.order'].search([
            ('state', 'in', ['draft', 'under_repair', 'confirmed', 'ready', '2binvoiced']),
            ('create_date', '>=', start_of_month)
        ])
        
        if orders:
           # Inicializar el mensaje con un título claro
           message = "<b>📋 Órdenes Pendings, en Proceso, en Cotización y en Reparación:</b><br/><br/>"
        
           # Mapeo de los estados a sus títulos en el mensaje
           state_mapping = {
               'draft': "<b>🔹 Cotizacion:</b>",
               'under_repair': "<b>🔹 En Reparacion:</b>",
               'confirmed': "<b>🔹 Confirmed</b>",
               'ready': "<b>🔹 Listo:</b>",
               '2binvoiced': "<b>🔹 Para Facturacion:</b>",
           }

           # Construir el mensaje agrupando las órdenes por estado
           for state, header in state_mapping.items():
               filtered_orders = orders.filtered(lambda o: o.state == state)
               if filtered_orders:
                  message += f"{header}<br/>"
                  for order in filtered_orders:
                    # Añadir cada orden al mensaje con un formato claro
                    description_with_emoji = f"🛠️ {order.description or 'Sin descripción'}"
                    product_with_emoji = f"📱 {order.product_id.name}"
                    customer_with_emoji = f"👤 {order.partner_id.name}"
                    day_elapsed = f"🕒 {order.days_elapsed} días"
                    # Añadir cada orden al mensaje con un formato claro
                    message += f"- {order.name}: {description_with_emoji} - {product_with_emoji} - {customer_with_emoji} - {day_elapsed}<br/>"
                  message += "<br/>"  # Añadir un salto de línea entre secciones

          # Obtener el canal de difusión (reemplaza 'channel_name' con el nombre del canal)
           channel = self.env['mail.channel'].search([('id', '=', '32')], limit=1)
           if channel:
              # Publicar el mensaje en el canal
             channel.message_post(
                 body=message,
                 subtype_xmlid="mail.mt_comment",
                 message_type="comment"
             )



   ####fin de la tarea que publica todas las reparaciones pendiente en el chatter#####






    
    docuseal_document_id = fields.Char(string='Signature document')
    signature_status = fields.Selection([
        ('pending', 'Pending'),
        ('signed', 'Signed'),
        ('declined', 'Declined'),
    ], string='Signature status', default='pending')
    signed_by_client = fields.Many2one('res.partner', string='Signed by the customer')
    signed_date = fields.Datetime(string='Signature date')


    schedule_date = fields.Datetime(string='Delivery date', required=True)

    user_ids = fields.Many2many(
        'res.users',
        string='Collaborators',
        help='Collaborators who helped with the repair',
    )

    def action_repair_limited(self):
        """Fija el fin de la garantía al entregar: hoy más los días concedidos.

        No lleva @api.depends porque no es un campo calculado, sino una acción
        que se dispara desde action_repair_handover; el decorador no hacía
        nada. Se recorre el conjunto para que funcione con varias órdenes.
        """
        for orden in self:
            if orden.state == 'handover' and orden.warranty_fields:
                orden.guarantee_limit = fields.Date.today() + timedelta(
                    days=orden.warranty_fields)
        return True
    
    
    ####busqueda nueva por imei funcion original de odoo####
    @api.depends('imei', 'serial')
    def _compute_search_imei_serial(self):
        for record in self:
            record.search_imei_serial = record.id
            

    ###barra de progreso###
    
    @api.depends('state')
    def _compute_progress_percentage(self):
        state_progress_mapping = {
            'draft': 10,
            'confirmed': 20,
            'ready': 30,
            'under_repair': 50,
            'test': 70,
            '2binvoiced': 85,
            'done': 100,
            'handover': 100,
            'guarantee': 5,
            'cancel': 0
        }
        for order in self:
            order.progress_percentage = state_progress_mapping.get(order.state, 0)         


        

    @api.depends('faceid', 'wifi', 'signal', 'screen', 'camera', 'speaker', 'microphone', 'charging', 'buttons', 'touch', 'sim', 'sd', 'camerafront', 'panic', 'screw', 'earphone', 'flash')
    def _compute_evaluation(self):
        for record in self:
            # Lista de campos a evaluar con sus respectivos pesos
            fields_with_weights = {
                'faceid': 2,
                'wifi': 1,
                'signal': 1,
                'screen': 3,
                'camera': 2,
                'speaker': 1,
                'microphone': 1,
                'charging': 2,
                'buttons': 1,
                'touch': 2,
                'sim': 1,
                'sd': 1,
                'camerafront': 2,
                'panic': 1,
                'screw': 1,
                'earphone': 1,
                'flash': 1
            }
            
            total_weight = sum(fields_with_weights.values())
            score = 0
            
            for field, weight in fields_with_weights.items():
                if record[field]:
                    score += weight
            
            # Calcular la evaluación basada en el puntaje ponderado
            if score == total_weight:
                record.evaluation = "10/10 NITIDO"
            elif score >= total_weight * 0.8:
                record.evaluation = "8/10 BUENO"
            elif score >= total_weight * 0.6:
                record.evaluation = "5/10 ACEPTABLE"
            elif score >= total_weight * 0.4:
                record.evaluation = "3/10 REGULAR"
            elif score >= total_weight * 0.2:
                record.evaluation = "1/10 Malo"
            else:
                record.evaluation = "0/10 No probado"







 ######Funcion orginal confirmacion  que llama al metodo send_watsapp_update## 
    
    def action_repair_confirm(self):
        """Confirma la reparación y avisa al cliente.

        Delega la lógica en Odoo (_action_repair_confirm) y solo añade el
        aviso al cliente. En Odoo 17 desaparecieron 'fees_lines',
        'invoice_method' y el estado '2binvoiced'; las operaciones son ahora
        movimientos de stock en 'move_ids'.
        """
        if self.filtered(lambda repair: repair.state != 'draft'):
            raise UserError(_("Only draft repairs can be confirmed."))
        res = self._action_repair_confirm()
        self.send_watsapp_update()
        return res

   #############################################################
   #
   #
    def action_repair_start(self):
        """Pone la reparación en curso y avisa al cliente."""
        res = super().action_repair_start()
        self.send_watsapp_update()
        return res
    
    def action_repair_handover(self):
        """ Writes repair order state to 'Handed over'
        @return: True
        """
        if self.filtered(lambda repair: repair.state != 'done'):
            raise UserError(_("Repair must be done before handover."))
        self.write({'state': 'handover'})
        self.action_repair_limited()
        return self.send_watsapp_update()
    
    #############################################################
    def action_repair_guarantee(self):
        """ Writes repair order state to 'Guarantee'
        @return: True
        """
        self.write({'state': 'guarantee'})
        return self.send_watsapp_update()
       
   
#############################################################

    def action_repair_test(self):
        """ Writes repair order state to 'Test'
        @return: True
        """
        #    raise UserError(_("Repair must be done before testing."))
        self.write({'state': 'test'})
        return self.send_watsapp_update()



###crear un wizard para confirmar las funciones antes de cerrar la reparacion###
    def action_repair_end(self):
        return {
            'type': 'ir.actions.act_window',
            'name': 'Confirm Repair End',
            'res_model': 'repair.end.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_repair_id': self.id,
            }
        }
    


    def action_repair_end_confirmed(self):
        """Da por terminada la reparación y avisa al cliente.

        En Odoo 17 desaparecieron los campos 'repaired', 'invoice_id' e
        'invoice_method': la facturación se gestiona ahora con un pedido de
        venta ('sale_order_id'). Se delega en action_repair_end() de Odoo y
        aquí solo se añade el aviso al cliente.
        """
        # _check_product_tracking era de la 16; en la 17 las comprobaciones de
        # lote y de piezas incompletas las hace ya action_repair_end().
        self.write({'state': 'under_repair'})
        res = super().action_repair_end()
        self.send_watsapp_update()
        return res
    

###funcion crear wizard para capturar una notas antes de cancelar la reparacion###
    def action_repair_cancel(self):
        if any(repair.state == 'done' for repair in self):
            raise UserError(_("You cannot cancel a completed repair order."))
        
        # Abrir el asistente para ingresar la nota
        return {
            'type': 'ir.actions.act_window',
            'name': ('Repair Message'),
            'res_model': 'repair.message.wizard',
            'view_mode': 'form',
            'view_id': self.env.ref('axer_repair.repair_message_wizard').id,
            'target': 'new',
            'context': {
                'default_repair_id': self.id,
            },
        }

    def _cancel_repair_order(self, note):
        invoice_to_cancel = self.filtered(lambda repair: repair.invoice_id.state == 'draft').invoice_id
        if invoice_to_cancel:
            invoice_to_cancel.button_cancel()
        self.mapped('move_ids').write({'state': 'cancel'})
        self.write({'state': 'cancel'})
        # Enviar el mensaje por WhatsApp
        self.send_watsapp_update(note)
        return True
 
    


    @api.model
    def write(self, vals):
        old_user = self.user_id
        old_collaborators = self.user_ids
        old_state = self.state


        result = super(RepairP, self).write(vals)

        

        # Verificar si 'user_id' o 'user_ids' han cambiado
        if 'user_id' in vals or 'user_ids' in vals:
            new_user = self.user_id
            new_collaborators = self.user_ids

            # Obtener el grupo de técnicos de taller
            technician_group_id = self.env['res.groups'].browse(64)

            # Verificar si el nuevo usuario o colaboradores pertenecen al grupo de técnicos de taller
            #if new_user in technician_group_id.users or any(collab in technician_group_id.users for collab in new_collaborators):
            self._send_whatsapp_responsable(new_user, new_collaborators)
            self.write({'create_date_w': fields.Datetime.now()})
            
            

            # Notificar al nuevo responsable
            if new_user.partner_id:
                self.message_notify(
                    partner_ids=[new_user.partner_id.id],
                    body=f'Se te ha asignado un nuevo trabajo de {old_user.name} a {new_user.name}.',
                    subject='Nuevo trabajo asignado',
                    subtype_xmlid='mail.mt_comment'
                )

            # Notificar a los nuevos colaboradores
            for collaborator in new_collaborators:
                if collaborator.partner_id:
                    self.message_notify(
                        partner_ids=[collaborator.partner_id.id],
                        body=f'Se te ha asignado para colaborar en un trabajo asignado a {new_user.name}.',
                        subject='Colaboración en nuevo trabajo',
                        subtype_xmlid='mail.mt_comment'
                    )

        # Verificar si el estado ha cambiado de 'en reparacion' a 'done'
        if 'state' in vals and vals['state'] == 'done' and old_state == 'under_repair':
            new_user = self.user_id
            new_collaborators = self.user_ids
            technician_group_id = self.env['res.groups'].browse(64)
            self.write({'done_date_w': fields.Datetime.now()})

            # Verificar si el nuevo usuario pertenece al grupo de técnicos de taller
           # if new_user in technician_group_id.users:
            self._send_whatsapp_responsable_done(new_user, new_collaborators)

            # Enviar notificación por el chatter
            if new_user.partner_id:
                self.message_notify(
                    partner_ids=[new_user.partner_id.id],
                    body=f'¡Otro desafío superado! La reparación {self.name} ha sido finalizada. ¿Listo para el próximo?',
                    subject='Reparación finalizada',
                    subtype_xmlid='mail.mt_comment'
                )            

        return result


    @api.depends('create_date_w', 'done_date_w')
    def _compute_elapsed_time(self):
          for record in self:
            if record.create_date_w and record.done_date_w:
                delta = record.done_date_w - record.create_date_w
                seconds = delta.total_seconds()
                minutes, seconds = divmod(seconds, 60)
                hours, minutes = divmod(minutes, 60)
                days, hours = divmod(hours, 24)

                time_parts = []
                if days > 0:
                    time_parts.append(f"{int(days)} día{'s' if days > 1 else ''}")
                if hours > 0:
                    time_parts.append(f"{int(hours)} hora{'s' if hours > 1 else ''}")
                if minutes > 0:
                    time_parts.append(f"{int(minutes)} minuto{'s' if minutes > 1 else ''}")
                if seconds > 0 and not time_parts:
                    time_parts.append(f"{int(seconds)} segundo{'s' if seconds > 1 else ''}")

                record.elapsed_time_w = ', '.join(time_parts)
                record.elapsed_time_hours = delta.total_seconds() / 3600
            else:
                record.elapsed_time_w = '0 segundos'
                record.elapsed_time_hours = 0.0

    def _send_whatsapp_responsable_done(self, new_user, new_collaborators):
        url = self.env['repair.integration']._param('whatsapp_url')
        equipo = self.product_id.name
        falla = self.description
        entradano = self.name
        states = self.state

        # Formatear el tiempo transcurrido
        elapsed_time_hours = self.elapsed_time_hours
        if elapsed_time_hours < 1:
            elapsed_time_str = f"{elapsed_time_hours * 60:.0f} minutos"
        elif elapsed_time_hours < 24:
            elapsed_time_str = f"{elapsed_time_hours:.2f} horas"
        else:
            elapsed_time_days = elapsed_time_hours / 24
            elapsed_time_str = f"{elapsed_time_days:.2f} días"


        data = {
                "phone": new_user.phone,
                "message": f"""¡Otro desafío superado! La reparación {entradano} ha sido finalizada. 
                           en un tiempo: *{elapsed_time_str}* ¿Listo para el próximo?""",
                "mediaUrl": ""
             }
        self._send_whatsapp_message(data)

    def _send_whatsapp_responsable(self, new_user, collaborators):
        url = self.env['repair.integration']._param('whatsapp_url')
        equipo = self.product_id.name
        falla = self.description
        entradano = self.name
        states = self.state
        

    # Diccionario para los estados
        estados_dict = {
          'draft': 'Condition rating',
          'confirmed': 'Confirmed',
          'ready': 'Para Reparación',
          'done': 'Reparado'
        }

        estado_actual = estados_dict.get(states, 'Desconocido')

    # Mensaje para el responsable sobre un nuevo trabajo asignado
        message_responsable_nuevo_trabajo = f"""
         ¡Tienes un Desafío! Se te ha asignado un nuevo trabajo {entradano}.
         Revisa los detalles en la App. Se trata de un {equipo} 
         con un problema de {falla}. *¡Demuestra tus habilidades!* 
         State: {estado_actual}.
                   """

    # Mensaje para el responsable cuando se le asignan colaboradores
        message_responsable_con_colaborador = f"""
        Se te ha asignado un colaborador para que te ayude en tu trabajo {entradano}.
        Revisa los detalles en la App.
        """

    # Mensaje para los colaboradores
        message_colaborador = f"""
        ¡Estás asignado como colaborador! Se te ha asignado para ayudar en el trabajo {entradano}.
         El responsable principal es {new_user.name}. 
         Se trata de un {equipo} con un problema de {falla}.
         State: {estado_actual}.
          """

    # Enviar mensaje al responsable principal por nuevo trabajo
        if new_user.phone:
            data = {
            "phone": new_user.phone,
            "message": message_responsable_nuevo_trabajo,
            "mediaUrl": ""
           }
            self._send_whatsapp_message(data)

    # Enviar mensaje a los colaboradores
        if collaborators:
           for collaborator in collaborators:
               if collaborator.phone:
                  data = {
                    "phone": collaborator.phone,
                    "message": message_colaborador,
                    "mediaUrl": ""
                   }
                  self._send_whatsapp_message(data)

        # Enviar mensaje adicional al responsable informando sobre los colaboradores asignados
           if new_user.phone:
              data = {
                "phone": new_user.phone,
                "message": message_responsable_con_colaborador,
                "mediaUrl": ""
             }
              self._send_whatsapp_message(data)

    def _send_whatsapp_message(self, data):
        try:
           url = self.env['repair.integration']._param('whatsapp_url')
           response = requests.post(url, json=data, timeout=20)
           response.raise_for_status()
           self.send_api_whatsapp = response.status_code
        except requests.exceptions.HTTPError as http_err:
           _logger.debug(f"HTTP error occurred: {http_err} - Status Code: {response.status_code}")
        except requests.exceptions.ConnectionError:
           _logger.debug("Error connecting to the server. Please check your connection and the URL.")
        except requests.exceptions.Timeout:
           _logger.debug("The request timed out. Please try again later.")
        except Exception as err:
           _logger.debug(f"An error occurred: {err}")
            ################funcion para enviar mensaje de whatsapp a resposable################




    @api.constrains('sim')
    def _check_sim_for_raizer(self):
        if self.sim == False:
            raise ValidationError("Check that the device has no SIM or SD card before saving the repair order; if it has none, tick the No SIM box.")



##############Enviar un Quotation por whatsapp####################
    # @api.onchange('partner1_phone','typerepair','name2','imei','partner_id','product_id.name','description','name','state')
    def action_send_mail(self):
        if self.name != 'New' and self.whatsapp_sent == True:
         if self.state == self.last_whatsapp_state:
            url = self.env['repair.integration']._param('whatsapp_url')
            phone_number = self.partner1_phone.replace(" ","").replace("-", "").replace("+", "")
            equipo = self.product_id.name
            falla = self.description
            nombre = self.partner_id.name
            entradano = self.name
            states = self.state
            message = ""
    # Inicializar la variable para los nombres y precios de los productos
            products_message = ""
            for operation in self.move_ids:
                product_name = operation.name
                product_precio = operation.price_unit
        # Concatenar cada nombre y precio en la variable
                products_message += f"{product_name}   *RD$:{product_precio}*\n"
    # Construir el mensaje final incluyendo los nombres y precios de los productos
            amount_total = self.amount_total 
            if amount_total != 0:
                       message = f"""Hey, {nombre}
                       Este es el Quotation de la reparación de tu equipo *{equipo}*. 
                       DESCRIPCION:
                       {products_message}
                       El monto total a pagar es *RD$:{self.amount_total}*.
                       Por favor, confirma si esta deacuerdo.
        """
            data = {
                    "phone": phone_number,
                    "message": message,
                    "mediaUrl": "",

                }
            try:
                 response = requests.post(url, json=data, timeout=20)
                 response.raise_for_status()  # Esto lanzará un error si el código de estado es 4xx o 5xx
                 _logger.debug("Status Code", response.status_code)
                 _logger.debug(response.json())
                 self.send_api_whatsapp = response.status_code
                 self.whatsapp_sent = True
            except requests.exceptions.HTTPError as http_err:
    # Manejo de errores específicos de HTTP (e.g., respuestas 4xx, 5xx)
                _logger.debug(f"HTTP error occurred: {http_err} - Status Code: {response.status_code}")
            except requests.exceptions.ConnectionError:
    # Manejo de errores de conexión, por ejemplo, si no se puede alcanzar el servidor
                _logger.debug("Error connecting to the server. Please check your connection and the URL.")
            except requests.exceptions.Timeout:
    # Manejo de errores de tiempo de espera
                _logger.debug("The request timed out. Please try again later.")
            except Exception as err:
    # Manejo de cualquier otro tipo de error
                _logger.debug(f"An error occurred: {err}")               
                # Aquí iría el código para enviar el mensaje usando la API
                # Por ejemplo: response = requests.post(url, json=data, timeout=20)
         
#################Enviar un mensaje de agradecimiento por whatsapp####################

    def send_watsapp_thanks(self):
           
           
       if self.state == 'done' or self.state == 'cancel':
           #time.sleep(1 * 60)
           url = self.env['repair.integration']._param('whatsapp_url')
           phone_number = self.partner1_phone.replace("-", "").replace("+", "")
           nombre = self.partner_id.name
           taller = self._datos_taller(self.company_id)
           message = f"""Hey, {nombre}
           Gracias por visitar {taller['nombre']}. Esperamos que hayas tenido una excelente experiencia."""
           if taller['comunidad']:
               message += f"""
            Únete a nuestra comunidad de descuentos y promociones en *{taller['comunidad']}*"""
           states = self.state
           data = {
                    "phone": phone_number,
                    "message": message,
                    "mediaUrl": "https://media.giphy.com/media/v1.Y2lkPTc5MGI3NjExaXkyYXcxMDliNGE1aHlpaGhlYXhvYTV1aW5ydHU5bmlvaXdtZjdlaSZlcD12MV9pbnRlcm5hbF9naWZfYnlfaWQmY3Q9Zw/jpoDZOyEg38F4cFFMi/giphy.mp4",

                }
           

           try:
                 
                 response = requests.post(url, json=data, timeout=20)
                 response.raise_for_status()  # Esto lanzará un error si el código de estado es 4xx o 5xx
                 _logger.debug("Status Code", response.status_code)
                 _logger.debug(response.json())
                 self.send_api_whatsapp = response.status_code
                 self.whatsapp_sent = True
           except requests.exceptions.HTTPError as http_err:
    # Manejo de errores específicos de HTTP (e.g., respuestas 4xx, 5xx)
                _logger.debug(f"HTTP error occurred: {http_err} - Status Code: {response.status_code}")
           except requests.exceptions.ConnectionError:
    # Manejo de errores de conexión, por ejemplo, si no se puede alcanzar el servidor
                _logger.debug("Error connecting to the server. Please check your connection and the URL.")
           except requests.exceptions.Timeout:
    # Manejo de errores de tiempo de espera
                _logger.debug("The request timed out. Please try again later.")
           except Exception as err:
    # Manejo de cualquier otro tipo de error
                _logger.debug(f"An error occurred: {err}")               
                # Aquí iría el código para enviar el mensaje usando la API
                # Por ejemplo: response = requests.post(url, json=data, timeout=20)
 #############   



    def generate_signing_url(self, silencioso=False):
        """Pide al servicio de firma el enlace para que el cliente firme.

        Con 'silencioso' devuelve None en vez de avisar cuando la firma no
        está configurada: así los avisos automáticos siguen su curso aunque el
        taller no use firma digital.
        """
        self.ensure_one()
        integracion = self.env['repair.integration']
        base_firma = (integracion._param('signature_url') or '').rstrip('/')
        token_firma = integracion._param('signature_token')
        if not integracion._activo('signature') or not base_firma or not token_firma:
            if silencioso:
                return None
            raise UserError(_(
                "La firma digital no está configurada. Revísala en "
                "Ajustes → Repair Workshop."))

        nombre = self.partner_id.name
        montoconfirmado = self.amount_total
        entradano = self.name
        sigemail = self.partner_id.email if self.partner_id.email else f"{self.name}@{self.name}.com"
        urlfirma = base_firma + '/submissions/emails'
        payload = {
            "template_id": integracion._param('signature_template_id') or 1,
            "send_email": False,
             "submitters": [
                 {
                    "email": sigemail,
                    "fields": [
                       {
                           "name": 'nombre',
                           "default_value": nombre,
                           "readonly": "true"
                       },
                      { 
                           "name": 'entrada',
                           "default_value": entradano,
                           "readonly": "true"
                     },
                      {
                           "name": 'montocotizado',
                           "default_value": montoconfirmado,
                           "readonly": "true"
                       }
                  ]
               }
            ]
         }

        headers = {
            "X-Auth-Token": token_firma,
            "content-type": "application/json",
        }

        response = requests.post(urlfirma, json=payload, headers=headers, timeout=20)
        _logger.debug(response.text)

        if response.status_code == 200:
           response_json = response.json()
           if isinstance(response_json, list) and len(response_json) > 0:
               embed_src = response_json[0].get("embed_src")
               submission_id = response_json[0].get("submission_id")
               if embed_src and submission_id:
                  self.docuseal_document_id = submission_id
                  _logger.debug(f"Embed Source: {embed_src}")
                  return embed_src
               else:
                  _logger.debug("embed_src not found in the response.")
                  return None
           else:
              _logger.debug("Response JSON is not a list or is empty.")
              return None
        else:
            _logger.debug(f"Failed to generate signing URL. Status code: {response.status_code}")
            _logger.debug(response.text)
            return None



    ###confirma la firma del documento y envia un mensaje###
    def whatsapp_confirm(self):
        url = self.env['repair.integration']._param('whatsapp_url')
        phone_number = self.partner1_phone.replace(" ","").replace("-", "").replace("+", "")
        equipo = self.product_id.name
        falla = self.description
        nombre = self.partner_id.name
        entradano = self.name
        data = {
            "phone": phone_number,
            "message": f""" Tu equipo {equipo} con la entrada *#{entradano}* ha sido confirmado satisfactoriamente.
            Gracias por confiar en nosotros. Te mantedremos informado.
              """,
            "mediaUrl": "",
               }    
             # prueba de codigo para captura de errores
        try:
                 response = requests.post(url, json=data, timeout=20)
                 response.raise_for_status()  # Esto lanzará un error si el código de estado es 4xx o 5xx
                 _logger.debug("Status Code", response.status_code)
                 _logger.debug(response.json())
                 self.send_api_whatsapp = response.status_code
        except requests.exceptions.HTTPError as http_err:
    # Manejo de errores específicos de HTTP (e.g., respuestas 4xx, 5xx)
                _logger.debug(f"HTTP error occurred: {http_err} - Status Code: {response.status_code}")
        except requests.exceptions.ConnectionError:
    # Manejo de errores de conexión, por ejemplo, si no se puede alcanzar el servidor
                _logger.debug("Error connecting to the server. Please check your connection and the URL.")
        except requests.exceptions.Timeout:
    # Manejo de errores de tiempo de espera
                _logger.debug("The request timed out. Please try again later.")
        except Exception as err:
    # Manejo de cualquier otro tipo de error
                _logger.debug(f"An error occurred: {err}")        





 # Conversión entre UTC y la zona horaria del usuario que mira la pantalla
    def _convert_to_local_time(self, utc_dt):
        user_tz = self.env.user.tz or 'UTC'
        local_tz = pytz.timezone(user_tz)
        local_dt = pytz.utc.localize(utc_dt).astimezone(local_tz)
        return local_dt

    def _convert_to_utc_time(self, local_dt):
        user_tz = self.env.user.tz or 'UTC'
        local_tz = pytz.timezone(user_tz)
        utc_dt = local_tz.localize(local_dt).astimezone(pytz.utc)
        return utc_dt
    
    #################formato de fecha amigable####################s
    
    def friendly_date_format(self, date):
        if not date:
            return ''
        
        # No convertimos la fecha del usuario porque ya está en hora local
        local_date = date
        
        # Solo convertimos la hora actual del sistema
        now = self._convert_to_local_time(datetime.now())
        
        _logger.info(f"Fecha del usuario (ya en hora local): {local_date}")
        _logger.info(f"Hora actual convertida a local: {now}")
        
        # Formatear la hora manteniendo la original del usuario
        time_format = local_date.strftime('%I:%M %p').lstrip('0')
        time_format = time_format.replace('AM', 'am').replace('PM', 'pm')
        
        tomorrow = now + timedelta(days=1)
        end_of_week = now + timedelta(days=(6 - now.weekday()))
        day_names = get_day_names('wide', locale='es_ES')

        if local_date.date() == now.date():
            return f'hoy a las {time_format}'
        elif local_date.date() == tomorrow.date():
            return f'mañana a las {time_format}'
        elif local_date.date() <= end_of_week.date():
            day_name = day_names[local_date.weekday()]
            return f'el {day_name} a las {time_format}'
        else:
            day_name = day_names[local_date.weekday()]
            return f'el {day_name} {local_date.strftime("%d")} a las {time_format}'

    @api.onchange('partner1_phone','typerepair','name2','imei','partner_id','product_id.name','description','name','state')
    def send_watsapp_update(self, note=None):
        # Con los avisos desactivados no se prepara el mensaje ni se llama a
        # ningún servicio externo.
        if not self.env['repair.integration']._activo('whatsapp'):
            return
        if note is None:
            note = "."
        if self.state == self.last_whatsapp_state:
            return  # Si el estado no ha cambiado, no envíes el mensaje
            self.last_whatsapp_state = self.state 
        if self.state != 'draft' :
            taller = self._datos_taller(self.company_id)
            url = self.env['repair.integration']._param('whatsapp_url')
            phone_number = self.partner1_phone.replace(" ","").replace("-", "").replace("+", "")
            equipo = self.product_id.name
            falla = self.description
            nombre = self.partner_id.name
            entradano = self.name
            states = self.state
            message = ""
            #mediaUrl = ""
            if states == 'draft':
                states = 'Evaluacion'
                message = f"""Hola, {nombre}
                 Tu equipo {equipo} está en evaluación. Te informaremos pronto."""

            elif states == 'confirmed':
                 signing_url = self.generate_signing_url(silencioso=True) or ''
                 self.signing_urlshow = signing_url
                 amount_total = self.amount_total  # Asegúrate de que amount_total está definido en tu modelo
                 if amount_total != 0:
                    states = 'Confirmed'
                        # Inicializar la variable para los nombres y precios de los productos
                 products_message = ""
                 for operation in self.move_ids:
                     product_name = operation.product_id.display_name
                     product_precio = operation.product_id.lst_price
        # Concatenar cada nombre y precio en la variable
                     products_message += f"{product_name}   *RD$:{product_precio}*\n"
    # Construir el mensaje final incluyendo los nombres y precios de los productos
                     message =  f"""Hey, {nombre}
                       Este es el Quotation de la reparación de tu equipo *{equipo}*. 
                       DESCRIPCION:
                       {products_message}
                       El monto total a pagar es *RD$:{self.amount_total}*.
                       Por favor, confirma si esta deacuerdo click al siguiente enlace {signing_url} 
                       """


            elif states == 'under_repair':
                schedule_date_obj = fields.Datetime.from_string(self.schedule_date)
                friendly_date = self.friendly_date_format(schedule_date_obj)
                formatted_date = schedule_date_obj.strftime("%d/%m/%Y %H:%M")
                states = 'Para Reparacion'
                message = f"""Hey {nombre}
               Tu equipo {equipo} , con la entrada *#{entradano}* ya está en reparación. Con una fecha estimada de entrega,
                  {friendly_date} . Te Avisaremos cualquier novedad."""
            elif states == 'test':
                states = 'En Prueba'
                message = f"""Tu equipo *{equipo}* con la entrada *#{entradano}* está en prueba y revision . Te avisaremos cuando esté listo.""" 
            elif states == 'handover':
                states = 'Handed over'
                message = f"""Hey, {nombre}
                Tu equipo *{equipo}* con la entrada *#{entradano}* ha sido *Handed over* satisfactoriamente. Gracias por confiar en nosotros."""
                if taller['garantia']:
                    message += f"""
                Consulta nuestras políticas de garantía y devolución en *{taller['garantia']}*"""
                if taller['comunidad']:
                    message += f"""
                Accede a nuestras ofertas y promociones en *{taller['comunidad']}*"""     
            elif states == 'done':
                        states = 'Reparado'
                        amount_total = self.estimated_budget
                        if amount_total > 0:
                            importe = self.currency_id.symbol or ''
                            message = f"""Hey, {nombre}
                            Tu equipo *{equipo}* con la entrada *#{entradano}* ha sido *Reparado* satisfactoriamente. Puedes pasar a retirarlo.
                            El monto total a pagar es *{importe}{amount_total}*.
                            Gracias por confiar en nosotros."""
                            if taller['comunidad']:
                                message += f"""
                            Accede a nuestras ofertas y promociones en *{taller['comunidad']}*"""
                        else:
                            message = f"""Hey, {nombre}
                            Tu equipo *{equipo}* con la entrada *#{entradano}* ha sido *Reparado* satisfactoriamente.
                            Nuestro equipo técnico ha completado el servicio bajo garantía o acuerdo previo.
                            Puedes pasar a retirarlo cuando gustes."""
                            if taller['garantia']:
                                message += f"""
                            Más información sobre nuestras garantías en *{taller['garantia']}*"""
                            if taller['comunidad']:
                                message += f"""
                            Accede a nuestras ofertas y promociones en *{taller['comunidad']}*"""


            elif states == 'cancel':
                states = 'Cancelled'
                message = f"""Hey, {nombre}
                Lamentamos informarte que tu equipo *{equipo}* con la entrada *#{entradano}* no se ha podido reparar.
                Motivo: *{note}*."""
                if taller['redes']:
                    message += f"""
                Puedes ver los equipos que tenemos disponibles aquí: {taller['redes']}"""
                message += """
                Comunícate con nosotros para más información."""
               # urlmedia = "https://media.giphy.com/media/v1.Y2lkPTc5MGI3NjExaXkyYXcxMDliNGE1aHlpaGhlYXhvYTV1aW5ydHU5bmlvaXdtZjdlaSZlcD12MV9pbnRlcm5hbF9naWZfYnlfaWQmY3Q9Zw/jpoDZOyEg38F4cFFMi/giphy.mp4"    

              # Verifica si el mensaje no está vacío
            data = {
                    "phone": phone_number,
                    "message": message,
                    "mediaUrl": "",

                }
            
           
        
            try:
                 response = requests.post(url, json=data, timeout=20)
                 response.raise_for_status()  # Esto lanzará un error si el código de estado es 4xx o 5xx
                 _logger.debug("Status Code", response.status_code)
                 _logger.debug(response.json())
                 self.send_api_whatsapp = response.status_code
                 self.whatsapp_sent = True
            except requests.exceptions.HTTPError as http_err:
    # Manejo de errores específicos de HTTP (e.g., respuestas 4xx, 5xx)
                _logger.debug(f"HTTP error occurred: {http_err} - Status Code: {response.status_code}")
            except requests.exceptions.ConnectionError:
    # Manejo de errores de conexión, por ejemplo, si no se puede alcanzar el servidor
                _logger.debug("Error connecting to the server. Please check your connection and the URL.")
            except requests.exceptions.Timeout:
    # Manejo de errores de tiempo de espera
                _logger.debug("The request timed out. Please try again later.")
            except Exception as err:
    # Manejo de cualquier otro tipo de error
                _logger.debug(f"An error occurred: {err}")               
                # Aquí iría el código para enviar el mensaje usando la API
                # Por ejemplo: response = requests.post(url, json=data, timeout=20)
         



       ################################### 

   
    
    @api.onchange('partner1_phone','typerepair','name2','imei','partner_id','product_id.name','description','name','state')
    def send_watsapp(self):
        # Ojo: esto es el cálculo de 'send_api_whatsapp', así que leer la ficha
        # dispara el envío. El campo se asigna siempre, antes de cualquier
        # salida: si un cálculo no asigna su campo, Odoo aborta la lectura.
        self.send_api_whatsapp = 'OK'
        # Con los avisos desactivados no se llama a ninguna pasarela.
        if not self.env['repair.integration']._activo('whatsapp'):
            return
        
        # PRIMERA VERIFICACIÓN - NO PROCEDER SI:
        # - Orden creada desde wizard
        # - WhatsApp ya fue enviado
        # - La orden es nueva (name == 'New')
        # - No hay partner_id cargado todavía
        if (self.created_from_wizard or 
            self.whatsapp_sent == True or 
            self.name == 'New' or 
            not self.partner_id):
            return
        
        # SEGUNDA VERIFICACIÓN - EL TELÉFONO
        # Antes de intentar usar partner1_phone, debemos verificar su tipo
        if not hasattr(self, 'partner1_phone') or self.partner1_phone is False:
            return
            
        # AHORA ES SEGURO PROCESAR EL TELÉFONO
        try:
            # Solo tratar de usar replace si es una cadena
            if isinstance(self.partner1_phone, str):
                phone_number = self.partner1_phone.replace(" ","").replace("-", "").replace("+", "")
            else:
                # Si no es una cadena, convertirlo o usar una cadena vacía
                phone_number = str(self.partner1_phone) if self.partner1_phone else ""
                
            # No continuar si no hay número de phone útil
            if not phone_number:
                return
                
            # PROCEDER SOLO SI TENEMOS LOS DATOS BÁSICOS
            equipo = self.product_id.name if self.product_id else ""
            falla = self.description or ""
            nombre = self.partner_id.name
            entradano = self.name
            
            # INTENTAR CREAR EN LA API EXTERNA (OPCIONAL)
            try:
                self.send_parnert_api()
            except Exception:
                pass  # Ignorar errores en esta etapa
            
            # MENSAJE Y ENVÍO
            states = self.state
            if states == 'draft':
                states = 'Evaluacion'
            elif states == 'confirmed':
                states = 'Confirmed'
            elif states == 'ready':
                states = 'Par Reparacion'
            elif states == 'Done':
                states = 'Reparado'
                
            taller = self._datos_taller(self.company_id)
            contacto = " o ".join(filter(None, [taller['redes'], taller['telefono']])) or taller['nombre']
            url = self.env['repair.integration']._param('whatsapp_url')
            data = {
                "phone": phone_number,
                "message": f"""Hola, {nombre} \n
                
                ¡Gracias por elegirnos para reparar tu \n
                *{equipo}*!\n
                
                Queremos informarte que tu equipo, con la entrada \n 
                *#{entradano}*,\n  está en proceso\n *"{states}"*. La descripción del servicio es\n
                *"{falla}"*.\n
                
                Apreciamos tu preferencia y estamos comprometidos en devolverte tu dispositivo como nuevo!!.
                
                Si tienes alguna pregunta o necesitas más información,\n\n {contacto} no dudes en contactarnos.
                
                Saludos cordiales,
                *{taller['firma']}*
                """,
                "mediaUrl": "",
            }
            
            response = requests.post(url, json=data, timeout=20)
            self.send_api_whatsapp = response.status_code
            self.whatsapp_sent = True
            
            # IMPRIMIR SI ES NECESARIO
            if not self.env.context.get('skip_auto_print'):
                self.action_print_via_cups()
                
        except Exception as e:
            # Si hay cualquier error, simplemente salir sin hacer nada más
            _logger.error(f"Error en send_watsapp: {str(e)}")
            return



    @api.depends('typerepair')
    def _compute_classific(self):
        for record in self:
            if record.typerepair == "cell":
                record.classific = "C"
            elif record.typerepair == "tablet":
                record.classific = "T"
            elif record.typerepair == "smartwatch":
                record.classific = "S"
            else:
                record.classific = "A"
                              
            
    @api.depends('name2')
    def _compute_olddata(self):
        """Distingue las órdenes posteriores a la 318 de las importadas antes.

        Toma el número final de la referencia sea cual sea su prefijo: en la 17
        la secuencia es del tipo 'WH/RO/00005', y el corte fijo por posición que
        había antes rompía la lectura de cualquier orden.
        """
        for record in self:
            numero = re.search(r'(\d+)\s*$', record.name2 or '')
            record.olddata = "True" if numero and int(numero.group(1)) > 318 else "False"



    def _testconexion(self):
        """Indica si la sincronización con el Odoo externo está operativa."""
        integracion = self.env['repair.integration']
        if not integracion._activo('xmlrpc'):
            return 'False'
        return 'True' if integracion._xmlrpc_conectar() else 'False'

    @api.onchange('imei', 'name2', 'amount_total')
    def _apiproductexistexist(self):
        """Comprueba si el servicio ya existe en la otra base de datos.

        Sólo consulta: no crea nada, porque un onchange se dispara con cada
        pulsación y crearía registros duplicados en la otra instancia.
        """
        integracion = self.env['repair.integration']
        if not integracion._activo('xmlrpc'):
            self.product_exist = 'False'
            return
        if not self.name2 or self.name2 == 'New':
            self.product_exist = 'False'
            return
        encontrado = integracion.xmlrpc_execute(
            'product.template', 'search', [[['default_code', '=', self.name2]]]
        )
        self.product_exist = 'True' if encontrado else 'False'

    def send_parnert_api(self):
        """Copia el contacto de la reparación en el Odoo externo.

        Es una acción explícita, no un onchange: crear el contacto mientras el
        usuario teclea llenaba la otra base de datos de duplicados.
        """
        self.ensure_one()
        integracion = self.env['repair.integration']
        if not integracion._activo('xmlrpc'):
            raise UserError(_('Enable external synchronisation in '
                              'Ajustes → Repair Workshop.'))
        if not self.partner_id:
            raise UserError(_('The repair has no customer.'))
        existente = integracion.xmlrpc_execute(
            'res.partner', 'search', [[['phone', '=', self.partner_id.phone or '']]]
        ) if self.partner_id.phone else None
        if existente:
            return existente[0]
        return integracion.xmlrpc_execute('res.partner', 'create', [{
            'name': self.partner_id.name,
            'phone': self.partner_id.phone,
            'email': self.partner_id.email,
        }])

    def send_invoice_api(self):
        """Crea en el Odoo externo el servicio correspondiente a esta reparación."""
        self.ensure_one()
        integracion = self.env['repair.integration']
        if not integracion._activo('xmlrpc'):
            raise UserError(_('Enable external synchronisation in '
                              'Ajustes → Repair Workshop.'))
        if not self.name2 or self.name2 == 'New':
            raise UserError(_('The repair has no reference yet.'))
        if integracion.xmlrpc_execute(
                'product.template', 'search', [[['default_code', '=', self.name2]]]):
            self.product_exist = 'True'
            return False
        creado = integracion.xmlrpc_execute('product.template', 'create', [{
            'name': _('Tech service %s') % self.name2,
            'type': 'service',
            'barcode': (self.imei or '') + self.name2,
            'default_code': self.name2,
            'list_price': self.amount_total,
        }])
        self.product_exist = 'True' if creado else 'False'
        return creado

            
            

             
    



    
    
