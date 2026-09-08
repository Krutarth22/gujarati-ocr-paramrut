from docx import Document
import sys

def get_text(path):
    try:
        doc = Document(path)
        return '\n'.join([p.text for p in doc.paragraphs if p.text.strip()])
    except Exception as e:
        return f"Error reading {path}: {e}"

text1 = get_text('outputs/swami_ni_vato.docx')
text2 = get_text('outputs/swami ni vato chapter 1 to 9.docx')

print("--- OUR OCR (swami_ni_vato.docx) ---")
print(text1[:1000])
print("\n" + "="*50 + "\n")
print("--- OUTSIDE OCR (swami ni vato chapter 1 to 9.docx) ---")
print(text2[:1000])
