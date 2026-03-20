# Odoo Module Installation Guide - Orinx Production

This document provides a detailed, step-by-step guide to installing the custom modules from the `orinx-production-odoo` repository into a fresh Odoo system.

## Repository Information
- **GitHub URL:** [https://github.com/louisphm091/orinx-production-odoo](https://github.com/louisphm091/orinx-production-odoo)

List of modules included in this source code:
- `pos_theme_swift` (Configuration and interface for POS Swift)
- `dms` / `dms_field` / `dms_user_role` (Document Management System Integration)
- `fashion_forecast`
- `product_images_import`
- `sale_planning`
- `web_editor_media_dialog_dms`

---

## Deployment Steps

### Step 1: Clone the source code to the Odoo server

SSH into the server containing your Odoo source code. Navigate to the directory where your custom addons are stored and clone the repository.

For example, if you want to save the source code in the `/home/ubuntu/orinx/` directory, run the following commands:

```bash
cd /home/ubuntu/orinx/
git clone https://github.com/louisphm091/orinx-production-odoo.git
```

*(Note: If the repository is private, you will need to enter your GitHub Username and Password or a Personal Access Token).*

### Step 2: Install Python libraries (If any)

Before starting, check if these modules require any specific Python libraries (usually listed in a `requirements.txt` file).
If so, run:
```bash
pip3 install -r /home/ubuntu/orinx/orinx-production-odoo/requirements.txt
```

### Step 3: Declare the directory to Odoo using `addons_path`

Odoo needs to know where your code directory is located to load it into the system. Open your Odoo configuration file (usually `odoo.conf` or `/etc/odoo/odoo.conf`) using a text editor (e.g., vi, nano).

Find the `addons_path` line and **append the absolute path** to the `orinx-production-odoo` directory you just cloned. The paths are separated by commas `,`.

For example:
```ini
[options]
; ... other configurations
addons_path = /home/ubuntu/orinx/odoo/addons,/home/ubuntu/orinx/orinx-production-odoo
```

### Step 4: Restart the Odoo service

After altering the config file, you must restart Odoo for it to recognize the new directory path.
Depending on how you run Odoo, the restart command might be:

- **Running via systemd:**
  ```bash
  sudo systemctl restart odoo
  ```
- **Running directly from command line / tmux:**
  Press `Ctrl+C` to terminate the process and re-run the Odoo start command (ensure you pass the config file):
  ```bash
  ./odoo-bin -c /path_to_your/odoo.conf
  ```

### Step 5: Update Apps List

After Odoo restarts, it hasn't installed your module just yet. Now, perform the following actions on the browser interface:

1. Log into Odoo using an account with Administrator privileges (e.g., `admin`).
2. Turn on **Developer Mode** by navigating to *Settings*, scrolling to the very bottom, and clicking *Activate the developer mode*.
3. Open the **Apps** menu.
4. On the top menu bar, click on **Update Apps List**.
5. A popup will appear; click the **Update** button.

### Step 6: Search and Install

1. Still on the **Apps** screen, remove the *Apps* filter in the search bar (click the 'x' to clear the word *Apps*).
2. Enter the names of the modules present in `orinx-production-odoo` to search. For example: type `pos_theme_swift` or `fashion_forecast`.
3. The interface will show the corresponding results. Click **Install** or **Activate** on the respective module cards.
4. The installation process will start and the system may auto-refresh the page once finished. Repeat this step for the other modules if necessary.

> [!TIP]
> If you wish to install via the Command Line Interface (CLI) for speed and accuracy, you can use the `-i` or `-u` flag when starting the Odoo command. For example, to install the `pos_theme_swift` module for the first time:
> ```bash
> ./odoo-bin -c /path/odoo.conf -i pos_theme_swift -d name_of_db
> ```

---

## Troubleshooting

- **Module does not appear in the list:** Ensure the path in `addons_path` within `odoo.conf` is correct, restart Odoo, and **make certain** you have executed the *Update Apps List* action.
- **Permission denied error when cloning source code:** Check Git repository access permissions, or your SSH keys configuration on the server.
- **ImportError when installing or running Odoo:** The server is missing a Python library. Check what libraries the module needs to import (for example: `requests`, `pytz`, etc.) and use the command `pip3 install library_name` to resolve it.
- **Read/Write file log permissions:** Ensure the OS user running Odoo (e.g., `odoo` or `ubuntu`) has full read/write access to the `orinx-production-odoo` folder. Use `sudo chown -R ubuntu:ubuntu /home/ubuntu/orinx/orinx-production-odoo` if necessary.
