The original 24-case baseline remains untouched. Two cases have ambiguous gold wording:
- astronomy-scope originally claimed **confirmed** existence, while evidence explicitly denied confirmation. CONTRADICTED is defensible for confirmation status. The revised case asks about existence instead.
- law-jurisdiction originally said **only** Westland, which can negate Eastland applicability. The revised source explicitly states that Eastland is unaddressed.
These are changed inputs, not improved model predictions. Original failures remain recorded; revised-suite results must be reported separately. Neither original ambiguous case establishes a model accuracy failure.

The historic 56-case corpus also contains two gold-label defects exposed by stricter review. Original raw runs retain their original gold labels; audited runs use a separately versioned corpus:
- original-relation_holdout: “larger” does not specify population versus area. Corrected expected label UNVERIFIED; no claim wording was changed.
- new-new_negation: failure to detect **above a reporting limit** does not exclude detection below it. Corrected expected label UNVERIFIED. EPA distinguishes detection and quantitation limits: https://www.epa.gov/n-steps-online/data-considerations and https://www.epa.gov/sites/default/files/2018-10/documents/nrsa1819_lom_v1.1_june2018_clean.pdf .
These adjudications change the benchmark, not the predictions. Prior 56/56 was expected-label agreement on an imperfect corpus and cannot establish factual accuracy. Report original and audited results distinctly.

A further new-case gold correction applies to archaeology-attribution: the claim is about the inscription **proving** construction, and the evidence explicitly denies that it can establish construction. Its proper label is CONTRADICTED for proof status; this does not disprove King N built the temple. Original and intermediate UNVERIFIED gold runs remain preserved. This is the same distinction as the historic “trial proved” case.
