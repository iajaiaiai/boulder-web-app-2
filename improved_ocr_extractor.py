import subprocess
from pathlib import Path
import json
from datetime import datetime
import io

def improved_ocr_process(session_dir):
    """Process PDFs with OCR using the best available method."""
    session_path = Path(session_dir)
    ocr_texts = {}
    
    print(f'🔍 Running BEST OCR process on {session_path}')
    
    for pdf_file in session_path.glob('*.pdf'):
        print(f'📄 Processing {pdf_file.name}...')
        
        text = ''
        method_used = ''
        
        # Method 1: Try multiple OCR approaches and pick the best result
        best_text = ''
        best_method = ''
        best_score = 0
        
        # Approach 1: OCRmyPDF with optimized settings
        try:
            import subprocess
            print(f'🔍 Trying OCRmyPDF (optimized) for {pdf_file.name}...')
            
            ocr_output = session_path / f'ocr_opt_{pdf_file.name}'
            
            result = subprocess.run([
                'ocrmypdf', 
                str(pdf_file), 
                str(ocr_output),
                '--output-type', 'pdf',
                '--force-ocr',
                '--optimize', '0',
                '--language', 'eng',
                '--tesseract-oem', '3',
                '--tesseract-pagesegmode', '1',
                '--tesseract-thresholding', 'adaptive-otsu',
                '--tesseract-timeout', '300'
            ], capture_output=True, text=True, timeout=300)
            
            if result.returncode == 0:
                import fitz
                doc = fitz.open(ocr_output)
                ocr_text = ''
                for page_num in range(len(doc)):
                    page = doc.load_page(page_num)
                    page_text = page.get_text()
                    if page_text.strip():
                        ocr_text += f'--- PAGE {page_num + 1} ---\n{page_text}\n\n'
                doc.close()
                
                # Score this result (longer text with common words = better)
                score = len(ocr_text) + ocr_text.lower().count('the') * 10 + ocr_text.lower().count('and') * 5
                if score > best_score:
                    best_text = ocr_text
                    best_method = 'OCRmyPDF_Optimized'
                    best_score = score
                    print(f'✅ OCRmyPDF optimized: {len(ocr_text)} chars, score: {score}')
                
        except Exception as e:
            print(f'⚠️ OCRmyPDF optimized failed: {e}')
        
        # Approach 2: Direct Tesseract with high-res images
        try:
            print(f'🔍 Trying Tesseract (high-res) for {pdf_file.name}...')
            
            import fitz
            import pytesseract
            from PIL import Image, ImageEnhance
            
            doc = fitz.open(pdf_file)
            tesseract_text = ''
            
            for page_num in range(len(doc)):
                page = doc.load_page(page_num)
                
                # Convert to high-res image
                mat = fitz.Matrix(2.5, 2.5)  # High resolution
                pix = page.get_pixmap(matrix=mat)
                
                # Convert to PIL Image
                img_data = pix.tobytes("png")
                img = Image.open(io.BytesIO(img_data))
                
                # Enhance image
                img = img.convert('L')  # Grayscale
                contrast_enhancer = ImageEnhance.Contrast(img)
                img = contrast_enhancer.enhance(1.5)
                
                # Run Tesseract
                page_text = pytesseract.image_to_string(img, config='--oem 3 --psm 1')
                if page_text.strip():
                    tesseract_text += f'--- PAGE {page_num + 1} ---\n{page_text}\n\n'
            
            doc.close()
            
            # Score this result
            score = len(tesseract_text) + tesseract_text.lower().count('the') * 10 + tesseract_text.lower().count('and') * 5
            if score > best_score:
                best_text = tesseract_text
                best_method = 'Tesseract_HighRes'
                best_score = score
                print(f'✅ Tesseract high-res: {len(tesseract_text)} chars, score: {score}')
                
        except Exception as e:
            print(f'⚠️ Tesseract high-res failed: {e}')
        
        # Approach 3: Fallback to basic PyMuPDF
        try:
            print(f'🔍 Trying PyMuPDF fallback for {pdf_file.name}...')
            
            import fitz
            doc = fitz.open(pdf_file)
            pymupdf_text = ''
            
            for page_num in range(len(doc)):
                page = doc.load_page(page_num)
                page_text = page.get_text()
                if page_text.strip():
                    pymupdf_text += f'--- PAGE {page_num + 1} ---\n{page_text}\n\n'
            
            doc.close()
            
            # Score this result
            score = len(pymupdf_text) + pymupdf_text.lower().count('the') * 10 + pymupdf_text.lower().count('and') * 5
            if score > best_score:
                best_text = pymupdf_text
                best_method = 'PyMuPDF'
                best_score = score
                print(f'✅ PyMuPDF: {len(pymupdf_text)} chars, score: {score}')
                
        except Exception as e:
            print(f'⚠️ PyMuPDF failed: {e}')
        
        # Use the best result
        if best_text:
            text = best_text
            method_used = best_method
            print(f'🏆 BEST RESULT: {method_used} with {len(text)} characters')
        else:
            print(f'❌ All OCR methods failed for {pdf_file.name}')
            method_used = 'failed'
        
        # Save the extracted text
        if text.strip():
            text_filename = pdf_file.stem + f'_extracted_text_{method_used.lower().replace("_", "-")}.txt'
            text_path = session_path / text_filename
            
            with open(text_path, 'w', encoding='utf-8') as f:
                f.write(text)
            
            ocr_texts[pdf_file.name] = {
                'filename': pdf_file.name,
                'text_length': len(text),
                'text_file': str(text_path),
                'extracted_text': text,
                'method_used': method_used
            }
            
            print(f'💾 Saved {method_used} text to: {text_path}')
            print(f'📊 Total characters extracted: {len(text)}')
            
        else:
            print(f'❌ No text could be extracted from {pdf_file.name} using any method')
            ocr_texts[pdf_file.name] = {
                'filename': pdf_file.name,
                'text_length': 0,
                'text_file': '',
                'extracted_text': '',
                'method_used': 'failed'
            }
    
    # Save combined OCR results
    if ocr_texts:
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        combined_file = session_path / f'all_ocr_texts_{timestamp}.json'
        
        combined_data = {
            'extracted_at': datetime.now().isoformat(),
            'total_files': len(ocr_texts),
            'total_characters': sum(data['text_length'] for data in ocr_texts.values()),
            'ocr_texts': ocr_texts
        }
        
        with open(combined_file, 'w', encoding='utf-8') as f:
            json.dump(combined_data, f, indent=2, ensure_ascii=False)
        
        print(f'💾 Combined OCR data saved to: {combined_file}')
        print(f'📊 Total files processed: {len(ocr_texts)}')
        print(f'📊 Total characters extracted: {combined_data["total_characters"]}')
        
        return combined_file
    else:
        print('❌ No text could be extracted from any PDFs')
        return None