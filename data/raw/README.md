# Public data sets (not included)

The bench was built from three public data sets. They are not copied into this repository. Download each one from its own page and keep the licence stated there.

| Data set | What it holds | Licence | Where to get it |
|---|---|---|---|
| ACI-Bench (Yim et al., Scientific Data 10, 586, 2023) | Mock doctor-patient visit conversations with their clinical notes, made for research | CC BY 4.0 | https://github.com/wyim/aci-bench (data also on figshare, DOI 10.6084/m9.figshare.22494601) |
| MedEvidence (Polzak et al., arXiv:2505.22787, 2025) | Questions from 100 systematic reviews, each with the experts' answer and certainty-of-evidence grade | MIT | https://huggingface.co/datasets/clcp/med-evidence |
| Real-POCQi (Feng et al., arXiv:2606.28960, 2026) | 620 point-of-care questions from physicians with stored answers from four AI systems and physician ratings | CC BY 4.0 | https://huggingface.co/datasets/jjfenglab/Real-POCQi |

The code expects this layout (as used in the runs):

    data/raw/aci-bench-main.zip                 the ACI-Bench repository as a zip
    data/raw/aci-bench/aci-bench-main/...       the same repository unpacked
    data/raw/medEvidence.csv                    the MedEvidence file
    data/raw/real-pocqi/questions__train.jsonl  Real-POCQi questions
    data/raw/real-pocqi/answers__train.jsonl    Real-POCQi answers
    data/raw/real-pocqi/ratings__train.jsonl    Real-POCQi ratings

`PREKICKOFF_MANIFEST.txt` lists the sha256 and size of each downloaded file, so a fresh download can be checked against the files used.

The cases the experiments ran on are already built from these sets and are included in `data/cases/`. Rebuilding the cases (`tools/build_cases.py`) also needs `data/retired/visits.jsonl`, the earlier joined list the splits were drawn from, which is not included; the built cases in `data/cases/` are what the runs used. The raw files are needed only to rebuild the cases, to recompute Appendix J (`report_work/analysis/data_appendix.py`), for the tests that load the raw sets, and to put back the MedEvidence study texts that this copy withholds (`python3 tools/restore_study_texts.py`; see `data/cases/README.md`).
