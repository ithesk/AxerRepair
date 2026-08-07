# -*- coding: utf-8 -*-
"""Ajustes del módulo, accesibles desde Ajustes → Repair Workshop."""

from odoo import _, fields, models

PREFIJO = "axer_repair."


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    # ------------------------------------------------------------------ #
    # WhatsApp                                                            #
    # ------------------------------------------------------------------ #
    rw_whatsapp_enabled = fields.Boolean(
        string="WhatsApp notifications",
        config_parameter=PREFIJO + "whatsapp_enabled",
        help="Notifies the customer whenever their repair changes state.",
    )
    rw_whatsapp_url = fields.Char(
        string="Gateway URL",
        config_parameter=PREFIJO + "whatsapp_url",
        help="Endpoint receiving {phone, message, mediaUrl} by POST. Example: http://my-server:3005/send-message",
    )
    rw_whatsapp_token = fields.Char(
        string="Token",
        config_parameter=PREFIJO + "whatsapp_token",
        help="Optional. Sent as an Authorization: Bearer header.",
    )
    rw_whatsapp_test_phone = fields.Char(
        string="Test phone number",
        config_parameter=PREFIJO + "whatsapp_test_phone",
    )

    # ------------------------------------------------------------------ #
    # Digital signature                                                       #
    # ------------------------------------------------------------------ #
    rw_signature_enabled = fields.Boolean(
        string="Digital signature",
        config_parameter=PREFIJO + "signature_enabled",
        help="Asks the customer to sign the quotation or the handover.",
    )
    rw_signature_url = fields.Char(
        string="Service URL",
        config_parameter=PREFIJO + "signature_url",
        help="Base URL of the signature API. Example: https://sign.mydomain.com/api",
    )
    rw_signature_token = fields.Char(
        string="API token",
        config_parameter=PREFIJO + "signature_token",
    )
    rw_signature_template_id = fields.Char(
        string="Template",
        config_parameter=PREFIJO + "signature_template_id",
        help="Identifier of the document template the customer signs.",
    )

    # ------------------------------------------------------------------ #
    # IMEI lookup                                                    #
    # ------------------------------------------------------------------ #
    rw_imei_enabled = fields.Boolean(
        string="IMEI lookup",
        config_parameter=PREFIJO + "imei_enabled",
        help="Looks up the model and status of the device from its IMEI.",
    )
    rw_imei_url = fields.Char(
        string="Service URL",
        config_parameter=PREFIJO + "imei_url",
        default="https://sickw.com/api.php",
    )
    rw_imei_key = fields.Char(
        string="API key",
        config_parameter=PREFIJO + "imei_key",
        help="These services usually charge per lookup: check the rate before using them in bulk.",
    )

    # ------------------------------------------------------------------ #
    # AI assistant                                                     #
    # ------------------------------------------------------------------ #
    rw_ai_enabled = fields.Boolean(
        string="AI assistant",
        config_parameter=PREFIJO + "ai_enabled",
        help="Drafts the follow-up messages to the customer automatically.",
    )
    rw_ai_api_key = fields.Char(
        string="API key",
        config_parameter=PREFIJO + "ai_api_key",
    )
    rw_ai_model = fields.Char(
        string="Model",
        config_parameter=PREFIJO + "ai_model",
        default="gpt-4o-mini",
    )
    rw_ai_base_url = fields.Char(
        string="Alternative URL",
        config_parameter=PREFIJO + "ai_base_url",
        help="Optional. To use a provider compatible with the OpenAI API or a local model (Ollama, LM Studio).",
    )
    # 'config_parameter' no acepta campos Text, así que este se guarda a mano
    # en get_values / set_values para conservar el editor de varias líneas.
    rw_ai_instruction = fields.Text(
        string="Assistant instructions",
        help="Describes the role the assistant takes when drafting messages: tone, technical level and the name of your workshop.",
    )

    # ------------------------------------------------------------------ #
    # Odoo externo (XML-RPC)                                              #
    # ------------------------------------------------------------------ #
    rw_xmlrpc_enabled = fields.Boolean(
        string="Synchronise with another Odoo",
        config_parameter=PREFIJO + "xmlrpc_enabled",
        help="Creates products and contacts in a second Odoo database.",
    )
    rw_xmlrpc_url = fields.Char(
        string="URL",
        config_parameter=PREFIJO + "xmlrpc_url",
        help="Ejemplo: https://otra-instancia.odoo.com",
    )
    rw_xmlrpc_db = fields.Char(
        string="Database",
        config_parameter=PREFIJO + "xmlrpc_db",
    )
    rw_xmlrpc_user = fields.Char(
        string="User",
        config_parameter=PREFIJO + "xmlrpc_user",
    )
    rw_xmlrpc_password = fields.Char(
        string="Password or API key",
        config_parameter=PREFIJO + "xmlrpc_password",
    )

    # ------------------------------------------------------------------ #
    # Workshop identity                                                #
    # ------------------------------------------------------------------ #
    # El nombre, el logotipo y los datos de contacto salen de la ficha de la
    # compañía (Ajustes → Users y compañías). Aquí solo van los enlaces
    # propios del taller, que Odoo no contempla.
    rw_warranty_url = fields.Char(
        string="Warranty policy",
        config_parameter=PREFIJO + "warranty_url",
        help="Page where the customer can read the warranty terms. It appears on the receipt and in handover notifications.",
    )
    rw_community_url = fields.Char(
        string="Offers and community",
        config_parameter=PREFIJO + "community_url",
        help="Link offered to the customer once the repair is finished.",
    )
    rw_social_url = fields.Char(
        string="Social media",
        config_parameter=PREFIJO + "social_url",
        help="Profile offered when a device could not be repaired.",
    )
    rw_abandoned_days = fields.Integer(
        string="Abandoned equipment notice",
        config_parameter=PREFIJO + "abandoned_days",
        default=45,
        help="Days after which the workshop is no longer liable for an uncollected device. Printed on the receipt. Zero to omit it.",
    )
    rw_message_signature = fields.Char(
        string="Message signature",
        config_parameter=PREFIJO + "message_signature",
        help="How customer notifications sign off. If left empty, the company name is used.",
    )

    # ------------------------------------------------------------------ #
    # External access                                                  #
    # ------------------------------------------------------------------ #
    rw_api_key = fields.Char(
        string="API key",
        config_parameter=PREFIJO + "api_key",
        help="Key that external applications must send in the Authorization header to query repairs or request messages. Without a key, those endpoints stay closed.",
    )
    rw_webhook_secret = fields.Char(
        string="Signature webhook secret",
        config_parameter=PREFIJO + "webhook_secret",
        help="The signature service must send it in the X-Webhook-Secret header. Without it, anyone could mark a repair as signed.",
    )

    # ------------------------------------------------------------------ #
    # Campos que no admite 'config_parameter'                             #
    # ------------------------------------------------------------------ #
    def get_values(self):
        res = super().get_values()
        res["rw_ai_instruction"] = self.env["ir.config_parameter"].sudo().get_param(
            PREFIJO + "ai_instruction", ""
        )
        return res

    def set_values(self):
        super().set_values()
        self.env["ir.config_parameter"].sudo().set_param(
            PREFIJO + "ai_instruction", self.rw_ai_instruction or ""
        )

    # ------------------------------------------------------------------ #
    # Buttons de prueba                                                   #
    # ------------------------------------------------------------------ #
    def _probar(self, servicio):
        self.ensure_one()
        mensaje = self.env["repair.integration"].test_connection(servicio)
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {"title": _("Connection successful"), "message": mensaje,
                       "type": "success", "sticky": False},
        }

    def action_test_whatsapp(self):
        return self._probar("whatsapp")

    def action_test_signature(self):
        self.ensure_one()
        if not self.rw_signature_url:
            from odoo.exceptions import UserError
            raise UserError(_("Enter the URL of the signature service."))
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {"title": _("Settings saved"),
                       "message": _("Digital signature will be validated on the first real request."),
                       "type": "info", "sticky": False},
        }

    def action_test_ai(self):
        return self._probar("ai")

    def action_test_xmlrpc(self):
        return self._probar("xmlrpc")
