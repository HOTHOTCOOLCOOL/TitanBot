import sys
import argparse

def main():
    parser = argparse.ArgumentParser(description="Read a PDF and print its text.")
    parser.add_argument("pdf_path", help="Path to the PDF file")
    parser.add_argument("--page", type=int, help="Specific page to read (0-indexed)", default=None)
    parser.add_argument("--limit", type=int, help="Limit number of pages", default=10)
    args = parser.parse_args()

    try:
        import pdfplumber
    except ImportError:
        print("Error: pdfplumber is not installed. Please run: pip install pdfplumber")
        sys.exit(1)

    print(f"Reading PDF: {args.pdf_path}")
    try:
        with pdfplumber.open(args.pdf_path) as pdf:
            total_pages = len(pdf.pages)
            print(f"Total Pages: {total_pages}\n")
            
            if args.page is not None:
                if 0 <= args.page < total_pages:
                    print(f"--- Page {args.page} ---")
                    text = pdf.pages[args.page].extract_text()
                    print(text if text else "[No text found on this page]")
                else:
                    print(f"Error: Page {args.page} is out of bounds (0 to {total_pages-1})")
            else:
                for i, page in enumerate(pdf.pages[:args.limit]):
                    print(f"--- Page {i} ---")
                    text = page.extract_text()
                    print(text if text else "[No text found on this page]")
                
                if total_pages > args.limit:
                    print(f"\n[Output limited to first {args.limit} pages. Use --page or increase --limit to read more.]")
    except Exception as e:
        print(f"Failed to read PDF: {e}")

if __name__ == "__main__":
    main()
