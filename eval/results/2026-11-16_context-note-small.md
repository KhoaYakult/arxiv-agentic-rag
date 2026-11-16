# Citation eval - context-note-small

- Ngay: 2026-11-16
- Git commit: c5bf6eb
- Model: groq/openai/gpt-oss-120b; nghi giua cac cau: 25.0s
- So cau: 8 (answerable 2); da chay: 8; loi: 0; chua chay: 0
- Nguyen van cau tra loi: `2026-11-16_context-note-small.answers.jsonl`

| Chi so | Gia tri |
|---|---|
| (a) Answerable co >= 1 marker hop le | 2/2 (100%) |
| (b) Marker ngoai pham vi (tong) | 0 |
| (c) Citation precision (lenient) | 1/2 (50%) |
| (d) Answerable co kieu trich dan khac [n] | 0/2 (0%) |
| (e) Answerable bi grade 'no' o luot dau (cham oan) | 1/2 (50%) |
| (f) Unanswerable duoc grade 'yes' o luot dau (lot) | 0/6 (0%) |
| (g) Unanswerable co cau tra loi tu choi (heuristic) | 6/6 (100%) |
| So lan goi LLM trung binh / cau | 5.25 |

| id | type | lang | grade dau | top1 | top2 | rewrite | LLM calls | markers | trung evidence | tu choi | kieu khac | giay | error |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| q10 | numeric | vi | yes | 0.730 | 0.642 | 0 | 2 | [3] | - | co |  | 10.0 |  |
| q46 | formula | en | no | 0.639 | 0.613 | 2 | 6 | [1, 2] | co | - |  | 13.8 |  |
| q49 | unanswerable | en | no | 0.845 | 0.839 | 2 | 6 | [1, 2, 5] | - | co |  | 12.8 |  |
| q50 | unanswerable | en | no | 0.817 | 0.803 | 2 | 6 | [] | - | co |  | 19.5 |  |
| q51 | unanswerable | en | no | 0.707 | 0.697 | 2 | 6 | [] | - | co |  | 18.3 |  |
| q53 | unanswerable | en | no | 0.868 | 0.787 | 1 | 4 | [] | - | co |  | 13.4 |  |
| q58 | unanswerable | en | no | 0.771 | 0.732 | 2 | 6 | [] | - | co |  | 11.0 |  |
| q59 | unanswerable | en | no | 0.777 | 0.698 | 2 | 6 | [] | - | co |  | 9.1 |  |
