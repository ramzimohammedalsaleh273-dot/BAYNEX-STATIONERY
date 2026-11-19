# BAYNEX ERP Expansion — Phase 02

## Purpose

Turn the current stationery ERP foundation into a cohesive, production-oriented desktop ERP experience. The target is functional and usability parity with established ERP products such as ONYX in the workflows relevant to stationery, libraries, and print centers. BAYNEX must remain an independently implemented product: do not copy proprietary source code, assets, or claim pixel-identical reproduction.

## Starting point

- Base commit: `fca0392c08dd12f3dfc80499e996dba306e27b50`.
- Existing implementation includes catalog, warehouses/inventory, sales, POS, purchases, accounting, treasury, and party subledgers.
- Existing UI is a set of PySide6 dialogs with a shared stylesheet and basic table helpers.
- Existing UI audit is `docs/ONYX_UI_PARITY_AUDIT.md`.
- The previous phase-02 acceptance document describes the earlier catalog phase; this expansion is a new scope and must not be confused with that completed historical phase.

## Workstreams

### 1. UI foundation and consistency
- Establish a consistent application shell, navigation, page headers, command bars, search/filter rows, data tables, detail panels, status bars, dialogs, and validation messages.
- Standardize spacing, typography, field sizing, table row density, numeric alignment, date/currency formatting, keyboard navigation, focus states, and RTL behavior.
- Add reusable table models/delegates and filter/sort behavior where appropriate; avoid duplicated per-screen styling.
- Review every existing screen and migrate it to the shared design system without breaking workflows.

### 2. Master data
- Company and branch settings.
- Customers, suppliers, supplier/customer groups.
- Product groups and subgroups, item types, units and unit conversions.
- Multiple barcodes per item/unit, price lists, item images and supplementary attributes.
- Warehouses and warehouse-account mappings.

### 3. Inventory
- Opening balances, receipts, issues, transfers and transfer receiving.
- Stock adjustments, physical counts, variance posting and movement inquiry.
- Reorder levels, item/warehouse balances and stock valuation.
- Preserve immutable posted movements and auditable reversal workflows.

### 4. Sales and POS
- Sales invoices, returns, customer selection, sales representatives, discounts, tax configuration, payment allocation and document status.
- POS cashier workflow, suspended/resumed tickets, shift/cashier controls, barcode-first entry, split tender, receipt printing and reprints.
- Validate stock, payment and accounting effects atomically.

### 5. Purchasing
- Purchase invoices and returns, supplier balances, payment allocation.
- Additional charges/landed cost, discounts, free quantities and foreign purchases where supported by accounting policy.
- Clear handling of overpayment: reject it or record the excess as a supplier credit/advance; never silently display a negative amount as an ordinary remaining balance.

### 6. Accounting and treasury
- Chart of accounts, journal entries, ledgers, trial balance and financial statements.
- Cashboxes, banks, receipts, payments, internal transfers and bank reconciliation.
- Customer/supplier subledgers and settlement allocation.
- Financial periods, closing controls and auditable corrections.

### 7. Governance and operations
- Users, roles and granular permissions.
- Audit trail for sensitive actions.
- Backup/restore with verification, database integrity checks and safe migrations.
- Printing/export and a distributable Windows build.
- Clear offline-first behavior and single-device SQLite limitations documented.

### 8. Reporting
- Inventory balances, movement and valuation.
- Sales, purchases, returns, margin and cashier reports.
- Customer/supplier statements and aging.
- Cash/bank and accounting reports with date, branch, warehouse and party filters where applicable.

## Required acceptance gates

A screen is not accepted merely because it opens. For every screen:
1. Open/navigation and RTL/layout checks.
2. Add/edit/deactivate/search/filter tests as applicable.
3. Validation and duplicate-prevention tests.
4. Persistence across restart.
5. Inventory/accounting side effects and atomic rollback tests where applicable.
6. Permission tests once authorization is implemented.
7. Print/export tests where applicable.
8. Automated tests and Windows CI.
9. Manual Windows acceptance with screenshots and documented results.

For every posted document, verify the document, inventory ledger, party ledger, treasury ledger and general ledger agree. Use isolated test data/database; never run destructive acceptance scenarios against the user's live database.

## Delivery rules

- Work only on `work/phase-02-erp-expansion-2026-11-19`.
- Do not modify or merge into `main`.
- Do not overwrite user-local changes or discard stashes.
- Make small reviewable commits and run the full test suite after each coherent workstream.
- Do not claim complete ONYX parity, hardware validation, or production readiness without evidence.
- If a workflow depends on external hardware (barcode scanner/printer), separate software-level tests from physical-device acceptance.
