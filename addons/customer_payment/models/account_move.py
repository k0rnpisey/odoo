from odoo import api, fields, models


class AccountMove(models.Model):
    _inherit = 'account.move'

    # Field 1: Current invoice total
    cp_invoice_amount = fields.Monetary(
        string='Invoice Amount',
        compute='_compute_running_balance_fields',
        currency_field='currency_id',
        help='Total amount of this invoice'
    )

    # Field 2: Previous invoices total (same customer, same year, before this date)
    cp_previous_invoices_total = fields.Monetary(
        string='Previous Invoices Total',
        compute='_compute_running_balance_fields',
        currency_field='currency_id',
        help='Total of all invoices for this customer in the same year before this invoice date'
    )

    # Field 3: Cumulative invoice total (Field 1 + Field 2)
    cp_cumulative_invoice_total = fields.Monetary(
        string='Cumulative Invoice Total',
        compute='_compute_running_balance_fields',
        currency_field='currency_id',
        help='Sum of this invoice and all previous invoices in the same year'
    )

    # Field 4: Total payments from payment entries
    cp_total_payments = fields.Monetary(
        string='Total Payments',
        compute='_compute_running_balance_fields',
        currency_field='currency_id',
        help='Sum of all payment entries from customer payment tracking'
    )

    # Field 5: Remaining balance (Field 3 - Field 4)
    cp_remaining_balance = fields.Monetary(
        string='Remaining Balance',
        compute='_compute_running_balance_fields',
        currency_field='currency_id',
        help='Outstanding balance: Cumulative invoices minus total payments'
    )

    @api.depends('partner_id', 'invoice_date', 'amount_total', 'move_type')
    def _compute_running_balance_fields(self):
        """Compute running balance fields for customer invoices"""
        for record in self:
            # Only compute for customer invoices
            if record.move_type not in ['out_invoice', 'out_refund']:
                record.cp_invoice_amount = 0.0
                record.cp_previous_invoices_total = 0.0
                record.cp_cumulative_invoice_total = 0.0
                record.cp_total_payments = 0.0
                record.cp_remaining_balance = 0.0
                continue

            # Field 1: Current invoice amount
            record.cp_invoice_amount = record.amount_total

            # Field 2: Previous invoices in same year, before this date
            if record.invoice_date and record.partner_id:
                year = record.invoice_date.year
                date_start = fields.Date.from_string(f'{year}-01-01')

                previous_invoices = self.env['account.move'].search([
                    ('partner_id', '=', record.partner_id.id),
                    ('move_type', 'in', ['out_invoice', 'out_refund']),
                    ('state', '=', 'posted'),
                    ('invoice_date', '>=', date_start),
                    ('invoice_date', '<', record.invoice_date),
                    ('id', '!=', record.id),  # Exclude current invoice
                ])

                # Sum previous invoices (credit notes subtract)
                record.cp_previous_invoices_total = sum(
                    inv.amount_total if inv.move_type == 'out_invoice' else -inv.amount_total
                    for inv in previous_invoices
                )
            else:
                record.cp_previous_invoices_total = 0.0

            # Field 3: Cumulative total
            record.cp_cumulative_invoice_total = (
                record.cp_invoice_amount + record.cp_previous_invoices_total
            )

            # Field 4: Total payments from payment entries
            if record.invoice_date and record.partner_id:
                year = record.invoice_date.year

                # Find ALL customer_payment records for this customer/year
                customer_payments = self.env['customer.payment'].search([
                    ('partner_id', '=', record.partner_id.id),
                    ('year', '=', year),
                ])

                if customer_payments:
                    # Sum payment entries from ALL records, up to and including this invoice date
                    payment_entries = self.env['payment.entry'].search([
                        ('payment_id', 'in', customer_payments.ids),
                        ('payment_date', '<=', record.invoice_date),
                    ])
                    record.cp_total_payments = sum(payment_entries.mapped('amount'))
                else:
                    record.cp_total_payments = 0.0
            else:
                record.cp_total_payments = 0.0

            # Field 5: Remaining balance
            record.cp_remaining_balance = (
                record.cp_cumulative_invoice_total - record.cp_total_payments
            )
