from datetime import datetime, time, timedelta

from odoo import api, fields, models


class SalePlanningManufactureTrackingService(models.AbstractModel):
    _name = "sale.planning.manufacture.tracking"
    _description = "Demand & Supply Planning - Manufacture Tracking Service"

    @api.model
    def get_kpis(self):
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
        domain = [
            ("date_start", ">=", datetime.combine(date_from, time.min)),
            ("date_start", "<=", datetime.combine(date_to, time.max)),
            ("state", "in", ["confirmed", "progress", "done"]),
        ]
        mos = self.env["mrp.production"].search(domain)

        plan = sum(mos.mapped("product_qty")) if mos else 0.0
        finished_moves = mos.mapped("move_finished_ids")
        move_lines = finished_moves.mapped("move_line_ids")
        result = sum(move_lines.mapped("quantity")) if move_lines else 0.0

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
        workorders = self.env["mrp.workorder"].search([("state", "in", ["ready", "progress", "waiting"])])
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
        today = fields.Date.context_today(self)

        if "date_deadline" in mrp_production._fields:
            deadline_field = mrp_production._fields["date_deadline"]
            cutoff = today if deadline_field.type == "date" else datetime.combine(today, time.min)
            count = mrp_production.search_count(
                [
                    ("date_deadline", "<", cutoff),
                    ("state", "not in", ["done", "cancel"]),
                ]
            )
            return {"count": count}

        count = mrp_production.search_count(
            [
                ("date_start", "<", datetime.combine(today, time.min)),
                ("state", "not in", ["done", "cancel"]),
            ]
        )
        return {"count": count}

    @api.model
    def get_lines_table(self):
        workorders = self.env["mrp.workorder"].search([("state", "in", ["ready", "progress", "done", "waiting"])])
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

        result = []
        for index, row in enumerate(rows.values(), start=1):
            row["no"] = index
            row["target"] = row["plan"]
            row["rate"] = round((row["result"] / row["target"] * 100.0), 2) if row["target"] else 0.0

            if row["rate"] >= 100:
                row["status"] = "green"
            elif row["rate"] >= 80:
                row["status"] = "yellow"
            else:
                row["status"] = "red"

            result.append(row)

        return {"rows": result}
