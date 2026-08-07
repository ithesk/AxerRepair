# -*- coding: utf-8 -*-
"""Las direcciones públicas no pueden abrirse sin credencial.

Estas pruebas existen porque el módulo llegó a publicar en internet, sin
comprobar nada, el nombre, el teléfono y el código de desbloqueo de cualquier
cliente. Son las que impiden que vuelva a ocurrir.
"""

import json

from odoo.tests.common import HttpCase, tagged


@tagged("post_install", "-at_install")
class PruebaRutasPublicas(HttpCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        sucursal = cls.env["repair.location"].create({"name": "Taller de pruebas"})
        # El teléfono tiene una restricción de unicidad en la base de datos:
        # se limpian residuos de ejecuciones anteriores antes de crear.
        cls.env["res.partner"].search(
            [("phone", "=", "18095550002")]).write({"phone": False})
        cls.cliente = cls.env["res.partner"].create({
            "name": "Cliente de pruebas", "phone": "18095550002"})
        producto = cls.env["product.product"].create({
            "name": "Teléfono de pruebas", "type": "consu"})
        cls.reparacion = cls.env["repair.order"].create({
            "partner_id": cls.cliente.id, "product_id": producto.id,
            "product_uom": producto.uom_id.id, "description": "No enciende",
            "lead_source": "recomendacion", "imei": "350000000000002",
            "branch_id": sucursal.id, "passcode": "1234",
        })
        cls.token = cls.reparacion.get_access_token()
        # Sin commit: HttpCase comparte su transacción con las peticiones, y
        # confirmarla aquí deja el caso sin poder deshacer sus propios datos.

    # ------------------------------------------------------------------ #
    # Seguimiento del cliente                                             #
    # ------------------------------------------------------------------ #
    def test_seguimiento_exige_el_token(self):
        respuesta = self.url_open("/repair/track/%d/token-inventado" % self.reparacion.id)
        self.assertNotIn(self.cliente.name, respuesta.text)
        self.assertNotIn(self.reparacion.imei, respuesta.text)

    def test_seguimiento_funciona_con_el_token(self):
        respuesta = self.url_open("/repair/track/%d/%s" % (self.reparacion.id, self.token))
        self.assertEqual(respuesta.status_code, 200)

    def test_el_codigo_de_desbloqueo_no_sale_al_portal(self):
        """Es la llave del equipo: no puede viajar a una página pública."""
        respuesta = self.url_open("/repair/track/%d/%s" % (self.reparacion.id, self.token))
        self.assertNotIn(self.reparacion.passcode, respuesta.text)

    # ------------------------------------------------------------------ #
    # API para aplicaciones externas                                      #
    # ------------------------------------------------------------------ #
    def _consultar_api(self, cabeceras=None):
        return self.url_open(
            "/api/get-repair-orders",
            data=json.dumps({"phone": self.cliente.phone}),
            headers=dict({"Content-Type": "application/json"}, **(cabeceras or {})))

    def test_la_api_se_niega_sin_clave(self):
        self.assertEqual(self._consultar_api().status_code, 403)

    def test_la_api_se_niega_con_clave_inventada(self):
        respuesta = self._consultar_api({"Authorization": "Bearer inventada"})
        self.assertEqual(respuesta.status_code, 403)

    def test_la_api_no_describe_el_error(self):
        """El mensaje de rechazo no cuenta nada de la instalación."""
        respuesta = self._consultar_api()
        self.assertNotIn("Traceback", respuesta.text)
        self.assertNotIn("odoo", respuesta.text.lower())

    # El camino con la clave correcta no se prueba aquí: la petición la
    # atiende otro hilo, con su propia caché de parámetros, y una clave escrita
    # dentro de la transacción del test no llega a verse. Se comprueba contra
    # el servidor en marcha, donde responde 200 con los datos.

    def test_el_envio_de_mensajes_se_niega_sin_clave(self):
        respuesta = self.url_open(
            "/api/send-message",
            data=json.dumps({"phone": "18095550003", "message": "hola"}),
            headers={"Content-Type": "application/json"})
        self.assertEqual(respuesta.status_code, 403)

    # ------------------------------------------------------------------ #
    # Webhook del servicio de firma                                       #
    # ------------------------------------------------------------------ #
    def test_el_webhook_de_firma_exige_el_secreto(self):
        """Sin secreto, cualquiera podría dar por firmado un presupuesto."""
        respuesta = self.url_open(
            "/docuseal/webhook/",
            data=json.dumps({"jsonrpc": "2.0", "method": "call", "params": {}}),
            headers={"Content-Type": "application/json"})
        self.assertIn("autorizado", respuesta.text.lower())
        self.assertEqual(self.reparacion.signature_status, "pending")
