from odoo import models, fields
import requests
import logging

_logger = logging.getLogger(__name__)


class ProductProduct(models.Model):
    _inherit = 'product.product'
    
    fb_catalog_product_id = fields.Char(string="Facebook Catalog Product ID")

    def upload_products_to_facebook(self):
        catalog_id = self.env['ir.config_parameter'].sudo().get_param('fb_catalog_id')
        access_token = self.env['ir.config_parameter'].sudo().get_param('fb_catalog_access_token')
        
        products = self.search([('fb_catalog_product_id', '=', False)], limit=50)
        
        for product in products:
            payload = {
                "retailer_id": product.default_code,
                "name": product.name,
                "description": product.description or product.name,
                "image_url": f"https://74917c23419f53e4a34f7ffe3c85e25e.serveo.net/web/image?model=product.product&field=image_128&id={product.id}&unique=1726486822000",  # Make sure this URL is publicly accessible
                "price": int(product.list_price * 100),
                "currency": self.env.company.currency_id.name,
                "availability": "in stock",
                "condition": "new",
                # "brand": product.brand_id.name if product.brand_id else "",
            }
            
            response = requests.post(
                f"https://graph.facebook.com/v15.0/{catalog_id}/products",
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Content-Type": "application/json"
                },
                json=payload
            )
            
            res_json = response.json()
            print(">>>>>>>>>>>> %s" % res_json)
            if 'id' in res_json:
                product.fb_catalog_product_id = res_json['id']
            else:
                product.fb_catalog_product_id = product.default_code
                # _logger.error(f"Failed to upload product {product.id}: {res_json}")
