# Gate data - diem rerank luot dau (36 cau, khong goi LLM)

- Ngay: 2026-11-07. Cohere `rerank-v3.5`, top-5 sau hybrid top-20, cau hoi goc (chua rewrite).
- Muc dich: diem quyet dinh cua cong 3 tang (lo trinh giai doan 1). Grade LLM chua do du vi Groq het TPD (200K/ngay); ket qua 10 cau dau o `2026-11-07_gate-data-run1.md`.

## Ket qua

| | Answerable (21) | Unanswerable (15) |
|---|---|---|
| Trung vi top1 | 0.730 | 0.720 |
| Trung vi (top1 - top2) | 0.063 | 0.016 |
| Top1 cao nhat | 0.920 | **0.868** (q53) |
| Top1 thap nhat | 0.284 | 0.396 |

- Nguong tren an toan phai > 0.868 (khong de lot unanswerable): chi **4/21** cau answerable vuot (q09, q15, q41, q42) -> cong chi bo qua grader ~19% cau co dap an (dieu kien >= 50%: **KHONG DAT**).
- Nguong duoi: khong co cau unanswerable nao thap hon cau answerable thap nhat (0.284) -> tang duoi khong tiet kiem gi.
- 7/15 cau unanswerable co top1 cao hon trung vi cua cau answerable: cau 'gan chu de' (sai tap du lieu / sai cau hinh) duoc reranker cham cao y nhu cau co dap an. Khop nhan dinh: diem rerank do 'dung chu de', khong do 'du de tra loi'.
- Ket luan: **khong lam cong 3 tang theo diem rerank**; chuyen phuong an B (giu LLM grader, lam re hon).

## Chi tiet

| id | type | lang | top1 | top2 | top1-top2 |
|---|---|---|---|---|---|
| q41 | numeric | en | 0.920 | 0.867 | 0.053 |
| q42 | numeric | en | 0.916 | 0.909 | 0.007 |
| q15 | detail | en | 0.912 | 0.554 | 0.358 |
| q09 | numeric | en | 0.902 | 0.875 | 0.026 |
| q53 | unanswerable | en | 0.868 | 0.787 | 0.081 |
| q45 | definition | en | 0.848 | 0.640 | 0.207 |
| q49 | unanswerable | en | 0.845 | 0.839 | 0.006 |
| q18 | numeric | vi | 0.834 | 0.745 | 0.089 |
| q22 | formula | en | 0.828 | 0.819 | 0.009 |
| q23 | detail | en | 0.817 | 0.611 | 0.207 |
| q50 | unanswerable | en | 0.817 | 0.803 | 0.014 |
| q17 | numeric | en | 0.809 | 0.760 | 0.049 |
| q16 | unanswerable | en | 0.808 | 0.806 | 0.002 |
| q14 | formula | en | 0.800 | 0.180 | 0.620 |
| q59 | unanswerable | en | 0.777 | 0.698 | 0.079 |
| q58 | unanswerable | en | 0.771 | 0.733 | 0.038 |
| q57 | unanswerable | en | 0.759 | 0.743 | 0.016 |
| q10 | numeric | vi | 0.730 | 0.642 | 0.088 |
| q47 | detail | vi | 0.723 | 0.525 | 0.197 |
| q13 | definition | en | 0.721 | 0.483 | 0.238 |
| q24 | unanswerable | en | 0.720 | 0.684 | 0.037 |
| q11 | method | en | 0.719 | 0.658 | 0.061 |
| q54 | unanswerable | en | 0.714 | 0.644 | 0.070 |
| q51 | unanswerable | en | 0.707 | 0.697 | 0.010 |
| q19 | method | en | 0.695 | 0.643 | 0.052 |
| q21 | definition | en | 0.665 | 0.629 | 0.037 |
| q44 | method | en | 0.654 | 0.640 | 0.013 |
| q46 | formula | en | 0.639 | 0.613 | 0.026 |
| q43 | method | vi | 0.594 | 0.531 | 0.063 |
| q60 | unanswerable | vi | 0.588 | 0.477 | 0.111 |
| q56 | unanswerable | vi | 0.572 | 0.560 | 0.011 |
| q52 | unanswerable | vi | 0.530 | 0.520 | 0.010 |
| q55 | unanswerable | vi | 0.529 | 0.527 | 0.002 |
| q48 | unanswerable | vi | 0.396 | 0.294 | 0.102 |
| q20 | method | vi | 0.363 | 0.269 | 0.095 |
| q12 | method | vi | 0.284 | 0.212 | 0.072 |
