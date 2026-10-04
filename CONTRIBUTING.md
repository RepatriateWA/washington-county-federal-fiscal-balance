# Contributing to the Washington County Federal Fiscal Balance Project

The Washington County Federal Fiscal Balance Project (WCFFBP) is an open,
reproducible research project.

Replication, criticism, corrections, alternative methods, additional data
sources, and methodological improvements are welcome.

The purpose of contribution is not to defend a particular estimate of
Washington's fiscal relationship with the federal government. The purpose is
to improve the quality, transparency, reproducibility, and completeness of
the measurement.

**Measure first. Explain later.**

---

## 1. What Contributions Are Welcome

Useful contributions include:

- identifying an error in source interpretation;
- identifying a missing federal receipt or expenditure;
- identifying double counting or potential overlap between sources;
- proposing a better authoritative source;
- improving acquisition or ETL code;
- improving validation procedures;
- improving geographic attribution or allocation methods;
- identifying inappropriate assumptions about economic incidence;
- identifying time-basis inconsistencies;
- identifying suppression, missing-data, or completeness problems;
- reproducing an existing WCFFBP calculation independently;
- proposing an alternative reproducible methodology;
- improving documentation, citations, or provenance;
- identifying a limitation that has not been adequately disclosed;
- extending the framework to additional years, programs, jurisdictions,
  or accounting components.

A contribution does not need to agree with an existing WCFFBP result.

---

## 2. Finding an Error Is a Contribution

WCFFBP is designed to make errors discoverable.

A reproducible demonstration that a source was misinterpreted, a transaction
was double counted, an allocation was unjustified, a transformation was
incorrect, or a calculation was wrong strengthens the project when the
research record is corrected transparently.

Corrections should not erase the analytical history that preceded them.
Where practicable, WCFFBP preserves the earlier research state, documents
the correction, and records the improved methodology in subsequent versions.

The objective is not to make the project appear infallible.

The objective is to make its results progressively harder to dispute.

---

## 3. No Predetermined Result

WCFFBP does not evaluate a method according to whether it makes Washington's
federal fiscal balance more positive or more negative.

A proposed change should be evaluated according to the quality of its
evidence and methodology.

A method is not correct because it produces a result favorable to a particular
interpretation of Washington's relationship with the federal government.

A method is not incorrect because it changes an existing WCFFBP result.

Likewise, agreement with a WCFFBP result does not establish that an
independent method is correct.

The conclusions are products of the methodology. They are not inputs to it.

---

## 4. The Preferred Form of a Methodological Challenge

The most useful challenges identify the specific part of the analytical chain
being questioned.

Where possible, identify:

1. the source or dataset;
2. the observation, program, transaction, award, or population involved;
3. the applicable year or accounting period;
4. the current WCFFBP treatment;
5. the reason that treatment may be incorrect or incomplete;
6. the evidence supporting a different treatment;
7. the expected effect of the proposed change; and
8. a reproducible way to test the proposition.

A challenge does not need to arrive with a complete replacement methodology.

Evidence that demonstrates that the existing treatment cannot be supported is
itself useful.

---

## 5. Source Standards

WCFFBP generally prefers authoritative primary sources.

Examples include administrative data, official statistical publications,
official APIs, agency reports, government financial records, and other
first-party federal or state sources.

Secondary research can be extremely useful for:

- identifying relevant source families;
- understanding federal accounting systems;
- discovering methodological alternatives;
- comparing results;
- identifying omissions; and
- diagnosing disagreements.

Secondary research does not automatically become an accounting control.

The authority of a source, the authority of an accounting treatment, and the
authority to assign a dollar geographically are separate questions.

See `DATA_SOURCES.md` for the project's source and provenance framework.

---

## 6. Reproducibility

Whenever practicable, a proposed analytical change should be reproducible by
another researcher.

Useful supporting material may include:

- source URLs or API endpoints;
- retrieval dates;
- source-file names;
- checksums;
- acquisition scripts;
- SQL;
- Python code;
- transformation logic;
- validation output;
- reconciliation tables; and
- citations to relevant source documentation.

Not every contribution requires software.

A clearly documented manual source observation may be valuable when the
underlying source cannot reasonably be acquired programmatically.

The important requirement is that another researcher can understand what was
done and, where practicable, independently verify it.

See `REPRODUCIBILITY.md` for the project's broader reproducibility standard.

