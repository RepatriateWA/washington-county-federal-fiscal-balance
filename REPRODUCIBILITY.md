# WCFFBP Reproducibility

## Washington County Federal Fiscal Balance Project

The Washington County Federal Fiscal Balance Project (WCFFBP) is designed as a transparent and reproducible research system.

Reproducibility in WCFFBP does not mean that every historical source file can always be downloaded again in exactly the form in which it originally appeared. Federal agencies revise datasets, replace files, alter APIs, change schemas, and retire publication systems.

Instead, WCFFBP seeks to preserve enough information for an independent researcher to determine:

- what source was used;
- when and how it was acquired;
- what transformations were performed;
- what validation was applied;
- what accounting decision was made;
- whether the observation was permitted to enter the fiscal-balance ledger;
- how a published value was calculated; and
- where exact reproduction is no longer possible, why it is not possible.

The objective is not merely to make WCFFBP results repeatable on the original research computer.

The objective is to make them independently auditable.

> **Measure first. Explain later.**

---

## 1. Reproducibility Is Not a Single Test

WCFFBP distinguishes several related forms of reproducibility.

### 1.1 Result reproducibility

Can an independent researcher reproduce a published WCFFBP value from the underlying analytical records and accounting rules?

For a published fiscal-balance value, this means being able to reconstruct the applicable federal inflows and federal outflows and apply the WCFFBP sign convention:

**Federal Fiscal Balance = Federal Inflows to Washington − Federal Outflows from Washington**

### 1.2 Analytical reproducibility

Can an independent researcher reproduce the transformation, reconciliation, allocation, or accounting analysis used for a particular source or component?

Examples include:

- reproducing a federal expenditure component;
- reproducing a federal receipts component;
- testing an overlap classification;
- reproducing a county allocation;
- verifying a statewide control;
- reproducing an extraordinary-funding classification; or
- testing whether an observation satisfies the requirements for ledger inclusion.

### 1.3 Database reproducibility

Can an independent researcher reconstruct the database structures and analytical objects used by WCFFBP?

This includes, as applicable:

- schemas;
- reference tables;
- source-domain tables;
- metadata tables;
- accounting-policy tables;
- analytical views;
- reporting views; and
- validation structures.

### 1.4 Source reproducibility

Can an independent researcher reacquire the upstream source data used by WCFFBP?

This is sometimes possible exactly and sometimes only approximately.

An authoritative agency may subsequently revise a file, replace a download, change an API response, alter a workbook, or remove a historical publication. Therefore, reacquiring a source at a later date does not necessarily reproduce the historical source observation originally used by WCFFBP.

WCFFBP distinguishes source reacquisition from reproduction of the analytical record.

---

## 2. The Reproduction Chain

The intended WCFFBP reproduction chain is:

**Published result → analytical calculation → accounting policy → validation or reconciliation → transformed observation → acquisition record → authoritative source**

The chain can also be followed in the opposite direction:

**Authoritative source → acquisition → transformation → validation or reconciliation → accounting policy → analytical calculation → published result**

Not every source component currently implements every element of this chain in an identical technical form. WCFFBP has developed incrementally, and older source domains may use different structures from newer ones.

The principle, however, is consistent:

> A published number should be traceable backward far enough for another researcher to determine where it came from, what happened to it, and why it was used.

---

## 3. Reproduce a Version, Not an Unqualified `main`

WCFFBP is continuing research.

The repository may change as:

- new source years are added;
- source agencies revise data;
- previously unresolved components are resolved;
- accounting classifications change;
- allocation methods improve;
- errors are identified;
- validation procedures improve; or
- new evidence changes a prior methodological decision.

For this reason, exact replication should identify the specific WCFFBP version being reproduced.

A reproduction record should preserve, where available:

- Git commit hash;
- release or tag;
- WCFFBP version;
- source vintage;
- retrieval date;
- database state or applicable migration level; and
- analytical artifact version.

A result reproduced from a later version of WCFFBP may legitimately differ from an earlier result.

Such a difference is not necessarily a reproduction failure. It may represent a documented methodological or evidentiary change.

---

## 4. Current Development Environment

The principal WCFFBP development environment for DRAFT-1 is:

- Windows;
- PowerShell;
- Python;
- PostgreSQL; and
- Git.

