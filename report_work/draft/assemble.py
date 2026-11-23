#!/usr/bin/env python3
"""Number the citations of the report and write its reference list.

    python3 assemble.py REPORT.src.md REPORT.md

In the source, a citation is [@key] or [@key1; @key2]. Keys are numbered in the order they first appear. The line
`<!-- references -->` is replaced by the numbered list. A key that is not in REFS stops the run; a reference that is
never cited is listed on the screen, not in the report.
"""
import os
import re
import sys

# key -> the reference as printed. Every entry was opened at its source on 15 Nov 2026
# (report_work/refs/REFERENCES.md, STANDARDS_TABLE.md, IMPACT_SOURCES.md), except those marked CHECK.
REFS = {
    "vendorpages": "Product pages on how long an AI scribe keeps visit audio, read 15 November 2026. Microsoft, Dragon Copilot frequently asked questions ([learn.microsoft.com](https://learn.microsoft.com/en-us/industry/healthcare/dragon-copilot/about/faqs)); Suki, Security FAQ ([developer.suki.ai](https://developer.suki.ai/documentation/references/faqs/security)); Freed, HIPAA compliance in AI scribes ([getfreed.ai](https://www.getfreed.ai/resources/hipaa-compliance-in-ai-scribes)); Doximity, Meet Doximity Scribe ([blog.doximity.com](https://blog.doximity.com/articles/meet-doximity-scribe)).",
    "camel": "Debenedetti E, Shumailov I, Fan T, Hayes J, Carlini N, Fabian D, Kern C, Shi C, Terzis A, Tramèr F. Defeating prompt injections by design. arXiv:2503.18813, 2025. [arxiv.org/abs/2503.18813](https://arxiv.org/abs/2503.18813)",
    "fides": "Costa M, Köpf B, Kolluri A, Paverd A, Russinovich M, Salem A, Tople S, Wutschitz L, Zanella-Béguelin S. Securing AI agents with information-flow control. arXiv:2505.23643, 2025. [arxiv.org/abs/2505.23643](https://arxiv.org/abs/2505.23643)",
    "ama2026": "American Medical Association, Center for Digital Health and AI. 2026 Physician Survey on Augmented Intelligence. March 2026. [ama-assn.org/system/files/physician-ai-sentiment-report.pdf](https://www.ama-assn.org/system/files/physician-ai-sentiment-report.pdf)",
    "tpmg": "Kaiser Permanente Division of Research. AI-assisted notetaking gains steady support from Kaiser Permanente physicians. 1 April 2025. Reports Tierney AA, Gayre G, Hoberman B, et al. Ambient artificial intelligence scribes: learnings after 1 year and over 2.5 million uses. NEJM Catalyst, 2025, doi:10.1056/CAT.25.0040. [divisionofresearch.kaiserpermanente.org](https://divisionofresearch.kaiserpermanente.org/?p=24811)",
    "gallup2026": "Gallup. Teachers Using AI Say It Frees Up Time for What Matters Most. Walton Family Foundation and Gallup survey of 1,952 US K-12 educators, 28 July to 14 August 2026. [news.gallup.com/poll/715364](https://news.gallup.com/poll/715364/teachers-using-say-frees-time-matters-mostost.aspx)",
    "instructure2026": "Instructure. New Instructure Data Shows K-12 Districts Are Demanding Evidence, Not Just Access to Edtech Tools. Press release on the 2026 Edtech Top 40, 29 June 2026. [instructure.com/press-release](https://www.instructure.com/press-release/new-instructure-data-shows-k-12-districts-are-demanding-evidence-not-just-access)",
    "omb2025": "Office of Management and Budget. 2025 Federal Agency AI Use Case Inventory, with summary as of 13 April 2026. [github.com/ombegov/2025-Federal-Agency-AI-Use-Case-Inventory](https://github.com/ombegov/2025-Federal-Agency-AI-Use-Case-Inventory)",
    "hhsbreach": "US Department of Health and Human Services, Office for Civil Rights. Annual Report to Congress on Breaches of Unsecured Protected Health Information for Calendar Year 2024. [hhs.gov/sites/default/files/breach-report-to-congress-2024.pdf](https://www.hhs.gov/sites/default/files/breach-report-to-congress-2024.pdf)",
    "nong": "Nong P, Platt J. Patients' trust in health systems to use artificial intelligence. JAMA Network Open 8(2):e2460628, 2025. [doi:10.1001/jamanetworkopen.2024.60628](https://doi.org/10.1001/jamanetworkopen.2024.60628)",
    "ab3030": "California Health and Safety Code, section 1339.75 (added by Assembly Bill 3030, Statutes of 2024, chapter 848), in force 1 January 2025. [leginfo.legislature.ca.gov](https://leginfo.legislature.ca.gov/faces/codes_displaySection.xhtml?lawCode=HSC&sectionNum=1339.75)",
    "iso24970": "International Organization for Standardization. ISO/IEC 24970, Artificial intelligence: AI system logging. Catalogue entry, stage 60.00 (International Standard under publication), read 15 November 2026. [iso.org/standard/88723.html](https://www.iso.org/standard/88723.html)",
    "ctsite": "Certificate Transparency. Community site, home page, read 15 November 2026. [certificate.transparency.dev](https://certificate.transparency.dev/)",
    "cenclc": "CEN-CENELEC. Artificial Intelligence (Joint Technical Committee 21), topic page and the work programme of CEN/CLC/JTC 21 linked from it, read 15 November 2026. [cencenelec.eu](https://www.cencenelec.eu/areas-of-work/cen-cenelec-topics/artificial-intelligence/)",
    "apart": "Apart Research. AI x Epistemics Research Sprint, 13 to 15 November 2026, sprint page, Track 2: Trust Infrastructure. [apartresearch.com/sprints/ai-x-epistemics-research-sprint-2026-11-13-to-2026-11-15](https://apartresearch.com/sprints/ai-x-epistemics-research-sprint-2026-11-13-to-2026-11-15)",
    "quiron": "Alcázar-Peral JM, Álvaro-de la Parra JA, Blanco D, Blanco Á, Barrios ME, et al. Real-world evaluation of an ambient AI scribe in Spanish outpatient care after 2.3 million uses: impact on clinician experience, semantic agreement, and workflow efficiency. Frontiers in Digital Health 8:1874919, 2026. [doi:10.3389/fdgth.2026.1874919](https://www.frontiersin.org/journals/digital-health/articles/10.3389/fdgth.2026.1874919/full)",
    "ama": "American Medical Association. 2 in 3 physicians are using health AI, up 78% from 2023. News article on the AMA physician survey, 26 February 2025. [ama-assn.org](https://www.ama-assn.org/practice-management/digital-health/2-3-physicians-are-using-health-ai-78-2023)",
    "fox": "Fox S, Markham L, Lail R, Karotsieris M. One note in three: a verified census of three deployed AI scribes, and the instrument that counted it. arXiv:2608.31017, 2026. [arxiv.org/abs/2608.31017](https://arxiv.org/abs/2608.31017)",
    "hipaa528": "45 CFR § 164.528, Accounting of disclosures of protected health information. Code of Federal Regulations, 2024 edition. [govinfo.gov](https://www.govinfo.gov/content/pkg/CFR-2024-title45-vol2/xml/CFR-2024-title45-vol2-sec164-528.xml)",
    "euaia": "Regulation (EU) 2024/1689 of the European Parliament and of the Council of 13 June 2024 laying down harmonised rules on artificial intelligence (Artificial Intelligence Act), Articles 12, 19 and 26 and Annex III. Official Journal of the European Union, 12 July 2024. [eur-lex.europa.eu](https://eur-lex.europa.eu/legal-content/EN/TXT/HTML/?uri=OJ:L_202401689)",
    "omnibus": "Regulation (EU) 2026/1744 of the European Parliament and of the Council of 8 July 2026 amending Regulations (EU) 2024/1689, (EU) 2018/1139 and (EU) 2023/1230 as regards the simplification of the implementation of harmonised rules on artificial intelligence (Digital Omnibus on AI). Official Journal of the European Union, 24 July 2026. [eur-lex.europa.eu](https://eur-lex.europa.eu/legal-content/EN/TXT/HTML/?uri=CELEX:32026R1744)",
    "ferpa": "34 CFR § 99.32, What recordkeeping requirements exist concerning requests and disclosures? (FERPA regulations). Electronic Code of Federal Regulations, version of 1 November 2026. [ecfr.gov](https://www.ecfr.gov/current/title-34/subtitle-A/part-99/subpart-D/section-99.32)",
    "privacyact": "5 U.S.C. § 552a(c), Accounting of certain disclosures (Privacy Act of 1974). United States Code, 2023 edition. [govinfo.gov](https://www.govinfo.gov/content/pkg/USCODE-2023-title5/html/USCODE-2023-title5-partI-chap5-subchapII-sec552a.htm)",
    "otel": "OpenTelemetry. Semantic conventions for generative AI systems (status: Development). Repository open-telemetry/semantic-conventions-genai, read 15 November 2026. [github.com/open-telemetry/semantic-conventions-genai](https://github.com/open-telemetry/semantic-conventions-genai)",
    "fhirprov": "HL7 International. Resource Provenance. FHIR R5 (v5.0.0), Trial Use. [hl7.org/fhir/R5/provenance.html](https://hl7.org/fhir/R5/provenance.html)",
    "fhiraudit": "HL7 International. Resource AuditEvent. FHIR R5 (v5.0.0), Trial Use. [hl7.org/fhir/R5/auditevent.html](https://hl7.org/fhir/R5/auditevent.html)",
    "fhirevidence": "HL7 International. Resource Evidence. FHIR R5 (v5.0.0), Trial Use. [hl7.org/fhir/R5/evidence.html](https://hl7.org/fhir/R5/evidence.html)",
    "aitfhir": "HL7 International, Electronic Health Records Work Group. AI Transparency on FHIR, implementation guide, continuous build of version 1.0.0 (based on FHIR R4), read 15 November 2026, with its source files ([github.com/HL7/aitransparency-ig](https://github.com/HL7/aitransparency-ig/tree/main/input/fsh)); ballot version 1.0.0-ballot, January 2026. [build.fhir.org/ig/HL7/aitransparency-ig](https://build.fhir.org/ig/HL7/aitransparency-ig/en/index.html)",
    "crosby": "Crosby SA, Wallach DS. Efficient data structures for tamper-evident logging. USENIX Security Symposium, 2009. [usenix.org](https://www.usenix.org/legacy/event/sec09/tech/full_papers/crosby.pdf)",
    "ct": "Laurie B, Langley A, Kasper E. Certificate Transparency. RFC 6962, IETF, 2013. [rfc-editor.org/rfc/rfc6962](https://www.rfc-editor.org/rfc/rfc6962.txt)",
    "sigstore": "Sigstore. Rekor transparency log, overview. [docs.sigstore.dev/logging/overview](https://docs.sigstore.dev/logging/overview/)",
    "c2pa": "Coalition for Content Provenance and Authenticity. C2PA Technical Specification, version 2.2. [c2pa.org](https://c2pa.org/specifications/specifications/2.2/specs/C2PA_Specification.html)",
    "agentleak": "El Yagoubi F, Badu-Marfo G, Al Mallah R. AgentLeak: a benchmark for internal-channel privacy leakage in multi-agent LLM systems. arXiv:2602.11510, 2026. [arxiv.org/abs/2602.11510](https://arxiv.org/abs/2602.11510)",
    "tracefix": "Xia S, Li Q, Ehsan T, Ortiz J. TraceFix: repairing agent coordination protocols with TLA+ counterexamples. arXiv:2605.07935, 2026. [arxiv.org/abs/2605.07935](https://arxiv.org/abs/2605.07935)",
    "gdprmon": "Arfelt E, Basin D, Debois S. Monitoring the GDPR. ESORICS 2019, LNCS 11735, pp. 681 to 699. [doi:10.1007/978-3-030-29959-0_33](https://researcher.itu.dk/ws/portalfiles/portal/84814983/esorics19.pdf)",
    "belem": "Belem CG, Wu S, Yao H, Steyvers M, Singh S, Smyth P. From 'May' to 'Is': certainty distortion in language model rewriting. arXiv:2606.07951, 2026; accepted at EMNLP 2026. [arxiv.org/abs/2606.07951](https://arxiv.org/abs/2606.07951)",
    "acibench": "Yim W, Fu Y, Ben Abacha A, Snider N, Lin T, Yetisgen M. Aci-bench: a novel ambient clinical intelligence dataset for benchmarking automatic visit note generation. Scientific Data 10:586, 2023. [doi:10.1038/s41597-023-02487-3](https://www.nature.com/articles/s41597-023-02487-3)",
    "medevidence": "Polzak C, Lozano A, Sun MW, Burgess J, Zhang Y, Wu K, Yeung-Levy S. Can large language models match the conclusions of systematic reviews? arXiv:2505.22787, 2025. Dataset MedEvidence. [arxiv.org/abs/2505.22787](https://arxiv.org/abs/2505.22787)",
    "realpocqi": "Feng J, Patel V, Heagerty P, Mai Y, Sivaraman V, Vossler P, Ouyang J, Jena AB. Expert evaluation of clinical AI tools on real point-of-care clinical queries. arXiv:2606.28960, 2026. Dataset Real-POCQi. [arxiv.org/abs/2606.28960](https://arxiv.org/abs/2606.28960)",
    "z3": "de Moura L, Bjørner N. Z3: an efficient SMT solver. TACAS 2008. [microsoft.com/en-us/research/publication/z3-an-efficient-smt-solver](https://www.microsoft.com/en-us/research/publication/z3-an-efficient-smt-solver/)",
    "tla": "Lamport L. The TLA+ home page. [lamport.azurewebsites.net/tla/tla.html](https://lamport.azurewebsites.net/tla/tla.html)",
    "scipy": "SciPy. scipy.stats.binomtest and proportion_ci, method 'exact' (Clopper-Pearson). SciPy v1.18.0 manual. [docs.scipy.org](https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats._result_classes.BinomTestResult.proportion_ci.html)",
    "terekhov": "Terekhov M, Panfilov A, Dzenhaliou D, Gulcehre C, Andriushchenko M, Prabhu A, Geiping J. Adaptive attacks on trusted monitors subvert AI control protocols. arXiv:2510.09462, 2025 (version 2, 2026). [arxiv.org/abs/2510.09462](https://arxiv.org/abs/2510.09462)",
    "nasr": "Nasr M, Carlini N, Sitawarin C, Schulhoff SV, Hayes J, et al. The attacker moves second: stronger adaptive attacks bypass defenses against LLM jailbreaks and prompt injections. arXiv:2510.09023, 2025. [arxiv.org/abs/2510.09023](https://arxiv.org/abs/2510.09023)",
    "greshake": "Greshake K, Abdelnabi S, Mishra S, Endres C, Holz T, Fritz M. Not what you've signed up for: compromising real-world LLM-integrated applications with indirect prompt injection. arXiv:2302.12173, 2023. [arxiv.org/abs/2302.12173](https://arxiv.org/abs/2302.12173)",
    "tlatrace": "Cirstea H, Kuppe MA, Loillier B, Merz S. Validating traces of distributed programs against TLA+ specifications. arXiv:2404.16075, 2024. [arxiv.org/abs/2404.16075](https://arxiv.org/abs/2404.16075)",
    "cochrane": "CHECK Schünemann HJ, et al. Chapter 15: Interpreting results and drawing conclusions, table 15.6.b. Cochrane Handbook for Systematic Reviews of Interventions. [training.cochrane.org/handbook/current/chapter-15](https://training.cochrane.org/handbook/current/chapter-15)",
}

