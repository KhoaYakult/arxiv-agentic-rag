# Cross-lingual retrieval (Viet hoi bai Anh)

- Ngay: 2026-11-16; git: 930ee81; 21 cap cau song song (lenient, top-20 sau rerank)
- `vi-sparse-en*` = ban dich cua nguoi (can tren); `vi-sparse-mt` = qwen3.8-27b dich (se dua vao production)

| Cau hinh | Hit@1 | Hit@5 | MRR@20 |
|---|---|---|---|
| en | 0.619 | 0.905 | 0.735 |
| vi | 0.476 | 0.810 | 0.609 |
| vi-dense | 0.476 | 0.810 | 0.611 |
| vi-sparse-en* | 0.476 | 0.857 | 0.626 |
| vi-sparse-mt | 0.476 | 0.857 | 0.626 |

## Hang cua doan dung theo cau (None = khong co trong top-20)

| cau | ngon ngu goc | en | vi | vi-dense | vi-sparse-en* | vi-sparse-mt | ban dich qwen |
|---|---|---|---|---|---|---|---|
| q09 | en | 5 | 5 | 5 | 5 | 5 | What is the BLEU score of the base Transformer on WMT 2014 English–French (newstest2014) in the main translation results table? |
| q11 | en | 2 | 10 | 7 | 8 | 8 | Why does the Transformer divide the dot product between the query and key by a scaling factor before applying softmax? |
| q13 | en | 1 | 1 | 1 | 1 | 1 | How does the paper define self-attention? |
| q14 | en | 1 | 1 | 1 | 1 | 1 | According to the learning schedule formula, how does the learning rate of the Transformer change during training, and how many warmup steps are used? |
| q15 | en | 1 | 1 | 1 | 1 | 1 | How many sentence pairs are in the English-German training data, and what is the size of the shared vocabulary? |
| q17 | en | 2 | 2 | 2 | 2 | 2 | What is the top-20 retrieval accuracy of the Lucene BM25 baseline on CuratedTREC? |
| q19 | en | 1 | 1 | 1 | 1 | 1 | How does DPR obtain multiple negative passages from a mini-batch without encoding any additional passages? |
| q21 | en | 1 | 2 | 2 | 2 | 2 | How does the paper define top-k retrieval accuracy? |
| q22 | en | 1 | 1 | 1 | 1 | 1 | In the BM25+DPR hybrid system, how are the two scores combined into the ranking function, and what weight is assigned to the DPR similarity? |
| q23 | en | 1 | 1 | 1 | 1 | 1 | After preprocessing the Wikipedia dump, how many passages does DPR index, and what is the length of each passage? |
| q41 | en | 2 | 2 | 2 | 2 | 2 | On PopQA, how accurately does the T5-based retrieval evaluator of CRAG assess retrieval quality compared to directly querying ChatGPT? |
| q42 | en | None | None | None | None | None | When using SelfRAG-LLaMA2-7b as the generator, what is the FactScore achieved by CRAG on the Biography dataset? |
| q44 | en | 1 | None | None | 3 | 3 | How does the decompose-then-recompose step of CRAG transform a retrieved document into knowledge provided to the generator? |
| q45 | en | 1 | 1 | 1 | 1 | 1 | In CRAG, when is a retrieval labeled as "Correct"? |
| q46 | en | 1 | 4 | 4 | 4 | 4 | What does Equation (1) in the paper, which decomposes P(Y/X) into a retrieval component and a generation component, imply about a RAG pipeline? |
| q10 | vi | 17 | 14 | 13 | 14 | 14 | How many parameters (in millions) does the big-sized Transformer model have in the table of architecture variants? |
| q12 | vi | 1 | 1 | 1 | 1 | 1 | How does the Transformer prevent the decoder from seeing tokens at later positions when predicting the current token? |
| q18 | vi | 3 | 3 | 3 | 3 | 3 | When training in-batch with batch 128 and adding 1 negative BM25 for each question, what is the top-20 accuracy on the Natural Questions dev set? |
| q20 | vi | 3 | 3 | 3 | 3 | 3 | Why does DPR choose dot-product similarity between two vectors instead of using a multi-layer cross-attention model? |
| q43 | vi | 1 | 1 | 1 | 1 | 1 | How does the system handle the case when the CRAG retrieval evaluator is not confident enough to determine whether a document is correct or incorrect? |
| q47 | vi | 1 | 1 | 1 | 1 | 1 | Which confidence threshold pair (upper threshold, lower threshold) does CRAG use on the PopQA dataset? |
