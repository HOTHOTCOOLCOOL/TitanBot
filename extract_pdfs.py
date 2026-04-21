import sys
import pdfplumber

def extract_pdf(pdf_path, output_path, limit=5):
    try:
        with pdfplumber.open(pdf_path) as pdf:
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(f"Reading PDF: {pdf_path}\n")
                total_pages = len(pdf.pages)
                f.write(f"Total Pages: {total_pages}\n\n")
                
                for i, page in enumerate(pdf.pages[:limit]):
                    f.write(f"--- Page {i} ---\n")
                    text = page.extract_text()
                    if text:
                        f.write(text + "\n")
                    else:
                        f.write("[No text found on this page]\n")
                
                if total_pages > limit:
                    f.write(f"\n[Output limited to first {limit} pages.]\n")
        print(f"Successfully extracted {pdf_path} to {output_path}")
    except Exception as e:
        print(f"Failed to read {pdf_path}: {e}")

if __name__ == '__main__':
    pdfs = [
        (r"C:\Users\davidliu\Downloads\2602.12735v1.pdf", "paper1.txt"),
        (r"C:\Users\davidliu\Downloads\2602.19127v1.pdf", "paper2.txt"),
        (r"C:\Users\davidliu\Downloads\2603.03296v1.pdf", "paper3.txt"),
        (r"C:\Users\davidliu\Downloads\2602.14470v1.pdf", "paper4.txt"),
        (r"C:\Users\davidliu\Downloads\2602.05665v1.pdf", "paper5.txt")
    ]
    for pdf_path, output_path in pdfs:
        extract_pdf(pdf_path, output_path)
