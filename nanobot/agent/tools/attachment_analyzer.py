"""
Attachment analyzer tool for nanobot.

Provides tools to:
- Parse various file formats (PDF, Excel, Word, Text)
- Extract content from attachments

Requires:
- PyPDF2: pip install PyPDF2
- python-docx: pip install python-docx
- pandas: pip install pandas
"""

import os
import tempfile
from pathlib import Path
from typing import Any

# Import at top level to avoid runtime import issues
try:
    from PyPDF2 import PdfReader
except ImportError:
    PdfReader = None

try:
    import pandas as pd
except ImportError:
    pd = None

try:
    from docx import Document
except ImportError:
    Document = None

from loguru import logger

from nanobot.agent.tools.base import Tool


class AttachmentAnalyzerTool(Tool):
    """
    Tool for analyzing email attachments.
    
    Supports parsing:
    - PDF files (.pdf)
    - Excel files (.xls, .xlsx)
    - Word documents (.doc, .docx)
    - Text files (.txt)
    """
    
    def __init__(self):
        self._temp_files = []
    
    @property
    def name(self) -> str:
        return "attachment_analyzer"
    
    @property
    def description(self) -> str:
        return """Attachment analyzer tool.
Allows you to:
- Parse and extract content from various file formats
- Get text content from PDF, Excel, Word, and text files

Supports: PDF, Excel (.xls, .xlsx), Word (.doc, .docx), Text (.txt)"""
    
    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["parse", "list_supported", "get_info"],
                    "description": "The action to perform"
                },
                "file_path": {
                    "type": "string",
                    "description": "Path to the file to analyze"
                },
                "max_length": {
                    "type": "integer",
                    "description": "Maximum characters to extract (for text extraction)",
                    "default": 50000
                }
            },
            "required": ["action"]
        }
    
    async def execute(self, **kwargs: Any) -> str:
        """Execute attachment analyzer action."""
        action = kwargs.get("action", "parse")
        
        try:
            if action == "parse":
                return await self._parse_attachment(
                    kwargs.get("file_path", ""),
                    kwargs.get("max_length", 50000)
                )
            elif action == "list_supported":
                return self._list_supported()
            elif action == "get_info":
                return await self._get_file_info(kwargs.get("file_path", ""))
            else:
                return f"Unknown action: {action}"
        except Exception as e:
            logger.error(f"Attachment analyzer error: {e}")
            return f"Error: {str(e)}"
    
    def _list_supported(self) -> str:
        """List supported file formats."""
        return """Supported file formats:
- PDF (.pdf): Full text extraction
- Excel (.xls, .xlsx): Table data with statistics
- Word (.doc, .docx): Document text extraction
- Text (.txt): Plain text files
- CSV (.csv): Comma-separated values"""
    
    async def _get_file_info(self, file_path: str) -> str:
        """Get file information."""
        if not os.path.exists(file_path):
            return f"File not found: {file_path}"
        
        stat = os.stat(file_path)
        size = stat.st_size
        ext = os.path.splitext(file_path)[1].lower()
        
        info = f"""File: {os.path.basename(file_path)}
Path: {file_path}
Size: {size:,} bytes ({size / 1024:.1f} KB)
Type: {ext or 'unknown'}
Supported: {ext in ['.pdf', '.xls', '.xlsx', '.doc', '.docx', '.txt', '.csv']}"""
        
        return info
    
    async def _parse_attachment(self, file_path: str, max_length: int = 50000) -> str:
        """Parse attachment and extract content."""
        if not file_path:
            return "Error: No file path provided"
        
        if not os.path.exists(file_path):
            return f"Error: File not found: {file_path}"
        
        ext = os.path.splitext(file_path)[1].lower()
        
        try:
            if ext == ".pdf":
                return await self._parse_pdf(file_path, max_length)
            elif ext in [".xls", ".xlsx"]:
                return await self._parse_excel(file_path, max_length)
            elif ext in [".doc", ".docx"]:
                return await self._parse_word(file_path, max_length)
            elif ext == ".txt":
                return await self._parse_text(file_path, max_length)
            elif ext == ".csv":
                return await self._parse_csv(file_path, max_length)
            else:
                return f"Unsupported file format: {ext}"
        except Exception as e:
            logger.error(f"Error parsing {file_path}: {e}")
            return f"Error parsing file: {str(e)}"
    
    async def _parse_pdf(self, file_path: str, max_length: int) -> str:
        """Parse PDF file."""
        if PdfReader is None:
            return "Error: PyPDF2 not installed. Run: pip install PyPDF2"
        
        try:
            reader = PdfReader(file_path)
            text = ""
            for page in reader.pages:
                try:
                    page_text = page.extract_text()
                    if page_text:
                        text += page_text
                except Exception as e:
                    logger.debug(f"Error extracting page text: {e}")
                    continue
            
            if not text.strip():
                return f"=== PDF ===\n\n[No text content could be extracted]"
            
            if len(text) > max_length:
                text = text[:max_length] + f"\n\n... [truncated]"
            
            return f"=== PDF ===\n\n{text}"
        except Exception as e:
            logger.error(f"PDF parsing error: {e}")
            return f"Error parsing PDF: {str(e)}"
    
    async def _parse_excel(self, file_path: str, max_length: int) -> str:
        """Parse Excel file."""
        if pd is None:
            return "Error: pandas not installed. Run: pip install pandas"
        
        try:
            df = pd.read_excel(file_path)
            
            output = f"=== Excel ===\n"
            output += f"表格共 {df.shape[0]} 行，{df.shape[1]} 列。\n"
            output += f"列名: {', '.join(df.columns.tolist())}\n\n"
            output += "前5行数据:\n" + df.head().to_string()
            
            if len(output) > max_length:
                output = output[:max_length] + "\n\n... [truncated]"
            
            return output
        except Exception as e:
            return f"Error parsing Excel: {str(e)}"
    
    async def _parse_word(self, file_path: str, max_length: int) -> str:
        """Parse Word document."""
        if Document is None:
            return "Error: python-docx not installed. Run: pip install python-docx"
        
        try:
            doc = Document(file_path)
            text = "\n".join([para.text for para in doc.paragraphs])
            
            if len(text) > max_length:
                text = text[:max_length] + "\n\n... [truncated]"
            
            return f"=== Word ===\n\n{text}"
        except Exception as e:
            return f"Error parsing Word: {str(e)}"
    
    async def _parse_text(self, file_path: str, max_length: int) -> str:
        """Parse text file."""
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                text = f.read()
            
            if len(text) > max_length:
                text = text[:max_length] + "\n\n... [truncated]"
            
            return f"=== Text ===\n\n{text}"
        except Exception as e:
            return f"Error reading text file: {str(e)}"
    
    async def _parse_csv(self, file_path: str, max_length: int) -> str:
        """Parse CSV file."""
        if pd is None:
            return "Error: pandas not installed. Run: pip install pandas"
        
        try:
            df = pd.read_csv(file_path)
            
            output = f"=== CSV ===\n"
            output += f"表格共 {df.shape[0]} 行，{df.shape[1]} 列。\n"
            output += f"列名: {', '.join(df.columns.tolist())}\n\n"
            output += "前10行:\n" + df.head(10).to_string()
            
            if len(output) > max_length:
                output = output[:max_length] + "\n\n... [truncated]"
            
            return output
        except Exception as e:
            return f"Error parsing CSV: {str(e)}"
    
    def cleanup(self):
        """Clean up temporary files."""
        for temp_file in self._temp_files:
            try:
                if os.path.exists(temp_file):
                    os.remove(temp_file)
            except:
                pass
        self._temp_files.clear()
