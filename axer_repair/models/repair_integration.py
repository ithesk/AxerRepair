# -*- coding: utf-8 -*-
"""Punto único de acceso a los servicios externos del módulo.

Todas las integraciones (WhatsApp, firma digital, IA y XML-RPC) pasan por
aquí. Así no hay credenciales ni URLs repartidas por el código: se
configuran desde Ajustes y cada una puede desactivarse por separado.
"""
import logging

import requests

from odoo import _, api, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

PREFIJO = "axer_repair."
TIEMPO_ESPERA = 20  # segundos


class RepairIntegration(models.AbstractModel):
    _name = "repair.integration"
    _description = "External repair services"

    # ------------------------------------------------------------------
    # Lectura de la configuración
    # ------------------------------------------------------------------
    @api.model
    def _param(self, clave, defecto=""):
        return self.env["ir.config_parameter"].sudo().get_param(PREFIJO + clave, defecto)

    @api.model
    def _activo(self, servicio):
        return self._param("%s_enabled" % servicio, "False") in ("True", "true", "1")

    # ------------------------------------------------------------------
    # WhatsApp
    # ------------------------------------------------------------------
    @api.model
    def send_whatsapp(self, telefono, mensaje, media_url="", silencioso=True):
        """Envía un mensaje por la pasarela de WhatsApp configurada.

        Devuelve True si se envió. Si el servicio está desactivado o falla,
        registra el motivo y devuelve False (salvo silencioso=False, que
        lanza el error para que lo vea el usuario).
        """
        if not self._activo("whatsapp"):
            _logger.debug("WhatsApp desactivado: no se envía a %s", telefono)
            return False
        url = self._param("whatsapp_url")
        if not url:
            _logger.warning("WhatsApp activado pero sin URL configurada")
            return False
        if not telefono:
            return False

        datos = {"phone": telefono, "message": mensaje, "mediaUrl": media_url or ""}
        cabeceras = {}
        clave = self._param("whatsapp_token")
        if clave:
            cabeceras["Authorization"] = "Bearer %s" % clave

        try:
            resp = requests.post(url, json=datos, headers=cabeceras, timeout=TIEMPO_ESPERA)
            resp.raise_for_status()
            return True
        except requests.RequestException as err:
            _logger.warning("Fallo al enviar WhatsApp a %s: %s", telefono, err)
            if not silencioso:
                raise UserError(_("Could not send the WhatsApp message: %s") % err)
            return False

    # ------------------------------------------------------------------
    # Digital signature (DocuSeal)
    # ------------------------------------------------------------------
    @api.model
    def signature_enabled(self):
        return self._activo("signature")

    @api.model
    def signature_request(self, ruta, payload):
        """Llama a la API de firma digital. `ruta` se añade a la URL base."""
        if not self._activo("signature"):
            return None
        base = (self._param("signature_url") or "").rstrip("/")
        token = self._param("signature_token")
        if not base:
            _logger.warning("Digital signature activada pero sin URL configurada")
            return None

        cabeceras = {"Content-Type": "application/json"}
        if token:
            cabeceras["X-Auth-Token"] = token
        try:
            resp = requests.post(
                "%s/%s" % (base, ruta.lstrip("/")),
                json=payload,
                headers=cabeceras,
                timeout=TIEMPO_ESPERA,
            )
            resp.raise_for_status()
            return resp.json()
        except requests.RequestException as err:
            _logger.warning("Fallo en la API de firma: %s", err)
            raise UserError(_("Could not reach the signature service: %s") % err)

    # ------------------------------------------------------------------
    # AI assistant
    # ------------------------------------------------------------------
    @api.model
    def ai_enabled(self):
        return self._activo("ai") and bool(self._param("ai_api_key"))

    @api.model
    def ai_complete(self, prompt, max_tokens=200):
        """Devuelve la respuesta del modelo, o None si la IA está desactivada."""
        if not self.ai_enabled():
            return None
        try:
            from openai import OpenAI
        except ImportError:
            raise UserError(
                _("El asistente de IA necesita la librería 'openai'. "
                  "Instálala con: pip install openai")
            )

        cliente = OpenAI(
            api_key=self._param("ai_api_key"),
            base_url=self._param("ai_base_url") or None,
        )
        modelo = self._param("ai_model") or "gpt-4o-mini"
        try:
            resp = cliente.chat.completions.create(
                model=modelo,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=int(max_tokens),
            )
            return resp.choices[0].message.content
        except Exception as err:  # la librería define su propia jerarquía
            _logger.warning("Fallo en el asistente de IA: %s", err)
            raise UserError(_("The AI assistant did not answer: %s") % err)

    # ------------------------------------------------------------------
    # Odoo externo por XML-RPC
    # ------------------------------------------------------------------
    @api.model
    def xmlrpc_enabled(self):
        return self._activo("xmlrpc")

    @api.model
    def _xmlrpc_conectar(self):
        """Devuelve (models, db, uid, password) o None si no está configurado.

        La conexión se abre bajo demanda, nunca al importar el módulo.
        """
        if not self._activo("xmlrpc"):
            return None
        url = self._param("xmlrpc_url")
        db = self._param("xmlrpc_db")
        usuario = self._param("xmlrpc_user")
        clave = self._param("xmlrpc_password")
        if not all([url, db, usuario, clave]):
            _logger.warning("XML-RPC activado pero faltan datos de conexión")
            return None

        import xmlrpc.client

        try:
            common = xmlrpc.client.ServerProxy("%s/xmlrpc/2/common" % url.rstrip("/"))
            uid = common.authenticate(db, usuario, clave, {})
            if not uid:
                raise UserError(_("Credentials rejected by the external Odoo."))
            modelos = xmlrpc.client.ServerProxy("%s/xmlrpc/2/object" % url.rstrip("/"))
            return modelos, db, uid, clave
        except UserError:
            raise
        except Exception as err:
            _logger.warning("No se pudo conectar por XML-RPC a %s: %s", url, err)
            raise UserError(_("Could not connect to the external Odoo: %s") % err)

    @api.model
    def xmlrpc_execute(self, modelo, metodo, args, kwargs=None):
        """Ejecuta un método en el Odoo externo. Devuelve None si está desactivado."""
        conexion = self._xmlrpc_conectar()
        if not conexion:
            return None
        modelos, db, uid, clave = conexion
        return modelos.execute_kw(db, uid, clave, modelo, metodo, args, kwargs or {})

    @api.model
    def test_connection(self, servicio):
        """Comprueba un servicio desde el botón de Ajustes."""
        if servicio == "whatsapp":
            destino = self._param("whatsapp_test_phone")
            if not destino:
                raise UserError(_("Enter a test phone number."))
            if self.send_whatsapp(destino, _("Test message from Odoo."), silencioso=False):
                return _("Mensaje enviado correctamente a %s.") % destino
            raise UserError(_("The message could not be sent."))
        if servicio == "xmlrpc":
            self._xmlrpc_conectar()
            return _("Connection to the external Odoo is working.")
        if servicio == "ai":
            if self.ai_complete(_("Answer only with the word: correct")):
                return _("The AI assistant is responding.")
            raise UserError(_("The AI assistant is not configured."))
        raise UserError(_("Unknown service: %s") % servicio)
