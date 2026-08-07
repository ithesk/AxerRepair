# Repair Workshop Manager

Amplía el módulo **Repair** de Odoo con lo que necesita un taller que atiende a
clientes finales: recepción del equipo con su estado, seguimiento para el
cliente, avisos automáticos, firma del presupuesto y alta masiva de equipos.

Probado en **Odoo 17.0 Community**.

## Qué añade

| | |
|---|---|
| **Recepción** | IMEI, código de desbloqueo, tipo de equipo y quince comprobaciones del estado del aparato al entrar. |
| **Portal del cliente** | Página de seguimiento con el historial de estados, protegida por un enlace con token. |
| **Avisos** | Mensaje al cliente en cada cambio de estado, a través de una pasarela de WhatsApp configurable. |
| **Firma digital** | Envío del presupuesto a firmar y registro de la aceptación. |
| **Alta masiva** | Recepción de varios equipos de un mismo cliente escaneando IMEI, uno a uno o pegando una lista. |
| **Sucursales** | Cada reparación pertenece a una localidad, con su impresora de etiquetas y de recibos. |
| **Transferencias** | Movimiento de equipos entre sucursales, con recepción confirmada. |
| **Impresión** | Recibo de entrada, etiqueta de equipo y etiqueta QR. Con CUPS se envían a la impresora; sin él se ofrece el PDF. |
| **Asistente de IA** | Opcional: redacta los mensajes de seguimiento a partir del estado de la reparación. |

## Instalación

Copie la carpeta en su directorio de complementos y actualice la lista de
aplicaciones. Dependencias de Python:

```
requests  qrcode  babel
```

El asistente de IA necesita además `openai`, que solo se importa si el
asistente está activado: sin él, el módulo instala y funciona igual.

## Configuración

Todo en **Ajustes → Taller de reparación**. Cada integración tiene su
interruptor y mientras esté apagada el módulo no llama a ningún servicio
externo.

- **Identidad del taller** — el nombre y el logotipo salen de la ficha de su
  compañía; aquí se indican los enlaces de garantía, ofertas y redes sociales
  que aparecen en recibos y avisos.
- **Avisos por WhatsApp** — dirección de la pasarela y token.
- **Firma digital** — dirección del servicio, token y plantilla.
- **Consulta de IMEI** — proveedor y clave. Estos servicios suelen **cobrar por
  consulta**: revise la tarifa antes de usarlo de forma masiva.
- **Asistente de IA** — clave, modelo e instrucción. Admite proveedores
  compatibles con la API de OpenAI y modelos locales.
- **Sincronización externa** — replica productos y contactos en una segunda
  base de datos Odoo por XML-RPC.
- **Acceso desde fuera** — clave para las aplicaciones que consultan
  reparaciones y secreto del webhook de firma. **Mientras estén vacíos, esos
  accesos permanecen cerrados.**

Antes de imprimir, indique en **Reparaciones → Localidades** el servidor CUPS y
el nombre de las colas de impresión de cada sucursal.

## Direcciones públicas

| Dirección | Quién entra |
|---|---|
| `/repair/track/<id>/<token>` | El cliente, con el enlace que se le envía. |
| `/repair/label/<id>/<token>` | Igual, para imprimir su etiqueta. |
| `/repair/bulk/<id>/<token>` | Resumen de varios equipos del mismo cliente. |
| `/api/get-repair-orders` | Aplicaciones externas, con la clave de la API. |
| `/api/send-message` | Igual. |
| `/docuseal/webhook/` | El servicio de firma, con el secreto compartido. |

Ninguna devuelve el código de desbloqueo del equipo.

## Pruebas

```bash
odoo -d BASE -u axer_repair --test-enable --test-tags=/axer_repair
```

Veintidós pruebas que cubren el ciclo completo de una reparación, la generación de
los informes, la impresión sin CUPS instalado y el rechazo de las direcciones
públicas sin credencial.

## Autoría

Desarrollado por **Pablo Holguín** — [Innovación Tecnológica SK](https://www.innovaciontecnologica.com.do).

Copyright © 2024-2026 Pablo Holguín.

## Licencia

AGPL-3. Consulte el fichero `LICENSE`.

Este programa es software libre: puede redistribuirlo y modificarlo según los
términos de la GNU Affero General Public License, en su versión 3 o posterior.
Se distribuye sin ninguna garantía.
