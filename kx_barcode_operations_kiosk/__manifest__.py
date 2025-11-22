# -*- coding: utf-8 -*-
{
    'name': 'Barcode Operations Kiosk',
    'version': '18.0.1.0.0',
    'category': 'Inventory/Inventory',
    'summary': 'Barcode scanning kiosk for warehouse operations',
    'description': """
        Barcode Operations Kiosk
        ========================
        
        This module provides a kiosk-style barcode interface for warehouse operations:
        
        Key Features:
        -------------
        * Touch-friendly kiosk interface for barcode scanning
        * Support for receipts, deliveries, internal transfers, returns, and scrap
        * Real-time inventory updates
        * Batch and lot number tracking
        * User authentication via barcode
        * Mobile and tablet responsive design
        * Audio and visual feedback for scans
        * Session tracking and reporting
        
        Supported Operations:
        --------------------
        - Incoming Shipments (Receipts)
        - Outgoing Shipments (Deliveries)
        - Internal Transfers
        - Return Orders
        - Scrap Operations
        
        Compatible with standard GS1 barcodes and custom formats.
    """,
    'author': 'Your Company',
    'website': 'https://www.yourcompany.com',
    'license': 'LGPL-3',
    'depends': [
        'base',
        'stock',
        'product',
        'mail',
        'web',
    ],
    'data': [
        'security/security.xml',
        'security/ir.model.access.csv',
        'data/barcode_kiosk_data.xml',
        'views/barcode_kiosk_views.xml',
        'views/barcode_kiosk_session_views.xml',
        'views/res_config_settings_views.xml',
        'views/menu_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'kx_barcode_operations_kiosk/static/src/css/barcode_kiosk.css',
            'kx_barcode_operations_kiosk/static/src/js/barcode_handler.js',
            'kx_barcode_operations_kiosk/static/src/js/barcode_kiosk.js',
            'kx_barcode_operations_kiosk/static/src/xml/barcode_kiosk_templates.xml',
        ],
    },
    'images': ['static/description/icon.png'],
    'installable': True,
    'application': True,
    'auto_install': False,
}