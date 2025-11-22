# -*- coding: utf-8 -*-

from odoo import models, fields, api


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    # Kiosk Settings
    kiosk_enable_sound = fields.Boolean(
        string='Enable Sound Alerts',
        config_parameter='kx_barcode_operations_kiosk.enable_sound',
        default=True,
        help='Play sound alerts on successful/failed scans'
    )
    
    kiosk_auto_validate = fields.Boolean(
        string='Auto-validate Operations',
        config_parameter='kx_barcode_operations_kiosk.auto_validate',
        default=False,
        help='Automatically validate operations when all items are scanned'
    )
    
    kiosk_session_timeout = fields.Integer(
        string='Session Timeout (minutes)',
        config_parameter='kx_barcode_operations_kiosk.session_timeout',
        default=30,
        help='Automatically close sessions after this period of inactivity'
    )
    
    kiosk_allow_overscanning = fields.Boolean(
        string='Allow Over-scanning',
        config_parameter='kx_barcode_operations_kiosk.allow_overscanning',
        default=False,
        help='Allow scanning more than expected quantity'
    )
    
    kiosk_show_product_image = fields.Boolean(
        string='Show Product Images',
        config_parameter='kx_barcode_operations_kiosk.show_product_image',
        default=True,
        help='Display product images in kiosk interface'
    )
    
    kiosk_require_location_scan = fields.Boolean(
        string='Require Location Scan',
        config_parameter='kx_barcode_operations_kiosk.require_location_scan',
        default=False,
        help='Require scanning location before products for internal transfers'
    )