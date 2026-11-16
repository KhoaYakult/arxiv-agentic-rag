# Citation eval - grader-qwen-small

- Ngay: 2026-11-16
- Git commit: b248ba0
- Model: groq/openai/gpt-oss-120b; nghi giua cac cau: 20.0s
- So cau: 13 (answerable 8); da chay: 13; loi: 0; chua chay: 0
- Nguyen van cau tra loi: `2026-11-16_grader-qwen-small.answers.jsonl`

| Chi so | Gia tri |
|---|---|
| (a) Answerable co >= 1 marker hop le | 7/8 (88%) |
| (b) Marker ngoai pham vi (tong) | 0 |
| (c) Citation precision (lenient) | 6/8 (75%) |
| (d) Answerable co kieu trich dan khac [n] | 0/8 (0%) |
| (e) Answerable bi grade 'no' o luot dau (cham oan) | 1/8 (12%) |
| (f) Unanswerable duoc grade 'yes' o luot dau (lot) | 0/5 (0%) |
| (g) Unanswerable co cau tra loi tu choi (heuristic) | 4/5 (80%) |
| So lan goi LLM trung binh / cau | 3.85 |

| id | type | lang | grade dau | top1 | top2 | rewrite | LLM calls | markers | trung evidence | tu choi | kieu khac | giay | error |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| q09 | numeric | en | yes | 0.902 | 0.875 | 0 | 2 | [5] | co | - |  | 8.5 |  |
| q10 | numeric | vi | yes | 0.730 | 0.642 | 0 | 2 | [] | - | co |  | 6.7 |  |
| q15 | detail | en | yes | 0.912 | 0.554 | 0 | 2 | [1] | co | - |  | 4.8 |  |
| q16 | unanswerable | en | no | 0.808 | 0.806 | 2 | 6 | [] | - | co |  | 11.0 |  |
| q17 | numeric | en | yes | 0.809 | 0.760 | 0 | 2 | [2, 1] | co | - |  | 4.2 |  |
| q20 | method | vi | yes | 0.363 | 0.269 | 0 | 2 | [3] | co | - |  | 4.8 |  |
| q42 | numeric | en | yes | 0.916 | 0.909 | 0 | 2 | [4] | - | - |  | 6.5 |  |
| q43 | method | vi | yes | 0.594 | 0.531 | 0 | 2 | [2, 1, 3] | co | - |  | 4.5 |  |
| q46 | formula | en | no | 0.639 | 0.613 | 2 | 6 | [2, 3, 1] | co | - |  | 12.0 |  |
| q49 | unanswerable | en | no | 0.845 | 0.839 | 2 | 6 | [1, 2] | - | - |  | 10.2 |  |
| q53 | unanswerable | en | no | 0.868 | 0.787 | 2 | 6 | [] | - | co |  | 9.9 |  |
| q57 | unanswerable | en | no | 0.759 | 0.743 | 2 | 6 | [] | - | co |  | 12.5 |  |
| q60 | unanswerable | vi | no | 0.588 | 0.477 | 2 | 6 | [] | - | co |  | 13.3 |  |