The project has been developed using a Python virtual environment and a local PostgreSQL database.

The repository contains a pinned `requirements.txt` defining the Python package environment used by the project.

Principal dependencies include packages for:

- PostgreSQL access;
- tabular data processing;
- Excel ingestion;
- PDF processing;
- HTTP/API acquisition;
- environment-variable loading; and
- columnar data handling.

The repository itself is the authoritative source for the complete dependency list and pinned package versions.

WCFFBP does not assume that later package releases will behave identically to the versions used during DRAFT-1 development.

---

## 5. Clone the Repository

A researcher should begin from a clean clone of the repository and record the commit being reproduced.

Conceptually:

```powershell
git clone <WCFFBP repository>
cd washington-county-federal-fiscal-balance
git rev-parse HEAD
```

For an exact published release, check out the applicable release tag or commit rather than assuming the current `main` branch represents the historical analytical state.

Before beginning reproduction, record:

```powershell
git status
git rev-parse HEAD
```

A clean working tree provides a useful baseline for distinguishing repository state from subsequent local modifications.

---

## 6. Python Environment

Create and activate a Python virtual environment.

For the Windows/PowerShell development environment used by WCFFBP:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

Install the repository-pinned dependencies:

```powershell
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

A reproducer should record the Python version actually used.

For high-confidence replication, the researcher should also preserve the installed environment after setup, for example:

```powershell
python --version
python -m pip freeze
```

The committed `requirements.txt` is the project dependency specification. A locally generated `pip freeze` is useful as additional reproduction evidence but should not silently replace the committed environment definition.

---

## 7. PostgreSQL Environment

WCFFBP uses PostgreSQL as its principal analytical database.

Database credentials are not stored in the public repository.

The common WCFFBP database configuration uses the following environment variables:

```text
DB_HOST
DB_PORT
DB_NAME
DB_USER
DB_PASSWORD
```

The standard development configuration has used PostgreSQL on the local machine, with port `5432` where not otherwise specified.

A local `.env` file may be used to supply configuration through `python-dotenv`.

### Never commit credentials

The `.env` file is intentionally excluded from Git.

A researcher should create a local `.env` containing their own database credentials. For example:

```text
DB_HOST=localhost
DB_PORT=5432
DB_NAME=<local_database_name>
DB_USER=<local_database_user>
DB_PASSWORD=<local_database_password>
```

The placeholders above must be replaced locally.

No password, API key, token, or other private credential should be committed to the repository.

Some source-specific loaders also recognize conventional PostgreSQL environment-variable names. The source code should be consulted when reproducing a particular loader.

---

## 8. Test the Database Connection

The repository contains a database connection test:

```powershell
python etl\test_connection.py
```

A successful connection should be established before migrations or database-dependent loaders are executed.

Connection success establishes only that Python can communicate with the configured PostgreSQL database. It does not establish that the WCFFBP schema or source data have been loaded correctly.

---

## 9. Database Construction

WCFFBP contains foundational database migrations under:

```text
database/migrations/
```

The migration runner executes migration files in sorted filename order.

The migration mechanism establishes foundational structures such as:

- schemas;
- metadata tables; and
- reference tables.

The repository also contains a much larger chronological SQL history under:

```text
etl/sql/
```

These files document the continuing development of source schemas, accounting controls, reconciliation structures, analytical views, and reporting logic.

### Important distinction

Running the foundational migrations is **not equivalent to reconstructing the complete current WCFFBP database**.

The project developed through a sequence of source acquisitions, loaders, SQL migrations, reconciliation steps, policy decisions, and validation checkpoints.

Accordingly, DRAFT-1 does not claim that a new user can reconstruct the complete research database with one command.

Where a source-domain workflow has an established execution sequence, that sequence should be followed rather than assuming that every SQL file can be indiscriminately executed against an empty database.

---

## 10. Executing SQL

WCFFBP contains a general SQL execution utility.

A SQL file can be executed against the configured database using the repository runner, for example:

```powershell
python scripts\run_sql_file.py <path-to-sql-file>
```

The repository also contains a root-level compatibility copy of the SQL runner.

Researchers should execute SQL files only as part of a documented source-domain or analytical workflow.

The numerical ordering of SQL files records important project development history, but numerical order alone does not necessarily constitute a complete clean-room installation specification.

This distinction is particularly important for migrations that represent:

- corrections;
- policy changes;
- reconciliation decisions;
- replacement views;
- superseded analytical states; or
- source-specific prerequisites.

---

## 11. Source Acquisition

WCFFBP uses multiple authoritative federal and research sources.

Depending on the source, acquisition may occur through:

- public API;
- direct file download;
- agency workbook;
- agency CSV;
- agency ZIP archive;
- PDF publication;
- web download interface; or
- manually preserved historical publication.

Source-specific acquisition code and evidence should be preferred over generic assumptions about how a dataset was obtained.

The repository contains acquisition tooling for multiple source families, including federal economic, tax, expenditure, benefit, health-care, employment, procurement, and assistance data.

See:

- `DATA_SOURCES.md` for the source registry and provenance framework;
- `METHODOLOGY.md` for source-selection and accounting principles; and
- source-specific acquisition, validation, and evidence directories for implementation detail.

---

## 12. API Credentials

Some authoritative sources require an API key.

API credentials are local configuration and are not part of the WCFFBP research record.

For example, BEA acquisition scripts use:

```text
BEA_API_KEY
```

A reproducer must obtain their own valid credential from the applicable source provider and expose it to the acquisition process through the local environment.

WCFFBP acquisition artifacts should record the fact that an authenticated acquisition occurred where relevant, but credentials themselves must not be persisted in manifests, evidence files, logs, or Git history.

A source acquisition that requires a credential is reproducible when another authorized researcher can obtain their own credential and issue the same documented request. Reproducibility does not require sharing the original researcher's credential.

---

## 13. Repository-Preserved and Externally Reproducible Sources

WCFFBP deliberately does not use GitHub as a complete binary mirror of every upstream dataset.

Source material is divided conceptually into three classes.

### Repository-preserved

Selected source artifacts may be committed when their size, provenance value, and redistribution characteristics make repository preservation appropriate.

### Externally reproducible

Large authoritative source acquisitions may be retained in the local research archive but excluded from Git when they can reasonably be reacquired.

For these sources, reproducibility depends on combinations of:

- authoritative source identification;
- acquisition scripts;
- source URLs or endpoints;
- retrieval metadata;
- request parameters;
- checksums;
- manifests;
- schema inventories; and
- validation evidence.

### Citation-only or conservative non-redistribution

Some third-party publications are not redistributed through the repository.

WCFFBP may instead preserve, as appropriate:

- bibliographic citation;
- source location;
- retrieval metadata;
- checksum;
- extraction methodology;
- analytical code;
- derived factual evidence; and
- validation artifacts.

This policy is particularly relevant to third-party research publications used for comparison or methodological review.

The absence of an upstream binary file from Git therefore does not, by itself, indicate missing provenance.

---

## 14. Source Version Drift

An upstream source downloaded today may not be identical to the source downloaded during the original analysis.

Possible causes include:

- revised federal data;
- corrected agency files;
- replacement workbooks;
- API revisions;
- schema changes;
- changed file names;
- historical-series revisions;
- removed publications; or
- altered web interfaces.

Where WCFFBP preserves a checksum for the original source, that checksum provides an identity test.

If a newly acquired file does not match the preserved checksum, the researcher should not silently treat it as the original source.

Instead, the new file should be treated as a different source vintage unless equivalence can be established.

---

## 15. Exact Reproduction Versus Reconstruction

WCFFBP distinguishes **exact reproduction** from **reconstruction**.

### Exact reproduction

Exact reproduction uses the same material source observations, transformations, accounting rules, and analytical version used for the original result.

### Reconstruction

Reconstruction attempts to reproduce the analysis using later-retrieved, revised, substituted, or otherwise nonidentical source material.

Reconstruction can be scientifically valuable.

It should not, however, be represented as exact reproduction when the underlying source observations differ.

A researcher finding a difference between an original WCFFBP result and a later reconstruction should first determine whether the difference arises from:

1. source revision;
2. source vintage;
3. software/environment difference;
4. transformation difference;
5. accounting-policy difference;
6. geographic-allocation difference;
7. time-basis difference; or
8. an error in either analysis.

Differences should be investigated, not automatically interpreted as failures.

---

## 16. ETL and Transformation

WCFFBP separates source acquisition from subsequent transformation wherever practical.

Depending on the source domain, processing may include:

- raw ingestion;
- schema normalization;
- identifier normalization;
- recipient normalization;
- agency linking;
- geographic linking;
- award linking;
- transaction normalization;
- extraordinary-funding classification;
- source-specific semantic interpretation;
- duplicate detection;
- cross-source reconciliation;
- accounting-policy application; and
- geographic allocation.

The precise sequence is source-specific.

Researchers should not infer that the presence of a loader or database table means that its values are authorized for inclusion in the fiscal-balance ledger.

> **Loading is not ledger authorization.**

---

## 17. Observation Grain and Re-Observation

Particular care is required with transaction-oriented federal datasets.

The same underlying transaction, award, recipient, or economic resource may appear:

- in multiple source batches;
- in multiple downloads;
- in multiple reporting systems;
- under multiple administrative identifiers; or
- in both authoritative control data and transaction-level provenance data.

WCFFBP therefore distinguishes source observations from canonical economic observations.

A repeated observation is not automatically a second expenditure.

Reproducers must preserve the distinction between:

- observing a record again; and
- identifying an additional federal dollar.

This is essential to preventing double counting.

---

## 18. Validation and Certification

WCFFBP uses source-specific validation rather than relying on a single universal validation routine.

The repository contains validation scripts for multiple source families and analytical components.

Depending on the domain, validation may test:

- expected row counts;
- expected geographic coverage;
- expected fiscal years;
- uniqueness;
- referential integrity;
- schema structure;
- accounting identities;
- source-control agreement;
- linkage coverage;
- suppression behavior;
- missingness;
- reconciliation closure;
- temporal consistency; and
- geographic consistency.

A successful loader execution is not equivalent to a validation PASS.

Likewise, a validation PASS establishes only the proposition tested by that validation.

---

## 19. The Release Validator

The repository contains:

```text
scripts/validate_release.py
```

This script provides release-level checks for selected foundational components, including:

- reference geography;
- IRS county SOI data;
- IRS state collection data;
- SSA OASDI data; and
- selected database-integrity conditions.

The validator uses explicit PASS/FAIL conditions and terminates unsuccessfully if its tested conditions fail.

It is important not to overinterpret this script.

At DRAFT-1, `validate_release.py` is **not a comprehensive validator of every source family, every accounting decision, or every published WCFFBP component**.

Later-developed domains have their own validation, reconciliation, certification, and evidence routines.

Therefore:

> **`RELEASE VALIDATION PASSED` means that the checks implemented by that validator passed. It does not mean that every proposition in the WCFFBP database has been independently certified by that one script.**

---

## 20. Validation Evidence

WCFFBP preserves important validation outputs as research evidence when they establish material facts about the analysis.

Examples may include evidence demonstrating:

- successful acquisition;
- source completeness;
- schema interpretation;
- linkage coverage;
- reconciliation closure;
- accounting classification;
- suppression behavior;
- geographic attribution;
- overlap treatment;
- control-total agreement; or
- a decision to withhold a component.

These artifacts are not merely execution logs.

Where retained intentionally, they form part of the audit trail.

Conversely, temporary diagnostics that add no evidentiary information beyond committed code need not be preserved indefinitely.

---

## 21. PASS, HOLD, WITHHOLD, and Unresolved States

WCFFBP intentionally permits analytical work to stop.

A component may remain unresolved because the available evidence does not support a defensible accounting or geographic-incidence decision.

This is a reproducibility feature.

An independent researcher should be able to reproduce not only why a dollar was included, but also why a dollar was withheld.

Accordingly, a reproduction attempt should not convert:

- missing to zero;
- suppressed to zero;
- unresolved to included;
- administrative geography to economic incidence;
- incomplete-year data to annual data; or
- an observed transaction to an additive transaction

without an explicit methodological basis.

A reproduced HOLD is a valid reproduction result.

---

## 22. Accounting Policy Must Be Reproduced

Matching source totals is not sufficient to reproduce WCFFBP.

The accounting treatment must also be reproduced.

This includes rules governing:

- preferred accounting sources;
- overlapping sources;
- duplicate exclusions;
- additive inclusion;
- allocation-only use;
- unresolved withholding;
- separate credit measures;
- contingent measures; and
- award-specific or program-specific classifications.

Where an award-specific accounting classification exists, it may take precedence over a broader program-level policy.

Where an explicit program mapping exists, it may determine treatment.

Where neither provides sufficient authority, the observation may remain unresolved rather than being assigned through inference.

The applicable SQL, policy tables, methodology documentation, and validation evidence together define the reproducible accounting state.

---

## 23. One Federal Dollar, One Accounting Path

A central reproducibility invariant is:

> **One Federal Dollar, One Accounting Path.**

A researcher may successfully reproduce every source table and still fail to reproduce WCFFBP if overlapping sources are added together indiscriminately.

Examples of possible overlap include:

- benefit data and assistance transactions;
- agency expenditure controls and procurement transactions;
- authoritative program totals and transaction-level reporting;
- repeated USAspending observations; and
- administrative datasets describing the same underlying federal resource.

WCFFBP retains overlapping observations when they are useful for provenance, reconciliation, classification, or allocation.

Retention does not imply additive ledger treatment.

---

## 24. Time Basis

A reproducible dollar amount must include its time basis.

WCFFBP source observations may be reported by:

- federal fiscal year;
- calendar year;
- tax year;
- report year;
- point-in-time observation;
- monthly period;
- quarterly period; or
- another source-defined reporting period.

A value must not be silently relabeled from one time basis to another.

Where a conversion is authorized, the method should be explicit and reproducible.

Where no defensible conversion has been established, the source observation should retain its native time basis or remain outside the affected ledger calculation.

---

## 25. Geography and Economic Incidence

A reproducible source location is not necessarily a reproducible economic-incidence location.

Federal records may identify:

- recipient location;
- place of performance;
- beneficiary residence;
- administrative office;
- employer location;
- taxpayer filing location;
- state total;
- county total; or
- another geographic concept.

WCFFBP does not automatically equate these concepts.

For county-level reproduction in particular, the researcher must reproduce the geographic attribution or allocation rule, not merely reproduce the source record's geographic field.

Where economic incidence cannot be supported, the value may remain statewide, unallocable, or unresolved.

---

## 26. Suppression, Missingness, and Zero

The following states are not equivalent:

- observed zero;
- missing;
- suppressed;
- unavailable;
- incomplete;
- unresolved;
- withheld; and
- not applicable.

A reproducer must preserve these distinctions.

For example, source suppression must not be converted to zero merely to make an aggregation complete.

Likewise, an incomplete period must not be silently annualized unless an approved methodology authorizes that transformation.

---

## 27. Extraordinary Funding

WCFFBP preserves classifications for extraordinary federal funding, including COVID-related spending and other identifiable extraordinary programs where supported by evidence.

These classifications are analytically distinct from the accounting question of whether the underlying expenditure is additive.

For example, a transaction can be correctly identified as COVID-related and still overlap an authoritative accounting source.

Therefore:

> **Program classification does not override double-counting controls.**

Reproducers should preserve both dimensions.

This permits alternative analytical views, including extraordinary-funding-inclusive and appropriately defined extraordinary-funding-excluded analyses, without rewriting the underlying source record.

---

## 28. Historical Analytical States

WCFFBP preserves historical research artifacts where they provide useful audit evidence.

Some historical SQL, reports, diagnostics, or views may embody:

- an earlier accounting treatment;
- an earlier source interpretation;
- an earlier sign convention;
- a provisional calculation;
- an unresolved question later resolved;
- or an analytical approach later superseded.

These artifacts should not automatically be interpreted as the current WCFFBP Reference Calculation.

Reproduction of a historical artifact means reproducing that historical analytical state.

Reproduction of the current reference calculation requires the current applicable methodology and accounting policy.

---

## 29. Sign Convention

The current public WCFFBP sign convention is:

**Federal Fiscal Balance = Federal Inflows to Washington − Federal Outflows from Washington**

Therefore:

- positive values indicate that attributed federal inflows exceed attributed federal outflows;
- negative values indicate that attributed federal outflows exceed attributed federal inflows; and
- zero indicates equality.

Historical diagnostic artifacts may use the opposite arithmetic.

Those artifacts are preserved as evidence rather than rewritten.

A researcher reproducing a historical artifact should preserve its original arithmetic. A researcher reproducing a current published WCFFBP result should apply the current canonical sign convention.

---

## 30. Published Results

A published WCFFBP result should be treated as the end of an evidentiary chain, not as an isolated spreadsheet value.

Where applicable, reproduction should establish:

1. the published value;
2. its component values;
3. the analytical or ledger records from which those components were derived;
4. the accounting policies governing those records;
5. the validation or reconciliation supporting those policies;
6. the transformed source observations;
7. the acquisition provenance; and
8. the authoritative upstream source.

A published result should not be considered reproduced merely because another calculation happens to arrive at the same number.

The route to the number matters.

---

## 31. Expected Reproduction Standard

WCFFBP does not require independent researchers to use the same computer, directory structure, database credentials, or personal API keys used during development.

A successful independent reproduction should instead produce **substantively equivalent analytical results from the same evidentiary and methodological state**.

Exact byte-for-byte equivalence may be appropriate for:

- preserved source files;
- checksummed artifacts;
- deterministic generated files; or
- fixed release outputs.

Numerical equivalence may be appropriate for:

- database aggregations;
- derived analytical values;
- reconciliations; or
- published calculations.

Logical equivalence may be appropriate for:

- classification outcomes;
- ledger dispositions;
- PASS/HOLD determinations; or
- independently implemented calculations following the same methodology.

The required standard depends on what is being reproduced.

---

## 32. Independent Implementations Are Welcome

Reproducibility does not require use of WCFFBP's own code.

An independent researcher may implement the methodology using:

- another programming language;
- another database;
- another statistical environment;
- another operating system; or
- independently written code.

Such an implementation is particularly valuable because it can test whether the published result depends unintentionally on WCFFBP-specific software behavior.

To compare meaningfully with the WCFFBP Reference Calculation, however, the independent implementation should identify:

- the WCFFBP version being tested;
- source vintages;
- accounting rules;
- time basis;
- geographic basis;
- missing/suppression treatment;
- allocation rules; and
- any methodological deviations.

A different result is not inherently evidence that either calculation is wrong.

A documented difference is an analytical finding to investigate.

---

## 33. Reproducibility and Modification

WCFFBP encourages replication, criticism, extension, and methodological improvement.

Researchers are free to test alternative assumptions and methods consistent with the repository's applicable licensing terms.

However, a materially modified methodology should be identified as such.

A derivative calculation should not be represented as an official **WCFFBP Reference Calculation** when it changes material source selection, accounting treatment, allocation, time basis, or other governing methodology without adoption into the WCFFBP reference methodology.

This distinction protects both openness and interpretability:

- researchers can change the method;
- researchers can challenge the method;
- researchers can improve the method;
- WCFFBP can adopt improvements supported by evidence;
- and readers can still determine which methodology produced which result.

---

## 34. Reproducing a Disagreement

A disagreement with WCFFBP should be made as reproducible as the WCFFBP calculation itself.

The most useful methodological challenge identifies:

- WCFFBP version or commit;
- affected source or component;
- disputed observation or rule;
- alternative source or interpretation;
- executable calculation where practical;
- resulting numerical effect; and
- evidence supporting the proposed change.

This allows disagreement to become part of the research process rather than merely an assertion about the result.

Where a challenge identifies a superior method or corrects an error, WCFFBP should be able to incorporate that change transparently into a later version.

The historical result should remain identifiable as the result produced under the earlier research state.

---

## 35. Known Reproducibility Limitations of DRAFT-1

DRAFT-1 should not be interpreted as a fully automated clean-room build system.

Known structural limitations include:

- there is not yet a single command that acquires every source, constructs the entire database, executes every source-domain workflow, and publishes the final result;
- some historical source material requires manual or source-specific acquisition;
- some large authoritative source files are deliberately not stored in Git;
- third-party publications may be cited without redistribution;
- upstream sources may change after the original acquisition;
- source-domain workflows developed at different stages of the project do not all use identical interfaces;
- some analytical components remain intentionally unresolved;
- some historical artifacts preserve superseded analytical states;
- the current release validator covers selected foundational components rather than the entire modern WCFFBP analytical architecture; and
- exact clean-room reconstruction of every historical research step has not yet been established as a single automated process.

These limitations should not be concealed by simplifying the reproduction instructions.

They define the current boundary of reproducibility and identify opportunities for improvement.

---

## 36. Recommended Reproduction Procedure

For a serious independent review, WCFFBP recommends the following sequence:

1. Identify the WCFFBP release, tag, or commit to be reproduced.
2. Clone that repository state into a clean working directory.
3. Record the Git commit and confirm the initial working-tree state.
4. Create an isolated Python environment.
5. Install the committed dependency versions.
6. Create a local PostgreSQL database.
7. Configure local database credentials without committing them.
8. Test the database connection.
9. Review `DATA_SOURCES.md` for the source families required by the calculation.
10. Reacquire or locate the required source artifacts.
11. Verify source identity against available manifests, metadata, or checksums.
12. Execute the applicable database migrations and source-domain setup.
13. Run the relevant loaders and transformations.
14. Run source-specific validation and certification.
15. Apply the applicable accounting and overlap policies.
16. Reproduce the analytical or ledger components.
17. Apply the applicable time and geographic treatment.
18. Reproduce the published calculation.
19. Compare the result with the corresponding WCFFBP release artifact.
20. Record and investigate every material difference.

A researcher reproducing only one component need not reconstruct unrelated source domains.

The smallest sufficient reproducible pathway is preferable to unnecessary execution of the entire research system.

---

## 37. Reporting a Reproduction

A useful reproduction report should identify at minimum:

```text
WCFFBP version/tag:
Git commit:
Date reproduced:
Operating system:
Python version:
PostgreSQL version:
Source/component reproduced:
Source vintage(s):
Source checksum(s), where available:
WCFFBP result:
Independent result:
Difference:
Validation status:
Methodological deviations:
Notes:
```

This information makes a reproduction itself reproducible.

---

## 38. Troubleshooting Differences

When a reproduced result differs from WCFFBP, investigate the difference systematically.

A useful diagnostic order is:

**Source identity → source version → row population → units → time basis → geography → suppression/missingness → duplicate treatment → overlap treatment → accounting disposition → allocation → aggregation → sign convention**

This ordering helps prevent a downstream numerical difference from being misdiagnosed before its upstream cause is understood.

Do not force a result to match WCFFBP merely because WCFFBP published it.

A reproducibility exercise should be capable of discovering an error in WCFFBP.

---

## 39. Reproducibility Failures Are Evidence

A failed reproduction attempt can itself reveal important information.

Examples include:

- an undocumented dependency;
- a missing source;
- a changed upstream file;
- an implicit manual step;
- an unstable identifier;
- an unrecorded assumption;
- a non-deterministic transformation;
- an undocumented accounting rule; or
- an error in the reference calculation.

Such findings should be documented and corrected rather than hidden.

A project becomes more reproducible by exposing these failures.

---

## 40. Relationship to Other WCFFBP Documentation

This document describes how WCFFBP research can be reproduced and audited.

It should be read together with:

### `README.md`

Defines the project's purpose, scope, research philosophy, and public orientation.

### `DATA_SOURCES.md`

Defines source provenance, source authority, acquisition status, and the relationship between source evidence and accounting use.

### `METHODOLOGY.md`

Defines the governing analytical and accounting principles.

### `DATA_DICTIONARY.md`

Defines the semantic meaning of principal observations, classifications, accounting states, time concepts, geography concepts, and database objects.

### Source-specific evidence

Documents source acquisition, validation, reconciliation, certification, and analytical decisions at a more detailed level.

The documents serve different purposes and should not be treated as substitutes for one another.

---

## 41. Current and Future Reproducibility

WCFFBP reproducibility is itself versioned research.

Future releases may improve reproducibility through:

- more automated acquisition;
- more complete environment specifications;
- unified orchestration;
- additional automated tests;
- broader release validation;
- standardized source-domain interfaces;
- machine-readable manifests;
- automated published-result generation; and
- clean-room reproduction testing.

Such improvements do not invalidate earlier research states.

They make the evidentiary chain easier to reproduce.

---

## 42. The Reproducibility Standard

WCFFBP does not define reproducibility as:

> “Run our code and trust the output.”

The intended standard is stronger:

> **An independent researcher should be able to identify the evidence, understand the transformations, reproduce the applicable accounting decisions, reconstruct the calculation, discover material differences, and explain why the result does or does not agree with WCFFBP.**

Agreement is useful.

**Auditability is essential.**

That is the reproducibility standard of the Washington County Federal Fiscal Balance Project.

**Measure first. Explain later.**
