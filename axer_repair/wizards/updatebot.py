import logging

from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.tools.translate import _

# La librería 'openai' es opcional: se importa dentro de 'repair.integration'
# solo cuando el asistente está activado, para que el módulo instale sin ella.

_logger = logging.getLogger(__name__)

INSTRUCCION_POR_DEFECTO = (
    "Eres un técnico de reparación con años de experiencia en microsoldadura. "
    "Explicas diagnósticos de forma clara a clientes sin conocimientos técnicos. "
    "Eres amable y escribes mensajes cortos."
)




class UpdateBotMessage(models.Model):
    _name = 'update.bot.message'
    _description = 'Update Bot Message'

    
    message = fields.Text(string='Message')
    repair_id = fields.Many2one('repair.order', string='Repair Order')
    customer_name = fields.Char(string='Customer Name', readonly=True)
    customer_phone = fields.Char(string='Customer Phone', readonly=True)
    customer_desc = fields.Char(string='Customer Description', readonly=True)
    action_result = fields.Text(string='Action Result')
    state_actual = fields.Text(string='State Actual')
    next_step = fields.Text(string='Next Step')
    history_message = fields.Text(string='History Message', readonly=True)


    
    @api.model
    def default_get(self, fields):
        res = super(UpdateBotMessage, self).default_get(fields)
        repair_id = self.env.context.get('active_id')
        if repair_id:
            repair_order = self.env['repair.order'].browse(repair_id)
            res.update({
                'repair_id': repair_order.id,
                'customer_name': repair_order.partner_id.name,
                'customer_phone': repair_order.partner_id.phone,
                'customer_desc': repair_order.description,
            })
        return res


    
    def action_updatebot_message(self):
        self.ensure_one()
        repair_order = self.repair_id

    # Obtener los detalles for the customer
        customer_name = repair_order.partner_id.name if repair_order.partner_id else 'Customer desconocido'
        customer_phone = repair_order.partner_id.phone if repair_order.partner_id else 'Phone desconocido'
        customer_desc = repair_order.description if repair_order.description else 'Description desconocida'


    # Mensaje original
        original_message = f"Hola, {customer_name}! descripcion del problema inicial: {customer_desc} ,Acciones realizadas: {self.action_result} State actual: {self.state_actual} ,Siguiente paso: {self.next_step} ,Notas: {self.message}"

    # Mejorar la redacción con el asistente de IA, si está activado
        integracion = self.env["repair.integration"]
        instruccion = integracion._param("ai_instruction") or INSTRUCCION_POR_DEFECTO
        prompt = (
            "%s\n\n"
            "Mejora la redacción del siguiente mensaje manteniendo un tono "
            "profesional, de modo que el cliente entienda con claridad la "
            "situación de su equipo y los siguientes pasos:\n\n%s"
        ) % (instruccion, original_message)

        improved_message = integracion.ai_complete(prompt, max_tokens=200)
        if not improved_message:
            # Sin IA configurada se envía el mensaje tal cual lo escribió el técnico
            improved_message = original_message
        improved_message = improved_message.strip()

    # Enviar el mensaje al cliente
        if not integracion.send_whatsapp(customer_phone, improved_message, silencioso=False):
            raise UserError(
                _("The message could not be sent. Revisa la configuración de "
                  "WhatsApp en Ajustes → Repair Workshop.")
            )

    # Crear el mensaje para el chatter
        mensaje = _("Se le envió este mensaje al cliente %s (Phone: %s, Description: %s): %s") % (
             customer_name, customer_phone, customer_desc, improved_message)

    # Publicar el mensaje en el chatter
        self.repair_id.message_post(body=mensaje, subtype_xmlid="mail.mt_note")

        return {'type': 'ir.actions.act_window_close'}