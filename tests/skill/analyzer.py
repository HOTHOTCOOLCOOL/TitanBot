# analyzer.py
import re
from collections import Counter

def summarize(text, max_length=500):
    """返回文本的前max_length个字符作为摘要"""
    return text[:max_length] + ("..." if len(text) > max_length else "")

def extract_keywords(text, top_n=10):
    """提取出现频率最高的词（简单分词，仅限英文）"""
    words = re.findall(r'\b[a-zA-Z]{3,}\b', text.lower())
    counter = Counter(words)
    return counter.most_common(top_n)

def analyze_content(text, analysis_type='summary'):
    """统一的分析接口"""
    if analysis_type == 'summary':
        return summarize(text)
    elif analysis_type == 'keywords':
        keywords = extract_keywords(text)
        return "关键词统计：\n" + "\n".join([f"{k}: {v}" for k, v in keywords])
    elif analysis_type == 'full':
        return text
    else:
        return f"未知分析类型 '{analysis_type}'，返回全文。\n{text}"