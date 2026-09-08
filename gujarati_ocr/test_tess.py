import pytesseract
from PIL import Image
import sys

try:
    img = Image.open('test_input_q80.jpg').convert('L')
    print("Testing with direct PIL Image (Grayscale)")
    pdf_bytes = pytesseract.image_to_pdf_or_hocr(img, extension='pdf', lang='guj+eng')
    print("Success. PDF bytes length:", len(pdf_bytes))
except Exception as e:
    print("Error with direct PIL Image:", repr(e))

try:
    img = Image.open('test_input_q80.jpg').convert('L')
    print("Testing with saved temp image path")
    img.save("temp_test.png")
    pdf_bytes = pytesseract.image_to_pdf_or_hocr("temp_test.png", extension='pdf', lang='guj+eng')
    print("Success. PDF bytes length:", len(pdf_bytes))
except Exception as e:
    print("Error with path:", repr(e))

