import xmlrpc.client
info = xmlrpc.client.ServerProxy('https://demo.odoo.com/start').start()
# wait, I can just use odoo shell or runner
