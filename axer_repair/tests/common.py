# -*- coding: utf-8 -*-
"""Datos de partida compartidos por las pruebas."""

from odoo.tests.common import TransactionCase


class ComunTaller(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.sucursal = cls.env["repair.location"].create({
            "name": "Taller de pruebas",
        })
        # El teléfono tiene una restricción de unicidad en la base de datos:
        # se limpian residuos de ejecuciones anteriores antes de crear.
        cls.env["res.partner"].search(
            [("phone", "=", "18095550001")]).write({"phone": False})
        cls.cliente = cls.env["res.partner"].create({
            "name": "Cliente de pruebas",
            "phone": "18095550001",
        })
        cls.producto = cls.env["product.product"].create({
            "name": "Teléfono de pruebas",
            "type": "consu",
        })

    def _crear_reparacion(self, **valores):
        datos = {
            "partner_id": self.cliente.id,
            "product_id": self.producto.id,
            "product_uom": self.producto.uom_id.id,
            "description": "No enciende",
            "lead_source": "recomendacion",
            "imei": "350000000000001",
            "branch_id": self.sucursal.id,
        }
        datos.update(valores)
        return self.env["repair.order"].create(datos)

    def _ajustar(self, clave, valor):
        self.env["ir.config_parameter"].sudo().set_param(
            "axer_repair." + clave, valor)
