# attachment_parser.py
import os
import pandas as pd
from PyPDF2 import PdfReader
from docx import Document

def parse_text(file_path):
    """解析纯文本文件"""
    with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
        return f.read()

def parse_pdf(file_path):
    """解析PDF文件"""
    reader = PdfReader(file_path)
    text = ""
    for page in reader.pages:
        text += page.extract_text()
    return text

def parse_excel(file_path):
    """解析Excel文件，返回表格摘要"""
    df = pd.read_excel(file_path)
    # 简单统计：行列数、前几行数据
    info = f"表格共 {df.shape[0]} 行，{df.shape[1]} 列。\n"
    info += "前5行数据：\n" + df.head().to_string()
    return info

def parse_word(file_path):
    """解析Word文档"""
    doc = Document(file_path)
    text = "\n".join([para.text for para in doc.paragraphs])
    return text

def parse_attachment(file_path):
    """根据文件扩展名选择解析器"""
    ext = os.path.splitext(file_path)[1].lower()
    if ext == '.txt':
        return parse_text(file_path)
    elif ext == '.pdf':
        return parse_pdf(file_path)
    elif ext in ['.xls', '.xlsx']:
        return parse_excel(file_path)
    elif ext in ['.doc', '.docx']:
        return parse_word(file_path)
    else:
        return f"不支持解析 {ext} 格式文件，仅保存了原始附件。"