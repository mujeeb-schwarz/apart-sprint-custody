# Cases

`exp1.jsonl` and `exp2.jsonl` are the cases of the two experiments, as the runs used them. They were built by `tools/build_cases.py` from the three public data sets below (see `data/raw/README.md`).

## Data credits

- **ACI-Bench.** Yim, W., Fu, Y., Ben Abacha, A., Snider, N., Lin, T., Yetisgen, M., Scientific Data 10, 586 (2023); https://github.com/wyim/aci-bench. Licence CC BY 4.0 (https://creativecommons.org/licenses/by/4.0/). The texts in `data/cases/` and in the run folders were selected and reformatted from it.
- **MedEvidence.** Polzak, C., Lozano, A., Sun, M. W., Burgess, J., Zhang, Y., Wu, K., Yeung-Levy, S., arXiv:2505.22787 (2025); https://huggingface.co/datasets/clcp/med-evidence. Licence MIT (https://opensource.org/licenses/MIT). The texts in `data/cases/` and in the run folders were selected and reformatted from it.
- **Real-POCQi.** Feng, J., Patel, V., Heagerty, P., Mai, Y., Sivaraman, V., Vossler, P., Ouyang, J., Jena, A. B., arXiv:2606.28960 (2026); https://huggingface.co/datasets/jjfenglab/Real-POCQi. Licence CC BY 4.0 (https://creativecommons.org/licenses/by/4.0/). The texts in `data/cases/` and in the run folders were selected and reformatted from it.

The study texts of the MedEvidence cases were withheld from this copy on Sun 22 Nov 2026, a week after the submission, because the studies stay under their publishers' licences. Each is replaced with a marker such as `[study text withheld: medev:0 pmid:17466514]`; titles and source ids stay. With MedEvidence downloaded into `data/raw/`, `python3 tools/restore_study_texts.py` puts the texts back and checks each file's sha256 against `withheld_study_texts.json` in this folder.
