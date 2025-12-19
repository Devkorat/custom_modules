
{
    'name': 'WhatsApp Order Integration',
    'version': '18.0.0.0.1',
    'category': 'Sales',
    'summary': 'Integrate Odoo with WhatsApp Business for order placement',
    'description': 'This module integrates Odoo with WhatsApp Business API to allow users to place orders via guided WhatsApp messages.',
    'author': 'ChatGPT',
    'depends': ['base', 'sale', 'contacts'],
    'data': [
        'security/ir.model.access.csv',
        'data/cron.xml',
        'views/whatsapp_session_views.xml',
        'views/res_config_settings_views.xml',
        'views/product_template_views.xml'
    ],
    'installable': True,
    'application': False,
}
