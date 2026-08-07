# AxerRepair

Módulo de Odoo para la gestión de un taller de reparación de dispositivos:
móviles, tabletas, relojes y portátiles.

| | |
|---|---|
| **Módulo** | `axer_repair` |
| **Versión** | 17.0.1.0.0 |
| **Licencia** | AGPL-3 |
| **Autor** | Pablo Holguín — [Innovación Tecnológica SK](https://www.innovaciontecnologica.com.do) |

## Instalación

Añada este repositorio a su `addons_path` y actualice la lista de aplicaciones:

```
addons_path = /ruta/a/AxerRepair,/otras/rutas
```

Dependencias de Python: `requests`, `qrcode`, `babel`.

## Documentación

La descripción completa de lo que hace el módulo, cómo se configura cada
integración y qué direcciones publica está en
[`axer_repair/README.md`](axer_repair/README.md).

## Pruebas

```bash
odoo -d BASE -u axer_repair --test-enable --test-tags=/axer_repair
```
