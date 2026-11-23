# References for the report (opened at the source, Sun 15 Nov 2026)

25 numbered references, every one opened at its primary in this pass, plus a reserve of nine more opened sources at the end. Sources that could not be opened are in `not_opened.md` and must not be cited.

**How they were opened.** Plain HTTPS requests (curl, generic user agent, no personal details), raw page or PDF saved and read as text, between 13:07 and 13:12 PST on 15 Nov 2026. Times come from the `date` command run straight after each batch of requests, so each time is "opened by". No summarising tool was used: every quote below was matched against the raw text.

**Depth.** For arXiv papers, the abstract page was read in full; the body was not opened in this pass. Claims marked "body only" in the record (for example AgentLeak's 31.5% to 2.4% interceptor result) are not supported here; see `not_opened.md`.

---

## (a) The problem: AI scribes and AI advice in clinical visits

**[1]** Fox, S., Markham, L., Lail, R., Karotsieris, M. "One note in three: a verified census of three deployed AI scribes, and the instrument that counted it." arXiv:2608.31017, v1, 31 Aug 2026.
- URL: https://arxiv.org/abs/2608.31017 (abstract page, full)
- Opened: by 13:07 PST, 15 Nov 2026
- Claim the report may rest on it: an audit of three commercial AI scribes on the same 142 consultations (565 notes) found a verified failure in 31.3% of notes (95% interval 27.0 to 35.6); with everything else fixed, the review instruction alone moved the share of candidate errors verified from 9.3% to 79.0%. (The 9.3% and 79.0% are shares of candidate errors, not of notes.)
- Quote: "One note in three (31.3% [27.0, 35.6]) carries a verified failure"
- Venue: cite as arXiv preprint; no venue is listed on the arXiv page.

**[2]** Microsoft. "Dragon Copilot: frequently asked questions" (data use and retention). Microsoft Learn, last updated 27 Jul 2026.
- URL: https://learn.microsoft.com/en-us/industry/healthcare/dragon-copilot/about/faqs
- Opened: by 13:10 PST, 15 Nov 2026
- Claim: a large AI scribe vendor states in its own documentation that it keeps visit audio, transcripts and recognised text for up to 90 days. This is the vendor's statement; nothing on the page lets an outsider check it.
- Quote: "retains audio, recognized text, transcript, and flowsheet value data for up to 90 days"

**[3]** de Marco, H. "Lawsuit claims Sharp HealthCare secretly recorded exam room conversations without patient consent." KPBS Public Media, 11 Dec 2025.
- URL: https://www.kpbs.org/news/health/2025/12/11/lawsuit-claims-sharp-healthcare-secretly-recorded-exam-room-conversations-without-patient-consent
- Opened: by 13:07 PST, 15 Nov 2026
- Claim: a proposed class action filed in San Diego Superior Court alleges that Sharp HealthCare recorded visits with an AI scribe (Abridge) without telling patients, and that chart text said patients had been advised and had consented. These are allegations reported by a news outlet; the complaint itself was not opened, and no court has decided them.
- Quote: "falsely documented that patients had given consent"

**[4]** State of Texas v. Pieces Technologies Inc. "Assurance of Voluntary Compliance" (petition for approval, file-stamped), Office of the Texas Attorney General, Sep 2024.
- URL: https://www.texasattorneygeneral.gov/sites/default/files/images/press/Petition%20for%20Approval%20of%20AVC%20Pieces%20File%20Stamped.pdf
- Opened: by 13:08 PST, 15 Nov 2026 (PDF, read as text)
- Claim: the State alleged that a clinical generative-AI vendor's advertised hallucination rates may have been false or misleading (paras 13 and 14); the assurance requires that any advertised accuracy metric disclose its definition and how it was calculated (para 17); Pieces denies wrongdoing and says it stated its rate accurately (para 15). The denial must be cited beside the allegation every time.
- Quotes: "the meaning or definition of such metric" (para 17); "denies any wrongdoing or liability" (para 15)

**[5]** 45 CFR § 164.528, "Accounting of disclosures of protected health information." Code of Federal Regulations, 2024 edition, via GovInfo (U.S. Government Publishing Office).
- URL: https://www.govinfo.gov/content/pkg/CFR-2024-title45-vol2/xml/CFR-2024-title45-vol2-sec164-528.xml
- Opened: by 13:11 PST, 15 Nov 2026
- Claim: under HIPAA a patient may ask for an accounting of disclosures of their health information for the past six years, but disclosures for treatment, payment and health care operations are excluded, so the handovers inside an AI-assisted visit are generally not on the list the patient can obtain.
- Quote: "except for disclosures: To carry out treatment, payment and health care operations"
- Note: the 2024 annual edition was opened; check the current eCFR text before final submission if the wording matters.

## (b) Prior art: tamper-evident logs, AI observability standards, content provenance

**[6]** Apart Research. "AI x Epistemics Research Sprint" (13 to 15 Nov 2026), sprint page, Track 2: Trust Infrastructure.
- URL: https://apartresearch.com/sprints/ai-x-epistemics-research-sprint-2026-11-13-to-2026-11-15 (live page; also a Wayback Machine copy of 27 Oct, kept outside the repository)
- Opened: by 13:11 PST, 15 Nov 2026
- Claim: the track's question, and its example project naming the OpenTelemetry GenAI conventions and Certificate Transparency as the precedent.
- Quote: "What minimal tamper-evident layer is missing from today's AI observability standards"

**[7]** Laurie, B., Langley, A., Kasper, E. "Certificate Transparency." RFC 6962, IETF, June 2013 (Experimental; obsoleted by RFC 9162, see reserve).
- URL: https://www.rfc-editor.org/rfc/rfc6962.txt
- Opened: by 13:07 PST, 15 Nov 2026
- Claim: Certificate Transparency keeps public, append-only logs built on Merkle trees, so anyone can audit what was logged and detect a log that rewrites its history; it is the precedent for an outside witness whose log only grows.
- Quote: "publicly auditable, append-only, untrusted logs of all issued certificates"

**[8]** Crosby, S. A., Wallach, D. S. "Efficient Data Structures for Tamper-Evident Logging." 18th USENIX Security Symposium, 2009.
- URL: https://www.usenix.org/legacy/event/sec09/tech/full_papers/crosby.pdf
- Opened: by 13:08 PST, 15 Nov 2026 (PDF, read as text)
- Claim: defines tamper-evident logs for the case of an untrusted logger kept honest by auditors, who can demand proof that past events are still present and that the log is consistent with earlier views.
- Quote: "kept honest by a number of auditors who will challenge the logger"
- Note: the USENIX presentation page returned 404; the venue is taken from the conference's own PDF path. Confirm the venue line on the paper's first page before final submission.

**[9]** OpenTelemetry. "Semantic conventions for generative AI systems." open-telemetry/semantic-conventions-genai repository, docs/gen-ai/README.md and gen-ai-spans.md (main branch).
- URL: https://github.com/open-telemetry/semantic-conventions-genai (read via https://raw.githubusercontent.com/open-telemetry/semantic-conventions-genai/main/docs/gen-ai/README.md)
- Opened: by 13:08 PST, 15 Nov 2026
- Claim: the GenAI conventions have status "Development"; they define spans and attributes such as `gen_ai.operation.name`, `gen_ai.provider.name` and `gen_ai.conversation.id`, and message content (`gen_ai.output.messages`, `gen_ai.system_instructions`) is Opt-In. The pages opened define no integrity, signing or witness attribute (absence on the pages opened, not a statement by OpenTelemetry). The conventions moved from the main semantic-conventions repository, whose old page now says "Moved".
- Quote: "Semantic conventions for generative AI systems **Status**: Development"

**[10]** HL7 International. "Resource Provenance." FHIR R5 (v5.0.0), Security Work Group, maturity level 4, Trial Use.
- URL: https://hl7.org/fhir/provenance.html
- Opened: by 13:08 PST, 15 Nov 2026
- Claim: FHIR Provenance records the activity that created or changed a version of a health record resource, with the agents and entities involved; it can carry a signature, but holds no deadline and no outside witness (per the standards table, `report_work/refs/STANDARDS_TABLE.md` and the overnight draft).
- Quote: "activity that created, revised, deleted, or signed a version of a resource"

**[11]** HL7 International. "Resource AuditEvent." FHIR R5 (v5.0.0), Security Work Group, maturity level 4, Trial Use.
- URL: https://hl7.org/fhir/auditevent.html
- Opened: by 13:08 PST, 15 Nov 2026
- Claim: AuditEvent records who did what, when and why; the specification only advises that servers not accept edits or deletes of audit records. That is guidance to servers; nothing in the resource lets an outside party check it.
- Quote: "would not generally accept update or delete operations on the resources"

**[12]** HL7 International, Electronic Health Records Work Group. "AI Transparency on FHIR" implementation guide, v1.0.0-ballot (STU 1 Ballot 1), based on FHIR R4.
- URL: https://hl7.org/fhir/uv/aitransparency/2026Jan/index.html
- Opened: by 13:08 PST, 15 Nov 2026
- Claim: a draft (ballot) guide for marking AI's part in health records with tags, Provenance and Device; its scope excludes validating the AI or its output, and no official version has been published yet.
- Quote: "it is not the intent of this project to endorse, validate, or invalidate"

**[13]** Coalition for Content Provenance and Authenticity (C2PA). "C2PA Technical Specification," version 2.2.
- URL: https://c2pa.org/specifications/specifications/2.2/specs/C2PA_Specification.html
- Opened: by 13:08 PST, 15 Nov 2026
- Claim: content provenance for media binds signed statements (assertions) about how an asset was created and edited; it is the nearest standard for marking AI-made content, written for media assets, not for records that pass through several AI steps. (Version 2.3 is also listed on the page; 2.2 is the one opened.)
- Quote: "cannot do so in a secure, tamper-evident and standardized way across platforms"

**[14]** El Yagoubi, F., Badu-Marfo, G., Al Mallah, R. "AgentLeak: A Benchmark for Internal-Channel Privacy Leakage in Multi-Agent LLM Systems." arXiv:2602.11510, v3, 15 Jun 2026.
- URL: https://arxiv.org/abs/2602.11510
- Opened: by 13:07 PST, 15 Nov 2026
- Claim: across 1,000 scenarios in four domains including healthcare, inter-agent messages leaked private data in 68.8% against 27.2% at the final output, so audits of the final output alone miss 41.7% of violations. (The 41.7% is the abstract's own figure; do not add it to 27.2%.)
- Quote: "output-only audits miss 41.7% of violations"

**[15]** Xia, S., Li, Q., Ehsan, T., Ortiz, J. "TraceFix: Repairing Agent Coordination Protocols with TLA+ Counterexamples." arXiv:2605.07935, v1, 8 May 2026.
- URL: https://arxiv.org/abs/2605.07935
- Opened: by 13:07 PST, 15 Nov 2026
- Claim: the nearest measured prior work to a checked pipeline: agent coordination protocols are verified with the TLA+ model checker TLC and run under a runtime monitor that rejects operations outside the verified topology; in 3,456 runs, topology-monitored execution had the highest completion (89.4% average). Its properties are about coordination, not data flow or deletion (the latter from the record's earlier read of the body; the abstract names deadlock and livelock).
- Quote: "executed under a runtime monitor that rejects out-of-topology coordination operations"

**[16]** Arfelt, E., Basin, D., Debois, S. "Monitoring the GDPR." ESORICS 2019, LNCS 11735, pp. 681 to 699, DOI 10.1007/978-3-030-29959-0_33. Accepted author manuscript, IT University of Copenhagen repository.
- URL: https://researcher.itu.dk/ws/portalfiles/portal/84814983/esorics19.pdf
- Opened: by 13:11 PST, 15 Nov 2026 (PDF, read as text)
- Claim: parts of the GDPR, including the right to erasure as a deadline (data seen deleted within 30 days of a request), were written in metric first-order temporal logic and monitored on a real industry log of 12,151 events about 587 applications, finding actual violations. The erasure violations found were data never deleted, not late deletions.
- Quote: "within 30 days after t, we must observe this data being deleted"

**[17]** Belem, C. G., Wu, S., Yao, H., Steyvers, M., Singh, S., Smyth, P. "From 'May' to 'Is': Certainty Distortion in Language Model Rewriting." arXiv:2606.07951, v2, 15 Sep 2026; accepted at EMNLP 2026 (Main).
- URL: https://arxiv.org/abs/2606.07951
- Opened: by 13:07 PST, 15 Nov 2026
- Claim: language models change the stated certainty of claims when rewriting, in up to 75% of outputs, mostly upward; in medical paraphrasing one model raised certainty in 20% of examples after one pass and 40% after five. This grounds rule 5. (The 75% is the top figure across tasks, not a medical figure.)
- Quote: "claude-haiku-4.5 increases certainty in 20% of examples after a single iteration"

## (c) The three data sets

**[18]** Yim, W., Fu, Y., Ben Abacha, A., Snider, N., Lin, T., Yetisgen, M. "Aci-bench: a Novel Ambient Clinical Intelligence Dataset for Benchmarking Automatic Visit Note Generation." Scientific Data 10, 586 (2023). DOI 10.1038/s41597-023-02487-3. Data: figshare, DOI 10.6084/m9.figshare.22494601; code and data: https://github.com/wyim/aci-bench
- URLs: https://www.nature.com/articles/s41597-023-02487-3 (paper); https://raw.githubusercontent.com/wyim/aci-bench/main/README.md (repository README)
- Opened: by 13:08 PST, 15 Nov 2026
- Claim: ACI-Bench is a public set of doctor-patient visit conversations with their clinical notes, made for research on AI note generation (splits 67 train, 20 validation, three test sets of 40, as the README lists them); article and data are under CC BY 4.0. Cite the Scientific Data article, as the README asks.
- Quote: "published under a Creative Commons Attribution 4.0 International License (CC BY)" (README, License section)

**[19]** Polzak, C., Lozano, A., Sun, M. W., Burgess, J., Zhang, Y., Wu, K., Yeung-Levy, S. "Can Large Language Models Match the Conclusions of Systematic Reviews?" arXiv:2505.22787, v1, 28 May 2025. Dataset: MedEvidence, Hugging Face `clcp/med-evidence`, MIT licence.
- URLs: https://arxiv.org/abs/2505.22787; https://huggingface.co/datasets/clcp/med-evidence (read via the Hugging Face API record and the dataset card)
- Opened: by 13:08 PST, 15 Nov 2026
- Claim: MedEvidence pairs findings from 100 systematic reviews with the studies they rest on, each question carrying the experts' answer and certainty-of-evidence grade; the public file has 284 rows (counted locally in `data/raw/medEvidence.csv`); the dataset card states licence MIT.
- Quote: "a benchmark pairing findings from 100 SRs with the studies they are based on"

**[20]** Feng, J., Patel, V., Heagerty, P., Mai, Y., Sivaraman, V., Vossler, P., Ouyang, J., Jena, A. B. "Expert Evaluation of Clinical AI Tools on Real Point-of-Care Clinical Queries." arXiv:2606.28960, v1, 27 Jun 2026. Dataset: Real-POCQi, Hugging Face `jjfenglab/Real-POCQi`, CC BY 4.0.
- URLs: https://arxiv.org/abs/2606.28960; https://huggingface.co/datasets/jjfenglab/Real-POCQi (API record and dataset card)
- Opened: by 13:08 PST, 15 Nov 2026
- Claim: Real-POCQi holds 620 real point-of-care questions that physicians put to OpenEvidence in June 2026 (filtered for identifying details and lightly rewritten), with stored answers from four AI systems including OpenEvidence (2,480 answers) and 1,156 pairwise physician ratings; licence CC BY 4.0.
- Quote: "620 Real-world Point-Of-Care Queries (Real-POCQi) submitted to the OpenEvidence (OE) platform"

## (d) Methods

**[21]** Lamport, L. "The TLA+ Home Page" (personal TLA+ site, last modified 13 Oct 2025). TLA+ is now maintained by the TLA+ Foundation (https://foundation.tlapl.us/, opened by 13:09 PST).
- URL: https://lamport.azurewebsites.net/tla/tla.html
- Opened: by 13:07 PST, 15 Nov 2026
- Claim: TLA+ is a language for modelling concurrent and distributed systems, with tools (the TLC model checker) that explore every order of events in a model; the project uses it to search the pipeline model for rare-path faults.
- Quote: "a high-level language for modeling programs and systems--especially concurrent and distributed ones"

**[22]** de Moura, L., Bjørner, N. "Z3: An Efficient SMT Solver." Tools and Algorithms for the Construction and Analysis of Systems (TACAS 2008), Springer, March 2008 (LNCS 4963). Software: https://github.com/Z3Prover/z3, MIT licence.
- URL: https://www.microsoft.com/en-us/research/publication/z3-an-efficient-smt-solver/ (Microsoft Research publication page); repository README via https://raw.githubusercontent.com/Z3Prover/z3/master/README.md
- Opened: by 13:09 PST, 15 Nov 2026
- Claim: Z3 is an SMT solver from Microsoft Research, released under the MIT licence; the project uses it to check the formal model's properties.
- Quote: "Z3 is a new and efficient SMT Solver freely available from Microsoft Research"
- Note: the Springer chapter page (DOI 10.1007/978-3-540-78800-3_24) returned a JavaScript challenge and was not read; the volume number LNCS 4963 is not shown on the page opened, so confirm it or drop it.

**[23]** SciPy. `scipy.stats.binomtest` and `BinomTestResult.proportion_ci`, SciPy v1.18.0 manual.
- URL: https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats._result_classes.BinomTestResult.proportion_ci.html (and .../scipy.stats.binomtest.html)
- Opened: by 13:10 PST, 15 Nov 2026
- Claim: the "exact" binomial confidence interval is the Clopper-Pearson method (Clopper and Pearson, Biometrika 26(4), 404 to 413, 1934, as the page cites it); the project's pass rule uses its one-sided reading (`config/design_choices.json`: "exact binomial (Clopper-Pearson), two-sided 95 percent, upper end").
- Quote: "'exact' : Use the Clopper-Pearson exact method"
- Note: the 1934 Biometrika paper itself was not opened (see `not_opened.md`); cite it only as "as cited in [23]" or open it first.

## (e) Hidden instructions that act on a monitoring model

**[24]** Terekhov, M., Panfilov, A., Dzenhaliou, D., Gulcehre, C., Andriushchenko, M., Prabhu, A., Geiping, J. "Adaptive Attacks on Trusted Monitors Subvert AI Control Protocols." arXiv:2510.09462, v2, 2 Mar 2026.
- URL: https://arxiv.org/abs/2510.09462
- Opened: by 13:07 PST, 15 Nov 2026
- Claim: an AI model whose outputs carry prompt injections aimed at the monitoring model consistently evaded diverse LLM monitors on two AI-control benchmarks; protocols that rely on an LLM monitor have it as a central point of failure.
- Quote: "the attacker embeds publicly known or zero-shot prompt injections in the model outputs"

**[25]** Nasr, M., Carlini, N., Sitawarin, C., Schulhoff, S. V., Hayes, J., Ilie, M., Pluto, J., Song, S., Chaudhari, H., Shumailov, I., Thakurta, A., Xiao, K. Y., Terzis, A., Tramèr, F. "The Attacker Moves Second: Stronger Adaptive Attacks Bypass Defenses Against LLM Jailbreaks and Prompt Injections." arXiv:2510.09023, v1, 10 Oct 2025.
- URL: https://arxiv.org/abs/2510.09023
- Opened: by 13:07 PST, 15 Nov 2026
- Claim: adaptive attacks bypassed 12 recent defences against jailbreaks and prompt injection, with attack success above 90% for most; the majority of those defences had originally reported near-zero attack success. (Not "all twelve" and not "above 90% for all".)
- Quote: "the majority of defenses originally reported near-zero attack success rates"

---

## Reserve: also opened this pass, not numbered

Use any of these in place of a numbered one if the report needs it; each was opened at the primary between 13:07 and 13:11 PST.

- Laurie, B., Messeri, E., Stradling, R. "Certificate Transparency Version 2.0." RFC 9162, IETF, Dec 2021 (obsoletes RFC 6962). https://www.rfc-editor.org/rfc/rfc9162.txt. Quote: "The append-only property of each log is achieved using Merkle Trees".
- Sigstore. "Rekor" transparency log overview. https://docs.sigstore.dev/logging/overview/. Claim: a public transparency log of signed software-supply-chain metadata. Quote: "an immutable, tamper-resistant ledger of metadata generated within a software project's supply chain".
- Doximity. "Meet Doximity Scribe." Doximity blog, 24 Jul 2025 (date from the record). https://blog.doximity.com/articles/meet-doximity-scribe (opened by 13:10). Claim: the strictest stated audio policy, not stored. Quote: "We do not store or retain any audio."
- Suki. "Security FAQ." https://developer.suki.ai/documentation/references/faqs/security (opened by 13:10). Quote: "The original audio recording is permanently deleted after 30 days."
- Freed. "HIPAA compliance in AI scribes" FAQ. https://www.getfreed.ai/resources/hipaa-compliance-in-ai-scribes (opened by 13:10). Quote: "deleted upon successful note generation, which happens within 60 seconds".
- Texas Attorney General. Press release, 18 Sep 2024, "first-of-its-kind" settlement with Pieces Technologies. https://www.texasattorneygeneral.gov/news/releases/attorney-general-ken-paxton-reaches-settlement-first-its-kind-healthcare-generative-ai-investigation. Quote: "these metrics were likely inaccurate". Cite with the denial in [4].
- American Medical Association. Physician AI sentiment report (2026 survey, 1,692 physicians, fielded 15 Jan to 2 Feb 2026). https://www.ama-assn.org/system/files/physician-ai-sentiment-report.pdf. Safe wording: 81% report "any awareness or use of AI"; the report's own summary says "Over 80% of physician respondents currently use AI in a professional context". Trust item: "Clear liability frameworks would increase trust in- and adoption of- AI."
- Cirstea, H., Kuppe, M. A., Loillier, B., Merz, S. "Validating Traces of Distributed Programs Against TLA+ Specifications." arXiv:2404.16075, v2, 17 Sep 2024. https://arxiv.org/abs/2404.16075. Quote: "detecting discrepancies between the specifications and the implementations in all cases".
- Greshake, K., Abdelnabi, S., Mishra, S., Endres, C., Holz, T., Fritz, M. "Not what you've signed up for: Compromising Real-World LLM-Integrated Applications with Indirect Prompt Injection." arXiv:2302.12173, v2, 5 May 2023. https://arxiv.org/abs/2302.12173. Quote: "LLM-Integrated Applications blur the line between data and instructions".
- OpenEvidence. Terms of Use, last updated 17 Sep 2026. https://www.openevidence.com/policies/terms. Claim: the provider of the stored answers in [20] may use de-identified and usage data for any lawful purpose consistent with its privacy policy or BAA. Quote: "de-identified data, or customer usage data for any lawful purpose".

## Notes for the writer

- Every number above is from the opened abstract, page or PDF. Body-only figures in the earlier record (AgentLeak's interceptor, TraceFix's fault levels, Belem's per-model table) were not re-opened in this pass.
- Vendor retention lines are the vendors' own statements and are dated by the page; the report should say "states" and give the page date.
- The Sharp matter is an allegation reported by KPBS; the Pieces matter carries the State's allegation and the company's denial together.
