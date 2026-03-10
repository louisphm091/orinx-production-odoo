import xmlrpc.client

url = 'http://localhost:8069'
db = 'orinx'
username = 'admin'
password = '1'

common = xmlrpc.client.ServerProxy(f"{url}/xmlrpc/2/common")
uid = common.authenticate(db, username, password, {})
models = xmlrpc.client.ServerProxy(f"{url}/xmlrpc/2/object")

# Check ir.translation for 'Total Supply Demand'
translations = models.execute_kw(db, uid, password, 'ir.translation', 'search_read', [
    [('source', '=', 'Total Supply Demand'), ('lang', '=', 'vi_VN')]
], {'fields': ['source', 'value', 'module', 'type', 'state']})

print(f"Total Supply Demand translations: {translations}")

# Check for menu titles
menus = models.execute_kw(db, uid, password, 'ir.ui.menu', 'search_read', [
    [('name', 'ilike', 'Kế hoạch bán hàng')]
], {'fields': ['name']})
print(f"Menus found with Vietnamese name: {menus}")
