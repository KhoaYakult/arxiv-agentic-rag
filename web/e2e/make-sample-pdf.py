"""Tao web/e2e/fixtures/sample.pdf (2 trang, co text layer) cho Playwright. Chay 1 lan:
    .venv/bin/python web/e2e/make-sample-pdf.py
"""

from pathlib import Path

import fitz

out = Path(__file__).parent / "fixtures" / "sample.pdf"
out.parent.mkdir(parents=True, exist_ok=True)
doc = fitz.open()
p1 = doc.new_page()
p1.insert_text((72, 90), "1 Introduction", fontsize=14)
p1.insert_textbox(fitz.Rect(72, 110, 520, 400),
                  "Recurrent models typically factor computation along the symbol positions of the input "
                  "and output sequences. We propose the Transformer, a model architecture eschewing recurrence.",
                  fontsize=11)
p2 = doc.new_page()
p2.insert_text((72, 90), "6 Results", fontsize=14)
p2.insert_textbox(fitz.Rect(72, 110, 520, 400),
                  "On the WMT 2014 English-to-French translation task, our big model achieves a BLEU score "
                  "of 41.0, outperforming all of the previously published single models.",
                  fontsize=11)
doc.save(out)
print(f"wrote {out} ({out.stat().st_size} bytes)")
