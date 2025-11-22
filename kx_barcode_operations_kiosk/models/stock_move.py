# -*- coding: utf-8 -*-

from odoo import models, fields, api


class StockMove(models.Model):
    _inherit = 'stock.move'

    barcode_scanned = fields.Boolean(
        string='Scanned via Kiosk', 
        default=False,
        help='Indicates if this move was processed through barcode kiosk'
    )
    last_scan_time = fields.Datetime(string='Last Scan Time')

    def mark_as_scanned(self):
        """Mark move as scanned"""
        self.write({
            'barcode_scanned': True,
            'last_scan_time': fields.Datetime.now(),
        })