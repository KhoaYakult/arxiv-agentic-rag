# Retrieval eval - sparse-or-rerank-en-v3

- Ngay: 2026-10-24
- Git commit: 8813f58
- So cau hoi (answerable): 21
- Configs yeu cau: rrf+rerank
- Configs da chay: rrf+rerank

## Metrics (strict)

| config | Hit@1 | Hit@3 | Hit@5 | Hit@10 | Hit@20 | MRR@20 | nDCG@10 | 0 ket qua |
|---|---|---|---|---|---|---|---|---|
| rrf+rerank | 0.333 | 0.476 | 0.571 | 0.714 | 0.905 | 0.452 | 0.481 | 0/21 |

## Metrics (lenient)

| config | Hit@1 | Hit@3 | Hit@5 | Hit@10 | Hit@20 | MRR@20 | nDCG@10 | 0 ket qua |
|---|---|---|---|---|---|---|---|---|
| rrf+rerank | 0.381 | 0.524 | 0.619 | 0.762 | 0.952 | 0.499 | 0.513 | 0/21 |

`0 ket qua` = so cau hoi ma config tra ve danh sach rong (vd sparse: `websearch_to_tsquery` AND tat ca tu khoa, cau hoi dai/tieng Viet de khong khop gi).

## Hit@5 (lenient) theo type

| config | definition (n=3) | detail (n=3) | formula (n=3) | method (n=6) | numeric (n=6) |
|---|---|---|---|---|---|
| rrf+rerank | 1.000 | 0.667 | 0.667 | 0.667 | 0.333 |

## Hit@5 (lenient) theo lang

| config | en (n=15) | vi (n=6) |
|---|---|---|
| rrf+rerank | 0.733 | 0.333 |

## Rank cua chunk lien quan dau tien (lenient)

`-` = khong co chunk lien quan trong top 20. Cot strict trong ngoac.

| id | paper | lang | type | rrf+rerank |
|---|---|---|---|---|
| q09 | 1706.03762 | en | numeric | 9 (-) |
| q10 | 1706.03762 | vi | numeric | 17 (17) |
| q11 | 1706.03762 | en | method | 2 (2) |
| q12 | 1706.03762 | vi | method | 10 (10) |
| q13 | 1706.03762 | en | definition | 1 (1) |
| q14 | 1706.03762 | en | formula | 1 (1) |
| q15 | 1706.03762 | en | detail | 1 (1) |
| q17 | 2004.04906 | en | numeric | 6 (6) |
| q18 | 2004.04906 | vi | numeric | 4 (4) |
| q19 | 2004.04906 | en | method | 3 (3) |
| q20 | 2004.04906 | vi | method | 1 (1) |
| q21 | 2004.04906 | en | definition | 1 (7) |
| q22 | 2004.04906 | en | formula | 1 (1) |
| q23 | 2004.04906 | en | detail | 1 (1) |
| q41 | 2401.15884 | en | numeric | 2 (2) |
| q42 | 2401.15884 | en | numeric | - (-) |
| q43 | 2401.15884 | vi | method | 20 (20) |
| q44 | 2401.15884 | en | method | 4 (4) |
| q45 | 2401.15884 | en | definition | 1 (1) |
| q46 | 2401.15884 | en | formula | 11 (11) |
| q47 | 2401.15884 | vi | detail | 17 (17) |

