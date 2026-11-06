# Citation eval - gate-data-run1

- Ngay: 2026-11-07
- Git commit: 4e125e5
- Model: groq/openai/gpt-oss-120b; nghi giua cac cau: 25.0s
- So cau: 36 (answerable 21); da chay: 10; loi: 0; chua chay: 26
- Nguyen van cau tra loi: `2026-11-07_gate-data-run1.answers.jsonl`
- LUU Y: dung som vi het quota (RateLimitError) o cau q19; 26 cau chua chay. Mau so ben duoi la so cau da chay.

| Chi so | Gia tri |
|---|---|
| (a) Answerable co >= 1 marker hop le | 8/9 (89%) |
| (b) Marker ngoai pham vi (tong) | 0 |
| (c) Citation precision (lenient) | 7/9 (78%) |
| (d) Answerable co kieu trich dan khac [n] | 0/9 (0%) |
| (e) Answerable bi grade 'no' o luot dau (cham oan) | 1/9 (11%) |
| (f) Unanswerable duoc grade 'yes' o luot dau (lot) | 0/1 (0%) |
| (g) Unanswerable co cau tra loi tu choi (heuristic) | 1/1 (100%) |
| So lan goi LLM trung binh / cau | 2.80 |

| id | type | lang | grade dau | top1 | top2 | rewrite | LLM calls | markers | trung evidence | tu choi | kieu khac | giay | error |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| q09 | numeric | en | yes | 0.902 | 0.875 | 0 | 2 | [5] | co | - |  | 5.0 |  |
| q10 | numeric | vi | no | 0.730 | 0.642 | 2 | 6 | [] | - | co |  | 9.6 |  |
| q11 | method | en | yes | 0.719 | 0.658 | 0 | 2 | [1, 2, 3] | co | - |  | 3.2 |  |
| q12 | method | vi | yes | 0.284 | 0.213 | 0 | 2 | [3, 1] | co | - |  | 3.9 |  |
| q13 | definition | en | yes | 0.720 | 0.483 | 0 | 2 | [1] | co | - |  | 2.6 |  |
| q14 | formula | en | yes | 0.800 | 0.180 | 0 | 2 | [1] | co | - |  | 5.0 |  |
| q15 | detail | en | yes | 0.912 | 0.554 | 0 | 2 | [1] | co | - |  | 2.9 |  |
| q16 | unanswerable | en | no | 0.807 | 0.807 | 2 | 6 | [] | - | co |  | 8.3 |  |
| q17 | numeric | en | yes | 0.809 | 0.760 | 0 | 2 | [1, 2] | co | - |  | 3.0 |  |
| q18 | numeric | vi | yes | 0.834 | 0.745 | 0 | 2 | [1] | - | - |  | 7.0 |  |
