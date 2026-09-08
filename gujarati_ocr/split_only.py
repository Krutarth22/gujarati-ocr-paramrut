from utils import split_pdf_output
import os

input_pdf = "swami ni vato chapter 10 16_ocr.pdf"
# Prefix logic similar to main.py
output_dir = os.path.dirname(input_pdf) if os.path.dirname(input_pdf) else "."
base_name = os.path.splitext(os.path.basename(input_pdf))[0]
# Name is already '..._ocr', so we can just use that base, but users want '..._ocr1.pdf'
# If input is 'foo_ocr.pdf', base is 'foo_ocr'.
# We want 'foo_ocr1.pdf'. So usage of base name is correct.
prefix = os.path.join(output_dir, base_name)

print(f"Splitting {input_pdf} with limit 175MB...")
files = split_pdf_output(input_pdf, max_size_mb=175, output_prefix=prefix)

print("Split files created:")
for f in files:
    print(f"- {f}")
