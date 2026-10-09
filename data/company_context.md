# Company context (Northwind)
- Internal finance system: http://127.0.0.1:5000  (login page /login, user `admin`, password `admin123` - sandbox account)
- Vendor invoices arrive as files in the `invoices/` folder. Filenames are scan numbers and say nothing about vendor or date.
- Procedure to record a vendor invoice: open "Add invoice" in the portal; use the vendor name as written on the invoice;
  amount = the total payable as a plain number; due date in YYYY-MM-DD.
- "Latest" invoice means the most recent invoice DATE (not due date, not file order).
- Never mark an invoice paid unless the user explicitly asked.
