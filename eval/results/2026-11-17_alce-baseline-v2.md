# Citation eval - alce-baseline-v2

- Ngay: 2026-11-17
- Git commit: e01ec2b
- Model: groq/openai/gpt-oss-120b; nghi giua cac cau: 20.0s
- So cau: 21 (answerable 21); da chay: 21; loi: 0; chua chay: 0
- Nguyen van cau tra loi: `2026-11-17_alce-baseline-v2.answers.jsonl`

| Chi so | Gia tri |
|---|---|
| (a) Answerable co >= 1 marker hop le | 20/21 (95%) |
| (b) Marker ngoai pham vi (tong) | 0 |
| (c) Citation precision (lenient) | 18/21 (86%) |
| (d) Answerable co kieu trich dan khac [n] | 0/21 (0%) |
| (e) Answerable bi grade 'no' o luot dau (cham oan) | 1/21 (5%) |
| (f) Unanswerable duoc grade 'yes' o luot dau (lot) | n/a |
| (g) Unanswerable co cau tra loi tu choi (heuristic) | n/a |
| So lan goi LLM trung binh / cau | 2.19 |
| (h) ALCE citation recall: cau khang dinh duoc chung minh day du | 34/64 (53%) (+2 mot phan; 21/21 cau tra loi da cham, 0 giam khao loi -> bo) |
| (i) ALCE citation precision: trich dan [n] co ich | 49/53 (92%) |
| (j) Cau khang dinh KHONG co trich dan | 24 |

| id | type | lang | grade dau | top1 | top2 | rewrite | LLM calls | markers | trung evidence | tu choi | ALCE du/khang dinh | ALCE co ich/trich dan | kieu khac | giay | error |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| q09 | numeric | en | yes | 0.902 | 0.875 | 0 | 2 | [5] | co | - | 1/1 | 1/1 |  | 4.4 |  |
| q10 | numeric | vi | yes | 0.730 | 0.642 | 0 | 2 | [] | - | co | 0/0 | 0/0 |  | 9.7 |  |
| q11 | method | en | yes | 0.719 | 0.658 | 0 | 2 | [2] | co | - | 1/5 | 1/1 |  | 8.2 |  |
| q12 | method | vi | yes | 0.284 | 0.212 | 0 | 2 | [3, 1] | co | - | 3/5 | 4/4 |  | 5.3 |  |
| q13 | definition | en | yes | 0.720 | 0.483 | 0 | 2 | [1] | co | - | 1/1 | 1/1 |  | 5.8 |  |
| q14 | formula | en | yes | 0.800 | 0.180 | 0 | 2 | [1] | co | - | 2/4 | 2/2 |  | 15.8 |  |
| q15 | detail | en | yes | 0.912 | 0.554 | 0 | 2 | [1] | co | - | 1/2 | 1/1 |  | 3.4 |  |
| q17 | numeric | en | yes | 0.809 | 0.760 | 0 | 2 | [1] | - | - | 1/1 | 1/1 |  | 6.7 |  |
| q18 | numeric | vi | yes | 0.834 | 0.745 | 0 | 2 | [1, 3] | co | - | 1/2 | 2/2 |  | 5.8 |  |
| q19 | method | en | yes | 0.695 | 0.643 | 0 | 2 | [1, 3, 2] | co | - | 2/9 | 5/6 |  | 5.6 |  |
| q20 | method | vi | yes | 0.363 | 0.269 | 0 | 2 | [3] | co | - | 4/7 | 4/4 |  | 7.4 |  |
| q21 | definition | en | yes | 0.665 | 0.629 | 0 | 2 | [1, 4] | co | - | 1/1 | 2/2 |  | 4.2 |  |
| q22 | formula | en | yes | 0.828 | 0.819 | 0 | 2 | [1, 2] | co | - | 1/4 | 2/2 |  | 4.5 |  |
| q23 | detail | en | yes | 0.817 | 0.611 | 0 | 2 | [1] | co | - | 2/2 | 2/2 |  | 3.7 |  |
| q41 | numeric | en | yes | 0.920 | 0.867 | 0 | 2 | [2] | co | - | 3/3 | 3/3 |  | 9.0 |  |
| q42 | numeric | en | yes | 0.916 | 0.909 | 0 | 2 | [4] | - | - | 0/1 | 0/1 |  | 6.8 |  |
| q43 | method | vi | yes | 0.593 | 0.531 | 0 | 2 | [2, 4, 1, 3] | co | - | 4/4 | 6/6 |  | 5.0 |  |
| q44 | method | en | yes | 0.654 | 0.640 | 0 | 2 | [1, 3, 4] | co | - | 1/6 | 5/7 |  | 5.3 |  |
| q45 | definition | en | yes | 0.848 | 0.640 | 0 | 2 | [1] | co | - | 1/1 | 1/1 |  | 4.9 |  |
| q46 | formula | en | no | 0.639 | 0.613 | 2 | 6 | [3, 1, 4] | co | - | 3/4 | 4/4 |  | 18.2 |  |
| q47 | detail | vi | yes | 0.723 | 0.525 | 0 | 2 | [1, 3] | co | - | 1/1 | 2/2 |  | 7.0 |  |
