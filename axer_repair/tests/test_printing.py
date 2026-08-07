# -*- coding: utf-8 -*-
"""Informes e impresión.

Lo que se comprueba aquí es que el módulo sirva igual en un servidor sin CUPS:
en ese caso debe ofrecer el PDF, nunca fallar.
"""

from odoo.tests.common import tagged

from .common import ComunTaller

INFORMES = [
    "axer_repair.action_report_repair_order",
    "axer_repair.action_report_repair_order4",
    "axer_repair.action_report_repair_order5",
    "axer_repair.action_report_repair_order_qr_simple",
]


@tagged("post_install", "-at_install")
class PruebaImpresion(ComunTaller):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # Sin diseño de documento, Odoo intercepta cualquier impresión y
        # devuelve su asistente de configuración en lugar del informe.
        if not cls.env.company.external_report_layout_id:
            cls.env.company.external_report_layout_id = cls.env.ref(
                "web.external_layout_standard")

    def test_los_informes_se_generan(self):
        """Cada informe produce su HTML sin romper la plantilla."""
        reparacion = self._crear_reparacion(estimated_budget=1200, powerstate=True,
                                            battery=80)
        for xmlid in INFORMES:
            informe = self.env.ref(xmlid)
            with self.subTest(informe=xmlid):
                cuerpo = self.env["ir.actions.report"]._render_qweb_html(
                    informe.report_name, reparacion.ids)[0]
                self.assertTrue(cuerpo)

    def test_el_recibo_sale_una_vez_por_reparacion(self):
        """Tres reparaciones son tres hojas, no nueve ni veintisiete.

        La plantilla del recibo llegó a recorrer 'docs' tres veces anidadas.
        """
        reparaciones = self.env["repair.order"]
        for i in range(3):
            reparaciones |= self._crear_reparacion(imei="35000000000000%d" % i)
        html = self.env["ir.actions.report"]._render_qweb_html(
            "axer_repair.report_repairorder3", reparaciones.ids)[0].decode()
        for reparacion in reparaciones:
            self.assertEqual(html.count(reparacion.name), 1,
                             "%s aparece más de una vez en el recibo" % reparacion.name)

    def test_sin_impresora_se_ofrece_el_pdf(self):
        """Sin CUPS ni impresora configurada no se falla: se devuelve el PDF."""
        reparacion = self._crear_reparacion()
        self.sucursal.write({"printer_name": "", "cups_server_ip": ""})
        accion = reparacion.print_label()
        self.assertIsInstance(accion, dict)
        self.assertEqual(accion.get("type"), "ir.actions.report")

    def test_las_etiquetas_masivas_no_interrumpen_el_alta(self):
        """Un fallo de impresora no puede cortar el alta de varios equipos."""
        reparacion = self._crear_reparacion()
        self.sucursal.write({"printer_name": "cola-inexistente",
                             "cups_server_ip": "203.0.113.1"})
        reparacion._print_simple_labels(reparacion)   # no debe lanzar nada
        self.assertFalse(reparacion.label_printed)

    def test_el_recibo_no_lleva_marca_del_modulo(self):
        """La identidad sale de la compañía, no del código."""
        self.env.company.name = "Taller Ejemplo"
        reparacion = self._crear_reparacion()
        html = self.env["ir.actions.report"]._render_qweb_html(
            "axer_repair.report_repairorder3", reparacion.ids)[0].decode()
        self.assertIn("Taller Ejemplo", html)
        for marca in ("ithesk", "n9.cl", "809-274"):
            self.assertNotIn(marca, html.lower())
