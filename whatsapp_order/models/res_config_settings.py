from odoo import models, fields, api
from werkzeug.urls import url_encode

# sellercentral.amazon.in
# wolpin@woltop.in
# 3vq4q9.cpD

class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    whatsapp_api_key = fields.Char(string='Whatsapp API Key', config_parameter='whatsapp_api_key', readonly=False)
    whatsapp_number = fields.Char(string='Whatsapp Number', config_parameter='whatsapp_number', readonly=False)
    fb_catalog_id = fields.Char(string="FB Catalog ID", config_parameter='fb_catalog_id', readonly=False)
    fb_catalog_access_token = fields.Char(string="FB Catalog Access Token", config_parameter='fb_catalog_access_token', readonly=False)
    google_map_api_key = fields.Char(string="Google Map API Key", config_parameter='google_map_api_key', readonly=False)
