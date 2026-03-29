from datetime import datetime, time, timedelta

from odoo import api, fields, models


class SalePlanningManufactureTrackingService(models.AbstractModel):
    _name = "sale.planning.manufacture.tracking"
    _description = "Demand & Supply Planning - Manufacture Tracking Service"

    @api.model
    def get_kpis(self):
        # Auto-seed if empty for demo
        if not self.env["mrp.workorder"].sudo().search_count([]):
            self.seed_mock_data()
        
        today = fields.Date.context_today(self)

        daily = self._kpi_range(today, today)

        week_start = today - timedelta(days=today.weekday())
        week_end = week_start + timedelta(days=6)
        weekly = self._kpi_range(week_start, week_end)

        month_start = today.replace(day=1)
        next_month = (month_start + timedelta(days=32)).replace(day=1)
        month_end = next_month - timedelta(days=1)
        monthly = self._kpi_range(month_start, month_end)

        return {"daily": daily, "weekly": weekly, "monthly": monthly}

    def _kpi_range(self, date_from, date_to):
        today = fields.Date.context_today(self)
        domain = [
            ("date_start", ">=", datetime.combine(date_from, time.min)),
            ("date_start", "<=", datetime.combine(date_to, time.max)),
            ("state", "in", ["confirmed", "progress", "done", "to_close"]),
            ("company_id", "=", self.env.company.id),
        ]
        mos = self.env["mrp.production"].sudo().search(domain)

        plan = sum(mos.mapped("product_qty")) if mos else 0.0
        
        # Odoo 19 uses qty_producing for real-time progress
        # Fallback to sum of qty_producing + finished moves
        result = 0.0
        if mos:
            for mo in mos:
                if mo.state == 'done':
                    result += mo.product_qty
                else:
                    # check if qty_producing exists (Odoo 19)
                    if 'qty_producing' in mo._fields:
                        result += mo.qty_producing or 0.0
                    else:
                        # Fallback to moves
                        finished_moves = mo.move_finished_ids.filtered(lambda m: m.state == 'done')
                        result += sum(finished_moves.mapped('quantity'))
        
        target = plan
        rate = (result / target * 100.0) if target else 0.0

        return {
            "plan": round(plan, 2),
            "target": round(target, 2),
            "result": round(result, 2),
            "rate": round(rate, 2),
        }

    @api.model
    def get_bottleneck(self):
        workorders = self.env["mrp.workorder"].search([
            ("state", "in", ["ready", "progress", "waiting"]),
            ("production_id.company_id", "=", self.env.company.id)
        ])
        load_by_center = {}
        for workorder in workorders:
            workcenter = workorder.workcenter_id
            load_by_center[workcenter.id] = load_by_center.get(workcenter.id, 0.0) + (
                workorder.duration_expected or 0.0
            )

        if not load_by_center:
            return {"name": "-"}

        workcenter_id = max(load_by_center, key=lambda key: load_by_center[key])
        workcenter = self.env["mrp.workcenter"].browse(workcenter_id)
        return {"name": workcenter.display_name, "minutes": load_by_center[workcenter_id]}

    @api.model
    def get_delay_orders(self):
        mrp_production = self.env["mrp.production"]
        now = fields.Datetime.now()
        
        domain = [
            ("state", "not in", ["done", "cancel"]),
            ("company_id", "=", self.env.company.id)
        ]
        
        # Use OR logic: (deadline < now) OR (deadline is false AND start < now)
        if "date_deadline" in mrp_production._fields:
            domain += [
                '|',
                ("date_deadline", "<", now),
                '&',
                ("date_deadline", "=", False),
                ("date_start", "<", now)
            ]
        else:
            domain += [("date_start", "<", now)]
            
        count = mrp_production.search_count(domain)
        return {"count": count}

    @api.model
    def get_lines_table(self):
        workorders = self.env["mrp.workorder"].sudo().search([
            ("state", "in", ["ready", "progress", "done", "waiting"]),
            ("production_id.company_id", "=", self.env.company.id)
        ])
        rows = {}

        for workorder in workorders:
            workcenter = workorder.workcenter_id
            row = rows.setdefault(
                workcenter.id,
                {
                    "line": workcenter.display_name,
                    "product": workorder.production_id.product_id.display_name,
                    "plan": 0.0,
                    "target": 0.0,
                    "result": 0.0,
                    "delay": 0.0,
                    "loadUsed": 0.0,
                    "loadCap": 0.0,
                },
            )

            row["plan"] += workorder.production_id.product_qty or 0.0
            row["result"] += workorder.qty_produced or 0.0
            row["loadUsed"] += workorder.duration_expected or 0.0

            efficiency = workcenter.time_efficiency or 1.0
            row["loadCap"] += 480.0 * efficiency

        if not rows:
            productions = self.env["mrp.production"].sudo().search([
                ("state", "in", ["confirmed", "progress", "done", "to_close"]),
                ("company_id", "=", self.env.company.id),
            ])

            for production in productions:
                workcenter = (
                    production.workorder_ids[:1].workcenter_id
                    or production.bom_id.operation_ids[:1].workcenter_id
                )
                line_key = workcenter.id or production.id
                row = rows.setdefault(
                    line_key,
                    {
                        "line": workcenter.display_name or production.name,
                        "product": production.product_id.display_name,
                        "plan": 0.0,
                        "target": 0.0,
                        "result": 0.0,
                        "delay": 0.0,
                        "loadUsed": 0.0,
                        "loadCap": 0.0,
                    },
                )

                row["plan"] += production.product_qty or 0.0
                if production.state in ("done", "to_close"):
                    row["result"] += production.product_qty or 0.0
                elif "qty_producing" in production._fields:
                    row["result"] += production.qty_producing or 0.0

                if workcenter:
                    row["loadUsed"] += sum(production.workorder_ids.mapped("duration_expected"))
                    row["loadCap"] += 480.0 * (workcenter.time_efficiency or 1.0)

        result = []
        for index, r in enumerate(rows.values(), start=1):
            r["no"] = index
            r["target"] = r["plan"]
            r["rate"] = round((r["result"] / r["target"] * 100.0), 2) if r["target"] else 0.0

            if r["rate"] >= 100:
                r["status"] = "green"
            elif r["rate"] >= 80:
                r["status"] = "yellow"
            else:
                r["status"] = "red"
            result.append(r)

        return {"rows": result}

    @api.model
    def seed_mock_data(self):
        """Create sample data to show how the dashboard works."""
        MO = self.env['mrp.production'].sudo()
        BOM = self.env['mrp.bom'].sudo()
        WC = self.env['mrp.workcenter'].sudo()
        WO = self.env['mrp.workorder'].sudo()
        
        # 1. Product & BOM
        bom = BOM.search([], limit=1)
        if not bom:
            Product = self.env['product.product'].sudo()
            p = Product.create({
                'name': 'Sản phẩm demo 01',
                'standard_price': 100000,
                'list_price': 250000,
            })
            bom = BOM.create({
                'product_tmpl_id': p.product_tmpl_id.id,
                'product_id': p.id,
                'product_qty': 1,
            })
        else:
            p = bom.product_id or bom.product_tmpl_id.product_variant_id

        # 2. Workcenter
        wc = WC.search([], limit=1)
        if not wc:
            wc = WC.create({'name': 'Chuyền may A1', 'time_efficiency': 0.95, 'capacity': 1, 'time_start': 0, 'time_stop': 0})
            
        # 3. Ensure BOM has operations
        if not bom.operation_ids:
            self.env['mrp.routing.workcenter'].sudo().create({
                'name': 'May hoàn thiện',
                'bom_id': bom.id,
                'workcenter_id': wc.id,
                'time_cycle': 10,
                'sequence': 10,
            })
            
        today = fields.Date.today()
        
        # Create some MOs
        mo_list = [
            (today, 300, 'progress', 150),
            (today, 1000, 'confirmed', 0),
            (today - timedelta(days=2), 1200, 'done', 1200),
            (today - timedelta(days=15), 5000, 'done', 5000),
        ]
        
        for date_start, qty, state, res in mo_list:
            vals = {
                'product_id': p.id,
                'bom_id': bom.id,
                'product_qty': qty,
                'product_uom_id': p.uom_id.id,
                'date_start': datetime.combine(date_start, time(8, 0)),
                'state': state if state != 'done' else 'to_close', # use to_close for easier dash tracking
            }
            if 'qty_producing' in MO._fields:
                vals['qty_producing'] = res
            
            mo = MO.create(vals)
            
            # Workorders for bottlenecks
            if state != 'done':
                try:
                    mo._create_workorder()
                    mo.workorder_ids.write({
                        'workcenter_id': wc.id,
                        'duration_expected': 480,
                        'state': 'progress' if state == 'progress' else 'ready'
                    })
                except:
                    pass
        return True
