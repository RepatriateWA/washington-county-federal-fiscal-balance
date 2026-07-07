# Changelog

All notable changes to the Washington County Federal Fiscal Balance project will be documented in this file.

This project follows a milestone-based versioning strategy.

---

# v0.7 – Revenue Foundation Complete (Unreleased)

## Added

### IRS SOI
- Automated county-level IRS SOI importer (2015–2022)
- Dynamic header detection across changing IRS workbook layouts
- Automatic AGI bracket mapping
- Statewide tax liability estimation
- Import validation scripts

### IRS Data Book
- Automated Table 5 importer
- PDF extraction subsystem using pdfplumber
- Excel and PDF unified loader
- Automatic batch import for FY2015–FY2024
- State collections schema
- Validation scripts

### Database
- IRS schema
- County income tax tables
- State collections tables
- Import logging

### Quality
- Release validation script
- Batch import utilities
- Git milestone history

---

# v0.6 – Statewide Tax Liability

## Added

- IRS tax liability columns
- Statewide tax series
- Tax liability validation
- Washington federal receipts estimates

---

# v0.5 – Dynamic IRS Header Scanner

## Added

- Automatic IRS header detection
- Workbook layout abstraction
- Cross-year compatibility

---

# v0.4 – County SOI Importer

## Added

- County IRS SOI ETL
- AGI bracket normalization
- County lookup integration
- Import validation

---

# v0.3 – Reference Database

## Added

- State registry
- County registry
- AGI bracket reference tables

---

# v0.2 – Database Architecture

## Added

- PostgreSQL schemas
- ETL framework
- Logging
- Project structure

---

# v0.1 – Initial Repository

## Added

- Repository initialization
- Documentation
- Development environment