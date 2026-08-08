# -*- coding: utf-8 -*-
{
    'name': 'Axer Repair',
    'version': '19.0.1.0.0',
    'summary': 'Portal de cliente, avisos, firma digital y reparaciones masivas',
    'description': """
Axer Repair — gestión de taller de reparación
=============================================

Amplía el módulo *Repair* de Odoo con las herramientas que necesita un taller
que atiende a clientes finales:

* **Portal del cliente**: seguimiento del estado de su equipo en tiempo real.
* **Avisos automáticos**: notificación al cliente en cada cambio de estado
  mediante una pasarela de WhatsApp configurable.
* **Firma digital**: solicitud de firma del presupuesto y del acta de entrega.
* **Recepción masiva**: alta de varios equipos en una sola operación.
* **Componentes y averías**: catálogo de piezas y etiquetas de incidencia.
* **Transferencias internas**: movimiento de equipos entre ubicaciones.
* **Etiquetas QR** e informes de recepción y entrega.
* **Asistente de IA** (opcional): redacción de los mensajes de seguimiento.

Todas las integraciones externas son opcionales y se configuran desde
*Ajustes → Taller de reparación*.
""",
    'author': 'Pablo Holguín',
    'maintainer': 'Pablo Holguín',
    'website': 'https://www.innovaciontecnologica.com.do',
    'license': 'AGPL-3',
    'category': 'Services/Repair',
    'depends': [
        'base',
        'mail',
        'repair',
        'portal',
        'product',
    ],
    'external_dependencies': {
        'python': ['requests', 'qrcode', 'babel'],
    },
    'data': [
        # seguridad
        'security/ir.model.access.csv',
        'security/axer_repair_rules.xml',
        # datos
        'data/cron_jobs.xml',
        'data/cron_jobs2.xml',
        'data/data_transf.xml',
        'data/data_repair.xml',
        'data/components.xml',
        # asistentes: definen acciones que las vistas referencian,
        # por eso se cargan antes que ellas
        'wizards/repair_message.xml',
        'wizards/updatebot.xml',
        'wizards/verification.xml',
        # vistas
        'views/res_config_settings_views.xml',
        'views/repair_views.xml',
        'views/repair_analysis_views.xml',
        'views/portal_header.xml',
        'views/portal_my_repairs.xml',
        'views/portal_templates.xml',
        'views/product_template_inherited_view.xml',
        'views/repair_location_views.xml',
        'views/printer_selection_wizard_view.xml',
        'views/transf.xml',
        'views/bulk_wizard.xml',
        'views/bulk_web.xml',
        'views/extesiones.xml',
        'views/repair_components_views.xml',
        # informes
        'report/repair_reports.xml',
        'report/repair_reports2.xml',
        'report/repair_reports4.xml',
        'report/report_transf.xml',
        'report/repair_templates_repair_order.xml',
        'report/repair_templates_repair_order2.xml',
        'report/repair_templates_repair_order4.xml',
        'report/qr_label.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'axer_repair/static/src/js/common.js',
            'axer_repair/static/src/js/common_issues_widget_template.xml',
            'axer_repair/static/src/js/common_issues_widget.css',
            'axer_repair/static/src/js/botoform.css',
            'axer_repair/static/src/js/quickbudgetwidget.js',
            'axer_repair/static/src/js/quick.css',
            'axer_repair/static/src/js/mobiledate.js',
            'axer_repair/static/src/js/mobile.xml',
            'axer_repair/static/src/js/date.css',
        ],
    },
    # Portada del catálogo: la primera imagen de 'images' es la que
    # se muestra como miniatura en el listado de aplicaciones.
    'images': ['static/description/banner.png'],
    'installable': True,
    'application': False,
    'auto_install': False,
}
