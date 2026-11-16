# -*- coding: utf-8 -*-
"""El recorrido de una reparación, de la recepción a la garantía."""

from odoo.exceptions import ValidationError
from odoo.tests.common import tagged

from .common import ComunTaller


@tagged("post_install", "-at_install")
class PruebaCicloReparacion(ComunTaller):

    def test_ciclo_completo(self):
        """Cada acción deja la reparación en el estado que le toca."""
        reparacion = self._crear_reparacion(warranty_fields=30)
        self.assertEqual(reparacion.state, "draft")

        pasos = [
            ("action_repair_confirm", "confirmed"),
            ("action_repair_start", "under_repair"),
            ("action_repair_test", "test"),
            ("action_repair_end_confirmed", "done"),
            ("action_repair_handover", "handover"),
            ("action_repair_guarantee", "guarantee"),
        ]
        for metodo, esperado in pasos:
            getattr(reparacion, metodo)()
            self.assertEqual(
                reparacion.state, esperado,
                "tras %s la reparación debería quedar en '%s'" % (metodo, esperado))

    def test_garantia_al_entregar(self):
        """Al entregar se fija el fin de la garantía sumando los días dados."""
        from datetime import timedelta
        from odoo import fields

        reparacion = self._crear_reparacion(warranty_fields=30)
        reparacion.action_repair_confirm()
        reparacion.action_repair_start()
        reparacion.action_repair_test()
        reparacion.action_repair_end_confirmed()
        reparacion.action_repair_handover()

        self.assertEqual(reparacion.guarantee_limit,
                         fields.Date.today() + timedelta(days=30))

    def test_sucursal_por_defecto(self):
        """Una reparación nueva propone una sucursal: el campo es obligatorio."""
        valores = self.env["repair.order"].default_get(["branch_id"])
        self.assertTrue(valores.get("branch_id"),
                        "sin sucursal por defecto no se puede guardar nada")

    def test_lectura_completa_de_la_ficha(self):
        """Todos los campos calculados se leen sin excepción.

        Es la prueba que detecta los restos de versiones anteriores: un campo
        que apunte a un modelo inexistente o un cálculo que use un atributo
        eliminado rompen aquí, no en producción.
        """
        reparacion = self._crear_reparacion()
        campos = [n for n, f in reparacion._fields.items() if f.store or f.compute]
        reparacion.read(campos)

    def test_telefono_admite_formatos_internacionales(self):
        """La validación no puede atarse a la numeración de un país."""
        contacto = self.env["res.partner"].create({
            "name": "Cliente extranjero", "phone": "34600111222", "customer_rank": 1})
        self.assertTrue(contacto.id)

        with self.assertRaises(ValidationError):
            self.env["res.partner"].create({
                "name": "Malo", "phone": "12ab", "customer_rank": 1})

    def test_el_modulo_no_estorba_al_resto_de_contactos(self):
        """Un proveedor puede compartir teléfono con un cliente, y no llevarlo.

        El módulo llegó a imponer teléfono obligatorio y único a todos los
        contactos de Odoo, lo que impedía guardar una empresa y su persona de
        contacto con el mismo número.
        """
        sin_telefono = self.env["res.partner"].create({"name": "Proveedor sin teléfono"})
        self.assertTrue(sin_telefono.id)

        mismo_numero = self.env["res.partner"].create({
            "name": "Persona de contacto", "phone": self.cliente.phone})
        self.assertTrue(mismo_numero.id)

    def test_dos_clientes_no_comparten_telefono(self):
        """Entre clientes sí se vigila: el teléfono localiza la reparación."""
        self.cliente.customer_rank = 1
        with self.assertRaises(ValidationError):
            self.env["res.partner"].create({
                "name": "Cliente duplicado", "phone": self.cliente.phone,
                "customer_rank": 1})

    def test_dias_en_taller(self):
        """Cuenta hasta hoy si sigue abierta y se congela al entregar.

        El campo está almacenado y dependía solo de 'create_date', que nunca
        cambia: se quedaba en el cero del día del alta.
        """
        from datetime import timedelta
        from odoo import fields

        # Una hora de margen: now() de la base lleva microsegundos y la hora de
        # Odoo no, y sin margen la resta daba 11 días según el instante.
        abierta = self._crear_reparacion()
        self.env.cr.execute(
            "UPDATE repair_order SET create_date = now() - interval '12 days 1 hour' WHERE id = %s",
            (abierta.id,))
        abierta.invalidate_recordset()
        self.env.add_to_compute(abierta._fields["days_elapsed"], abierta)
        abierta.flush_recordset(["days_elapsed"])
        self.assertEqual(abierta.days_elapsed, 12)

        cerrada = self._crear_reparacion(imei="350000000000009")
        self.env.cr.execute(
            "UPDATE repair_order SET create_date = now() - interval '30 days 1 hour' WHERE id = %s",
            (cerrada.id,))
        cerrada.invalidate_recordset()
        cerrada.write({"state": "handover",
                       "done_date_w": fields.Datetime.now() - timedelta(days=25)})
        self.env.add_to_compute(cerrada._fields["days_elapsed"], cerrada)
        cerrada.flush_recordset(["days_elapsed"])
        self.assertEqual(cerrada.days_elapsed, 5,
                         "una reparación entregada deja de sumar días")

        # Fechas incoherentes no pueden dar días negativos
        cerrada.write({"done_date_w": fields.Datetime.now() - timedelta(days=40)})
        self.env.add_to_compute(cerrada._fields["days_elapsed"], cerrada)
        cerrada.flush_recordset(["days_elapsed"])
        self.assertEqual(cerrada.days_elapsed, 0)

    def test_importe_total_sin_pedido(self):
        """Sin pedido de venta, el importe es el presupuesto estimado."""
        reparacion = self._crear_reparacion(estimated_budget=4500)
        self.assertEqual(reparacion.amount_total, 4500)

    def test_telefono_de_republica_dominicana(self):
        """Odoo guarda 1849 como prefijo de RD; el número no debe llevarlo pegado."""
        dominicana = self.env.ref("base.do")
        casos = {
            "809-555-0199": "18095550199",
            "(829) 555 0199": "18295550199",
            "8495550199": "18495550199",
            "1 809 555 0199": "18095550199",
            "+1 (809) 555-0199": "18095550199",
        }
        for i, (escrito, esperado) in enumerate(casos.items()):
            contacto = self.env["res.partner"].create({
                "name": "Dominicano %s" % i, "phone": escrito,
                "country_id": dominicana.id})
            self.assertEqual(contacto.phone, esperado, escrito)

    # ------------------------------------------------------------------
    # Convivencia con ventas: opciones de Ajustes
    # ------------------------------------------------------------------
    def test_telefono_tal_como_se_escribe(self):
        """Con «como se escribe» el contacto no se toca, pero el envío sale limpio."""
        self._ajustar("phone_storage", "keep")
        contacto = self.env["res.partner"].create({
            "name": "Cliente de la caja", "phone": "809-555-0142",
            "country_id": self.env.ref("base.do").id, "customer_rank": 1})
        self.assertEqual(contacto.phone, "809-555-0142")
        self.assertEqual(contacto._rw_telefono_whatsapp(), "18095550142")

    def test_telefono_repetido_se_reconoce_con_otro_formato(self):
        """El mismo número escrito de otra forma sigue siendo el mismo número."""
        self._ajustar("phone_storage", "keep")
        self.env["res.partner"].create({
            "name": "Primero", "phone": "809-555-0143", "customer_rank": 1})
        with self.assertRaises(ValidationError):
            self.env["res.partner"].create({
                "name": "Segundo", "phone": "(809) 555 0143", "customer_rank": 1})

    def test_telefono_repetido_permitido_si_se_desactiva(self):
        for modo in ("warn", "off"):
            self._ajustar("phone_unique", modo)
            numero = "80955501%s" % (44 if modo == "warn" else 45)
            uno = self.env["res.partner"].create({
                "name": "Uno %s" % modo, "phone": numero, "customer_rank": 1})
            dos = self.env["res.partner"].create({
                "name": "Dos %s" % modo, "phone": numero, "customer_rank": 1})
            self.assertTrue(uno.id and dos.id)
            aviso = dos._onchange_rw_telefono_repetido()
            self.assertEqual(bool(aviso), modo == "warn")

    def test_numeracion_propia(self):
        normal = self._crear_reparacion()
        self.assertFalse(normal.name.startswith("R0"))
        self._ajustar("own_numbering", "True")
        primera = self._crear_reparacion(imei="350000000000017")
        segunda = self._crear_reparacion(imei="350000000000018")
        self.assertRegex(primera.name, r"^R\d{6}$")
        self.assertEqual(int(segunda.name[1:]), int(primera.name[1:]) + 1)

    def test_equipo_de_cliente_fuera_de_la_venta(self):
        Producto = self.env["product.product"].with_context(axer_repair_device=True)
        equipo = Producto.create({"name": "Equipo de un cliente", "type": "consu"})
        self.assertFalse(equipo.sale_ok)
        self.assertFalse(equipo.purchase_ok)
        self.assertEqual(equipo.categ_id,
                         self.env.ref("axer_repair.product_category_customer_devices"))
        # Un producto normal no cambia
        normal = self.env["product.product"].create({"name": "Mercancía", "type": "consu"})
        self.assertTrue(normal.sale_ok)
        # Y el taller que vende esos modelos puede desactivarlo
        self._ajustar("devices_for_sale", "True")
        vendible = Producto.create({"name": "Equipo que también se vende", "type": "consu"})
        self.assertTrue(vendible.sale_ok)

