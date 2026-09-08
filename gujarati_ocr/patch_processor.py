import re

with open('processor.py', 'r') as f:
    content = f.read()

# Replace the direct image passing with temp file logic
old_code = """                                # 1. PDF Generation
                                pdf_bytes = pytesseract.image_to_pdf_or_hocr(processed_image, extension='pdf', lang=self.lang)
                                pdf_page_reader = PdfReader(io.BytesIO(pdf_bytes))
                                if len(pdf_page_reader.pages) > 0:
                                    pdf_writer.add_page(pdf_page_reader.pages[0])

                                # 2. Extract Text for DOCX
                                # Use --psm 3 and preserve_interword_spaces for tables
                                custom_config = r'--psm 3 -c preserve_interword_spaces=1'
                                raw_text = pytesseract.image_to_string(processed_image, lang=self.lang, config=custom_config)
                                text = self._clean_text(raw_text)"""

new_code = """                                import tempfile
                                import os
                                
                                # Save to temp file to avoid pytesseract PIL passing bug
                                fd, temp_img_path = tempfile.mkstemp(suffix='.png')
                                os.close(fd)
                                
                                try:
                                    processed_image.save(temp_img_path)
                                    
                                    # 1. PDF Generation
                                    pdf_bytes = pytesseract.image_to_pdf_or_hocr(temp_img_path, extension='pdf', lang=self.lang)
                                    pdf_page_reader = PdfReader(io.BytesIO(pdf_bytes))
                                    if len(pdf_page_reader.pages) > 0:
                                        pdf_writer.add_page(pdf_page_reader.pages[0])
    
                                    # 2. Extract Text for DOCX
                                    custom_config = r'--psm 3 -c preserve_interword_spaces=1'
                                    raw_text = pytesseract.image_to_string(temp_img_path, lang=self.lang, config=custom_config)
                                    text = self._clean_text(raw_text)
                                finally:
                                    if os.path.exists(temp_img_path):
                                        os.remove(temp_img_path)"""

content = content.replace(old_code, new_code)

old_code2 = """                # 1. Generate Searchable PDF Page
                pdf_bytes = pytesseract.image_to_pdf_or_hocr(processed_image, extension='pdf', lang=self.lang)
                pdf_page_reader = PdfReader(io.BytesIO(pdf_bytes))
                if len(pdf_page_reader.pages) > 0:
                    pdf_writer.add_page(pdf_page_reader.pages[0])

                # 2. Extract Text for DOCX
                # Use --psm 3 (auto segmentation) and preserve_interword_spaces=1 to keep table alignment
                custom_config = r'--psm 3 -c preserve_interword_spaces=1'
                raw_text = pytesseract.image_to_string(processed_image, lang=self.lang, config=custom_config)"""

new_code2 = """                import tempfile
                import os
                
                fd, temp_img_path = tempfile.mkstemp(suffix='.png')
                os.close(fd)
                
                try:
                    processed_image.save(temp_img_path)
                    
                    # 1. Generate Searchable PDF Page
                    pdf_bytes = pytesseract.image_to_pdf_or_hocr(temp_img_path, extension='pdf', lang=self.lang)
                    pdf_page_reader = PdfReader(io.BytesIO(pdf_bytes))
                    if len(pdf_page_reader.pages) > 0:
                        pdf_writer.add_page(pdf_page_reader.pages[0])
    
                    # 2. Extract Text for DOCX
                    custom_config = r'--psm 3 -c preserve_interword_spaces=1'
                    raw_text = pytesseract.image_to_string(temp_img_path, lang=self.lang, config=custom_config)
                finally:
                    if os.path.exists(temp_img_path):
                        os.remove(temp_img_path)"""

content = content.replace(old_code2, new_code2)

with open('processor.py', 'w') as f:
    f.write(content)
print("Updated processor.py")
