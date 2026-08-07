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

        abierta = self._crear_reparacion()
        self.env.cr.execute(
            "UPDATE repair_order SET create_date = now() - interval '12 days' WHERE id = %s",
            (abierta.id,))
        abierta.invalidate_recordset()
        self.env.add_to_compute(abierta._fields["days_elapsed"], abierta)
        abierta.flush_recordset(["days_elapsed"])
        self.assertEqual(abierta.days_elapsed, 12)

        cerrada = self._crear_reparacion(imei="350000000000009")
        self.env.cr.execute(
            "UPDATE repair_order SET create_date = now() - interval '30 days' WHERE id = %s",
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
