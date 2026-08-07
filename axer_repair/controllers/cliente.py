# -*- coding: utf-8 -*-
"""Consulta de reparaciones desde fuera de Odoo.

Todas estas direcciones son públicas, así que exigen credencial:

* las de una reparación concreta piden su token de acceso, el mismo que lleva
  el enlace que se envía al cliente;
* las de la API piden la clave configurada en Ajustes → Repair Workshop.

Sin credencial responden 404 o 403. Antes bastaba con recorrer los números de
reparación para leer el nombre, el phone y el código de desbloqueo de
cualquier cliente.
"""

import json
import logging

import requests

from odoo import http
from odoo.http import request

_logger = logging.getLogger(__name__)

TIEMPO_ESPERA = 20


def _clave_valida(clave_enviada):
    """Comprueba la clave de la API. Sin clave configurada, no se abre nada."""
    esperada = request.env["ir.config_parameter"].sudo().get_param(
        "axer_repair.api_key")
    if not esperada:
        return False
    if not clave_enviada:
        return False
    recibida = clave_enviada.replace("Bearer ", "").strip()
    # Comparación en tiempo constante para no filtrar la clave carácter a carácter
    import hmac
    return hmac.compare_digest(recibida, esperada)


def _cabeceras_cors():
    return {
        "Access-Control-Allow-Origin": request.env["ir.config_parameter"].sudo().get_param(
            "axer_repair.api_origin", "*"),
        "Access-Control-Allow-Methods": "POST, OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type, Authorization",
    }


def _reparacion_autorizada(order_id, token):
    """Devuelve la reparación solo si el token corresponde."""
    orden = request.env["repair.order"].sudo().browse(order_id)
    if not orden.exists() or not token or orden.access_token != token:
        return request.env["repair.order"]
    return orden


# Las rutas /repair/order y /repacion/order se han retirado: renderizaban las
# plantillas 'repair_portal_template' y 'repair_portal_template2', que no
# existen en el módulo, así que siempre respondían con un error. Eran, además,
# públicas y sin comprobación de identidad. El seguimiento for the customer se hace
# por /repair/track/<id>/<token>, que sí funciona y exige el token.


class RepairControllerNext(http.Controller):

    @http.route('/api/get-repair-orders', type='http', auth='public',
                methods=['POST', 'OPTIONS'], csrf=False)
    def get_repair_orders(self, **kwargs):
        cabeceras = _cabeceras_cors()
        if request.httprequest.method == 'OPTIONS':
            return http.Response(status=200, headers=cabeceras)

        if not _clave_valida(request.httprequest.headers.get('Authorization')):
            return http.Response(json.dumps({"error": "No autorizado"}),
                                 status=403, headers=cabeceras)
        try:
            datos = json.loads(request.httprequest.data)
            telefono = datos.get('phone')
            if not telefono:
                return http.Response(json.dumps({"error": "Falta el phone"}),
                                     status=400, headers=cabeceras)

            cliente = request.env['res.partner'].sudo().search(
                [('phone', '=', telefono)], limit=1)
            if not cliente:
                return http.Response(json.dumps({"error": "Customer no encontrado"}),
                                     status=404, headers=cabeceras)

            reparaciones = request.env['repair.order'].sudo().search(
                [('partner_id', '=', cliente.id)])
            # El código de desbloqueo no sale de Odoo: es la llave del equipo.
            lista = [{
                'id': orden.id,
                'product_name': orden.product_id.name,
                'description': orden.description,
                'imei': orden.imei,
                'evaluation': orden.evaluation,
                'state': orden.state,
                'partner_name': orden.partner_id.name,
                'user_id': orden.user_id.name,
                'battery': orden.battery or 0,
                'total_amount': orden.amount_total,
                'progress_percentage': orden.progress_percentage,
                'faceid': orden.faceid,
                'signal': orden.signal,
                'wifi': orden.wifi,
                'screen': orden.screen,
                'touch': orden.touch,
                'camera': orden.camera,
                'charging': orden.charging,
                'microphone': orden.microphone,
                'camerafront': orden.camerafront,
                'flash': orden.flash,
                'powerstate': orden.powerstate,
                'truetone': orden.truetone,
                'speaker': orden.speaker,
                'cover': orden.cover,
                'pos_url': orden.pos_url,
            } for orden in reparaciones]

            return http.Response(json.dumps({"status": "success", "orders": lista}),
                                 status=200, headers=cabeceras)
        except Exception as error:                      # noqa: BLE001
            _logger.exception("Error consultando reparaciones")
            # No se devuelve el detalle: describiría la instalación por dentro.
            return http.Response(json.dumps({"error": "Error interno"}),
                                 status=500, headers=cabeceras)


class MessageRepairController(http.Controller):

    @http.route('/api/send-message', type='http', auth='public',
                methods=['POST', 'OPTIONS'], csrf=False)
    def send_message(self, **kwargs):
        cabeceras = _cabeceras_cors()
        if request.httprequest.method == 'OPTIONS':
            return http.Response(status=200, headers=cabeceras)

        if not _clave_valida(request.httprequest.headers.get('Authorization')):
            return http.Response(json.dumps({"error": "No autorizado"}),
                                 status=403, headers=cabeceras)
        try:
            datos = json.loads(request.httprequest.data)
            telefono = datos.get('phone')
            mensaje = datos.get('message')
            if not telefono or not mensaje:
                return http.Response(json.dumps({"error": "Faltan datos"}),
                                     status=400, headers=cabeceras)

            # 'self.env' no existe en un controlador: esta ruta fallaba siempre.
            integracion = request.env['repair.integration'].sudo()
            if not integracion._activo('whatsapp'):
                return http.Response(json.dumps({"error": "Avisos desactivados"}),
                                     status=503, headers=cabeceras)
            url = integracion._param('whatsapp_url')
            requests.post(url, json={"phone": telefono, "message": mensaje,
                                     "mediaUrl": ""}, timeout=TIEMPO_ESPERA)
            return http.Response(json.dumps({"status": "success"}),
                                 status=200, headers=cabeceras)
        except Exception:                               # noqa: BLE001
            _logger.exception("Error enviando el mensaje")
            return http.Response(json.dumps({"error": "Error interno"}),
                                 status=500, headers=cabeceras)
