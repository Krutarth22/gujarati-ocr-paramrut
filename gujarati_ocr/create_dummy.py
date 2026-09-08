from reportlab.pdfgen import canvas
import os

def create_dummy_pdf(filename="test_input.pdf", pages=3):
    c = canvas.Canvas(filename)
    for i in range(pages):
        c.drawString(100, 750, f"This is page {i+1} of the dummy PDF.")
        c.drawString(100, 700, "This is some English text because I might not have Gujarati fonts installed.")
        c.showPage()
    c.save()
    print(f"Created {filename}")

if __name__ == "__main__":
    create_dummy_pdf()