---

## 7. Accounting Before Addition

The appearance of a federal dollar in a dataset does not automatically give
that dollar permission to enter the fiscal-balance ledger.

Before a component is treated as additive, WCFFBP may need to determine:

- what the observation measures;
- whether it represents an obligation, outlay, payment, expenditure, receipt,
  credit, or another accounting concept;
- whether another source already represents the same economic event;
- whether the time basis is compatible with the calculation;
- whether the geographic attribution is justified; and
- whether the observation is complete enough for the proposed use.

Potential overlap should be reconciled before addition.

Similarity of program names is not sufficient evidence of duplication.

Appearance in separate federal reporting systems is not sufficient evidence
that two observations are economically distinct.

---

## 8. Unresolved Evidence Is an Acceptable Result

Contributors should not manufacture completeness.

If available evidence does not establish whether a component is additive,
duplicative, geographically attributable, complete, or otherwise suitable
for the ledger, the appropriate result may be:

**unresolved**

or

**withheld pending reconciliation**

A missing value should not silently become zero.

A suppressed observation should not silently become zero.

A partial-year observation should not silently become a full-year estimate.

An unresolved component should not be forced into the calculation merely to
complete a table.

Explicit uncertainty is preferable to unsupported precision.

---

## 9. Time and Geography Matter

WCFFBP works with source systems that may report by:

- federal fiscal year;
- calendar year;
- tax year;
- reporting year;
- payment period;
- performance period; or
- another source-specific time basis.

These concepts should not be silently relabeled as equivalent.

Likewise, administrative geography does not necessarily establish economic
incidence.

Recipient address, place of performance, beneficiary residence, taxpayer
address, employer location, and place of work may answer different questions.

A statewide accounting source does not automatically provide authority for a
county allocation.

Contributions involving time conversion or geographic allocation should make
those assumptions explicit.

---

## 10. Extraordinary Federal Funding

COVID-19 and other extraordinary federal funding can materially affect
historical comparisons.

WCFFBP therefore attempts to preserve relevant classifications so that
analyses can distinguish extraordinary funding where the evidence permits.

Contributors should preserve such provenance rather than removing unusual
transactions simply because they complicate interpretation.

The same principle applies to other identifiable extraordinary funding
streams.

---

## 11. Historical Research States

WCFFBP is versioned research.

Earlier analytical artifacts may contain:

- provisional classifications;
- superseded assumptions;
- incomplete source coverage;
- earlier sign conventions;
- unresolved accounting treatments; or
- methods later replaced by stronger evidence.

Such artifacts are not necessarily errors that should be deleted.

They may be part of the audit trail.

When methodology changes, the preferred practice is to preserve the historical
evidence while clearly identifying the current treatment.

Do not silently rewrite historical evidence merely to make it conform to the
latest methodology.

---

## 12. The WCFFBP Reference Methodology

WCFFBP distinguishes between the open research framework and the project's
official Reference Methodology.

Researchers are encouraged to:

- reproduce WCFFBP;
- challenge WCFFBP;
- modify its methods;
- test alternative assumptions;
- extend the framework; and
- publish independent results.

An independent or modified analysis may accurately describe itself as
"based on WCFFBP," "derived from WCFFBP," or similar language when
appropriate under the applicable license.

A materially modified analysis should not be represented as the official
**WCFFBP Reference Calculation** unless the relevant methodology has been
adopted into the WCFFBP research record.

This distinction is intended to preserve provenance, not to discourage
independent work.

The project owns its reference methodology; it does not own the question.

---

## 13. Adoption of Methodological Changes

A proposed method does not become part of the WCFFBP Reference Methodology
merely because it has been submitted.

Before adoption, a material change may require:

1. source verification;
2. methodological review;
3. reproducibility review;
4. overlap or reconciliation analysis;
5. validation against relevant controls;
6. evaluation of effects on prior years or components;
7. documentation of known limitations; and
8. incorporation into the versioned research record.

When an improvement is adopted, WCFFBP should document the change sufficiently
for another researcher to determine what changed and why.

Material changes to the Reference Methodology should be associated with an
identifiable repository version or commit.

---

## 14. Disagreement Is Not a Failure of Reproduction

Two careful researchers can obtain different results because they made
different defensible decisions about:

