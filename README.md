# Orinx Production System: Deployment & Baseline Guide

This guide provides the necessary steps to deploy the **Orinx Manufacturing & Planning** modules onto a new Odoo 19 environment.

## 1. System Requirements
- **OS**: Ubuntu 22.04 LTS or higher
- **Database**: PostgreSQL 14+
- **Python**: 3.10+
- **Node.js**: 18+ (for asset processing)

## 2. Odoo 19 Base Installation

First, prepare the environment and clone the Odoo 19 source code:

```bash
# Install system dependencies
sudo apt update && sudo apt upgrade -y
sudo apt install python3-pip python3-dev python3-venv \
    libxml2-dev libxslt1-dev zlib1g-dev libsasl2-dev \
    libldap2-dev build-essential libssl-dev libffi-dev \
    libmysqlclient-dev libjpeg-dev libpq-dev libjpeg8-dev \
    liblcms2-dev libwebp-dev node-less -y

# Clone Odoo 19
mkdir ~/orinx && cd ~/orinx
git clone https://github.com/odoo/odoo.git --depth 1 --branch 18.0 odoo # Note: Use branch 18.0 or 19.0 when available
```

## 3. Clone Custom Modules

Clone the Orinx production repository into the `~/orinx` directory:

```bash
cd ~/orinx
git clone https://github.com/louisphm091/orinx-production-odoo.git
```

## 4. Environment Setup

Create a virtual environment and install Python dependencies:

```bash
cd ~/orinx
python3 -m venv venv
source venv/bin/activate

# Install Odoo base requirements
pip install -r odoo/requirements.txt

# Install custom requirements (if any)
# pip install pandas requests ...
```

## 5. Configuration (`odoo.conf`)

Create a configuration file to point to both the Odoo base addons and the Orinx custom addons:

```ini
[options]
admin_passwd = your_admin_password
db_host = 127.0.0.1
db_port = 5432
db_user = orinx
db_password = your_db_password
addons_path = /home/ubuntu/orinx/odoo/addons, /home/ubuntu/orinx/orinx-production-odoo
```

## 6. Database Initialization

```bash
# Ensure PostgreSQL user 'orinx' exists exists
sudo -u postgres createuser -s orinx

# Run Odoo to initialize the database and install modules
./odoo/odoo-bin -c odoo.conf -d orinx-manufacturing -i sale_planning,pos_theme_swift,fashion_forecast
```

## 7. Key Features & Implementation Notes

### Multi-Company Isolation
The system follows strict multi-company data isolation. When creating or querying data (Forecasts, Branches, Employees), ensure:
- Users are assigned to the correct company.
- Backend queries use `("company_id", "=", self.env.company.id)`.
- Dashboard calculations (Delays, Bottlenecks) are scoped to the active company.

### UI Customization (Navbar)
The navbar has been customized with the Orinx logo and black-themed icons. If the icons appear white after a deploy:
1. Ensure `sale_planning/static/src/scss/web_style.scss` is loaded.
2. Force a hard refresh (`Ctrl + F5`) to clear the Odoo asset bundle cache.

### Manufacturing Dashboards
- **Delayed Orders**: Logic uses `Datetime.now()` to detect late orders (Deadline passed or Start Date passed without completion).
- **Bottlenecks**: Aggregates `mrp.workorder` load by Work Center for the active company.

## 8. Development Maintenance

To apply updates from the repository:
```bash
cd ~/orinx/orinx-production-odoo
git pull
# Restart Odoo with -u to update modules
~/orinx/odoo/odoo-bin -c ~/orinx/odoo.conf -u sale_planning
```

---
*Support Contact: AI Programming Assistant (Orinx Project)*