CITE = re.compile(r"\[@([a-z0-9_]+(?:\s*;\s*@[a-z0-9_]+)*)\]")


def main(src, dst):
    text = open(src, encoding="utf-8").read()
    order = []

    def repl(m):
        keys = [k.strip().lstrip("@") for k in m.group(1).split(";")]
        nums = []
        for k in keys:
            if k not in REFS:
                sys.exit("unknown citation key: %s" % k)
            if k not in order:
                order.append(k)
            nums.append(order.index(k) + 1)
        return "[" + ", ".join(str(n) for n in sorted(nums)) + "]"

    # <!-- include: path --> takes in a file (path relative to the source); its headings go one level down
    base = os.path.dirname(os.path.abspath(src))

    def include(m):
        path = os.path.join(base, m.group(1).strip())
        body = open(path, encoding="utf-8").read().strip()
        body = re.sub(r"(?m)^(#+) ", lambda h: "#" + h.group(1) + " ", body)
        return body

    text = re.sub(r"<!-- include: (.+?) -->", include, text)
    text = CITE.sub(repl, text)
    lines = ["%d. %s" % (i, REFS[k]) for i, k in enumerate(order, 1)]
    for k in order:
        if REFS[k].startswith("CHECK"):
            print("still to be opened at its source: %s" % k)
    if "<!-- references -->" not in text:
        sys.exit("the line <!-- references --> is missing")
    text = text.replace("<!-- references -->", "\n\n".join(lines))
    open(dst, "w", encoding="utf-8").write(text)
    unused = [k for k in REFS if k not in order]
    print("references: %d cited, %d not used (%s)" % (len(order), len(unused), ", ".join(unused)))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