- source selection;
- accounting boundaries;
- time basis;
- overlap;
- geographic attribution;
- economic incidence;
- suppression;
- missing data; or
- treatment of unresolved observations.

A useful disagreement identifies where the analytical paths diverge.

When reporting a result that differs from WCFFBP, contributors are encouraged
to identify the earliest material point of divergence rather than reporting
only the final numerical difference.

That makes disagreement auditable.

---

## 15. Code Contributions

Code contributions should favor clarity and auditability over unnecessary
complexity.

Where applicable:

- avoid hard-coding analytical results that can be derived from source data;
- distinguish acquisition, transformation, validation, reconciliation, and
  reporting logic;
- preserve source values before transformation;
- make units explicit;
- make time bases explicit;
- make geographic assumptions explicit;
- avoid silent imputation;
- avoid silent annualization;
- avoid silent sign changes;
- avoid destructive modification of source evidence; and
- include validation appropriate to the materiality of the change.

A technically successful script is not, by itself, evidence that the resulting
accounting treatment is correct.

---

## 16. Documentation Contributions

Documentation improvements are welcome.

Particularly useful contributions include:

- clearer explanations of methodology;
- missing citations;
- corrections to source descriptions;
- clearer definitions;
- identification of ambiguous terminology;
- improved instructions for reproduction; and
- clearer disclosure of limitations.

Documentation should distinguish established facts from analytical judgments,
provisional treatments, and unresolved questions.

---

## 17. Submitting a Contribution

GitHub issues are appropriate for:

- questions;
- suspected errors;
- source suggestions;
- methodological challenges;
- reproducibility problems;
- documentation problems; and
- proposed research extensions.

Pull requests are appropriate when a contributor has a concrete change to
code, documentation, validation, or another repository artifact.

For material analytical changes, please explain:

- what is being changed;
- why;
- what evidence supports the change;
- which years or components are affected;
- whether published or historical results may change; and
- how another researcher can verify the change.

Small corrections do not require an elaborate submission.

The amount of supporting evidence should be proportionate to the significance
of the proposed change.

---

## 18. Security and Sensitive Information

Do not submit:

- API keys;
- passwords;
- authentication tokens;
- private credentials;
- personal identifying information that is not appropriate for publication;
  or
- other secrets.

Use environment variables or other appropriate local credential-management
methods for credentials required by acquisition scripts.

If sensitive information is discovered in the repository or its history,
please report the issue without reproducing the secret in a public issue.

---

## 19. Third-Party Material

Not every source used by WCFFBP is owned by WCFFBP or may be redistributed
under the same terms as WCFFBP's original code and documentation.

Contributors should respect applicable rights and redistribution conditions
for third-party material.

Where redistribution is inappropriate, preserve reproducibility through
appropriate combinations of:

- citations;
- authoritative source locations;
- retrieval metadata;
- checksums;
- acquisition instructions;
- extraction methodology; and
- derived factual evidence where appropriate.

Do not assume that the repository's license grants rights to third-party
material.

---

## 20. Scope of Review

WCFFBP welcomes both narrow and broad review.

A reviewer does not need to understand the entire project to make a useful
contribution.

A correction to one source field, one program classification, one county
allocation, one SQL expression, one citation, or one sentence of documentation
can improve the research record.

Conversely, researchers are welcome to attempt a complete independent
reproduction of the framework.

Both forms of scrutiny are valuable.

---

## 21. Research Culture

WCFFBP asks contributors and reviewers to separate three questions:

1. **What does the evidence show?**
2. **What accounting treatment does the evidence support?**
3. **What conclusions, if any, should be drawn from the resulting measurement?**

The repository is principally concerned with the first two.

Political, policy, and normative interpretations may exist outside the
technical project, but they should not determine how evidence is classified
inside it.

The strongest contribution is one that makes the measurement more accurate,
more transparent, more reproducible, or more clearly bounded.

---

## 22. Standard for Success

A successful contribution does not have to preserve the existing result.

It should make it easier for an independent researcher to determine:

- what evidence was used;
- what decision was made;
- why that decision was made;
- how the calculation was performed;
- what uncertainty remains; and
- where reasonable researchers may disagree.

WCFFBP welcomes scrutiny because scrutiny is part of the methodology.

**The objective is not to produce a particular answer. It is to make the
answer progressively harder to dispute.**

**Measure first. Explain later.**