# -*- coding: utf-8 -*-
"""Envío de documentos a las impresoras del taller.

Todo el módulo imprime a través de este servicio. Antes había siete copias del
mismo bloque (renderizar, escribir en /tmp, llamar a `lp`), ninguna con tiempo
límite, sin borrar el temporal y sin mirar si CUPS había aceptado el trabajo.

Cuando no hay ninguna impresora configurada —o el servidor no tiene CUPS— no se
da un error: se devuelve el PDF para que el usuario lo imprima desde el
navegador. Así el módulo sirve igual en una instalación sin CUPS.
"""

import logging
import os
import shutil
import subprocess
import tempfile

from odoo import _, api, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

# Un trabajo de impresión no debería tardar más que esto. Sin límite, una
# impresora apagada dejaba el proceso de Odoo esperando para siempre.
TIEMPO_LIMITE = 30


class RepairPrinting(models.AbstractModel):
    _name = "repair.printing"
    _description = "Workshop document printing"

    @api.model
    def _cups_disponible(self):
        """Indica si este servidor puede enviar trabajos a CUPS."""
        return bool(shutil.which("lp"))

    @api.model
    def _renderizar(self, informe_xmlid, registros):
        informe = self.env.ref(informe_xmlid)
        contenido, _tipo = self.env["ir.actions.report"]._render_qweb_pdf(
            informe, registros.ids)
        return contenido

    @api.model
    def _enviar_a_cups(self, contenido, impresora, servidor="", copias=1):
        """Manda un PDF ya generado a la impresora. Devuelve (correcto, aviso)."""
        orden = ["lp"]
        if servidor:
            orden += ["-h", servidor]
        orden += ["-d", impresora]
        if copias and copias > 1:
            orden += ["-n", str(copias)]

        ruta = None
        try:
            with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as temporal:
                temporal.write(contenido)
                ruta = temporal.name
            resultado = subprocess.run(
                orden + [ruta], capture_output=True, text=True,
                timeout=TIEMPO_LIMITE, check=False)
            if resultado.returncode != 0:
                aviso = (resultado.stderr or resultado.stdout or "").strip()
                _logger.warning("CUPS rechazó el trabajo en %s: %s", impresora, aviso)
                return False, aviso or _("CUPS rejected the job.")
            _logger.info("Enviado a %s: %s", impresora, resultado.stdout.strip())
            return True, ""
        except FileNotFoundError:
            return False, _("This server does not have the CUPS «lp» command installed.")
        except subprocess.TimeoutExpired:
            return False, _("Printer %s did not respond within %s seconds.") % (
                impresora, TIEMPO_LIMITE)
        except Exception as error:            # noqa: BLE001 - se informa al usuario
            _logger.exception("Error al imprimir en %s", impresora)
            return False, str(error)
        finally:
            # El temporal se borra siempre: antes se acumulaban en /tmp.
            if ruta and os.path.exists(ruta):
                try:
                    os.unlink(ruta)
                except OSError:
                    _logger.debug("No se pudo borrar el temporal %s", ruta)

    @api.model
    def imprimir(self, informe_xmlid, registros, impresora="", servidor="",
                 copias=1, silencioso=False):
        """Imprime un informe.

        Si hay impresora y CUPS, envía el trabajo y devuelve True. Si no,
        devuelve la acción de descarga del PDF para imprimirlo a mano, salvo
        que se pida 'silencioso', en cuyo caso devuelve False sin molestar.
        """
        if not registros:
            return False

        if not impresora or not self._cups_disponible():
            if silencioso:
                _logger.info(
                    "Sin impresora configurada para %s: no se imprime.", informe_xmlid)
                return False
            return self.env.ref(informe_xmlid).report_action(registros)

        contenido = self._renderizar(informe_xmlid, registros)
        correcto, aviso = self._enviar_a_cups(contenido, impresora, servidor, copias)
        if not correcto:
            if silencioso:
                return False
            raise UserError(
                _("No se pudo imprimir en «%s».\n\n%s\n\nRevisa la impresora en "
                  "Repairs → Branches.") % (impresora, aviso))
        return True
