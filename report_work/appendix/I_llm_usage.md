# Appendix I. LLM Usage Statement

I collaborated with AI systems throughout this project. The idea and the key direction were mine, and both were refined in that collaboration.

- **Design.** I set the question, the six rules and the three methods, and I developed the experiment design and the test plan together with a Claude agent. I took the design decisions and filed my own predictions before the run.
- **Building and running.** Claude (Anthropic), working through Claude Code, wrote the code of the test bench, ran the experiments and analysed the results.
- **Inside the experiments.** Claude Haiku 5.5 played the AI steps, Claude Sonnet 5.5 the AI parts of the monitor and the review, and Claude Opus 5.5 the judge. OpenAI's GPT-6.1 wrote the planted texts of the second experiment and the sealed attack ideas and forged the logs of the forger test, a second GPT-6.1 model confirmed the changes for rule 5, and OpenAI's `gpt-6-astra` served as second judge.
- **Checking.** Separate Claude agents that were given no conclusions audited the code before the run and recomputed every reported number from the stored run files afterwards. GPT-6.1 reviewed the experimental work and drafts of this report, and its objections are answered in the text or listed as limits.
- **Writing.** I set the overall structure and direction of the report and gave input and feedback on each draft. Claude drafted the text from the run data and the audits and drew the figures. I reviewed and edited it and take responsibility for every line. Every number was checked against the run files by a script, and every reference was opened at its source on 15 November 2026.

## Agents and AI calls by part of the work

An agent is one separate run of a model on one task. Table I1 counts the agents started from 12 November, before and during the sprint, as the session records stood on Sun 15 Nov at 20:29 Pacific; a few ran after the count.

Table I1. AI agents by part of the work.

<!-- widths: 52,12,36 -->
| Part of the work | Agents | Models |
|---|---|---|
| Research and sources: literature, standards, data sets, numbers on the problem, past sprint reports | 52 | Claude Sonnet 5.5, Opus 5.5 |
| Design and building of the test bench | 46 | mostly Claude Sonnet 5.5; Opus 5.5, Fable 5.2, Haiku 5.5 |
| Audits of the code and of the results | 40 | Claude Opus 5.5, Sonnet 5.5, Fable 5.2 |
| Running the experiments: the first trial on the practice set | 196 | Claude Sonnet 5.5 (121), Haiku 5.5 (75) |
| Data analysis and statistics | 6 | Claude Opus 5.5, Sonnet 5.5 |
| Figures | 7 | Claude Opus 5.5, Sonnet 5.5 |
| Writing and editing | 7 | Claude Opus 5.5 |
| Reviews of the report: judges, readers, facts and reference checks | 37 | Claude Opus 5.5, Sonnet 5.5 |
| Coordination and other | 18 | Claude Opus 5.5, Sonnet 5.5 |
| **Total** | **409** | |

The 196 agents of the fourth row answered the AI steps of the first trial on the practice set. The test runs used no agents: their AI calls went to the models directly (Table I2). One coordinating assistant, on Claude Fable 5.2 and for part of the last evening on Claude Opus 5.5, started the agents and assembled their work.

Table I2. AI calls inside the experiments, by role.

<!-- widths: 46,34,20 -->
| Role | Model | Calls |
|---|---|---|
| AI steps: visit note, plan, note for the patient | Claude Haiku 5.5 | 1,793 |
| Monitor | Claude Sonnet 5.5 | 3,375 |
| Review | Claude Sonnet 5.5 | 3,370 |
| Judge | Claude Opus 5.5 | 7,038 |
| Planted texts | GPT-6.1 | 73 |
| Confirmation of planted texts | GPT-6.1, a second model | 30 |
| Sealed attack ideas | GPT-6.1 | 1 |
| Second judge | `gpt-6-astra` (OpenAI) | 240 |
| Review of the forged logs (forger test) | Claude Sonnet 5.5 | 183 |
| Forged logs (forger test) | GPT-6.1 | 102 |

