# outlook_utils.py
import os
import win32com.client
from datetime import datetime
from pathlib import Path
import tempfile

def get_outlook_app():
    """获取Outlook应用程序对象"""
    try:
        outlook = win32com.client.Dispatch("Outlook.Application")
        return outlook
    except Exception as e:
        raise Exception(f"无法连接到Outlook: {e}")

def get_inbox():
    """获取收件箱文件夹（默认）"""
    outlook = get_outlook_app()
    namespace = outlook.GetNamespace("MAPI")
    inbox = namespace.GetDefaultFolder(6)  # 6 = olFolderInbox
    return inbox

def find_emails(folder, criteria):
    """
    根据条件查找邮件
    criteria: dict，支持字段：
        - subject_contains: str
        - from_email: str (发件人包含)
        - received_after: str (YYYY-MM-DD)
        - received_before: str
        - has_attachments: bool (默认True)
    返回邮件对象列表
    """
    # 使用限制条件构建筛选字符串（Restrict方法）
    # 注意：日期格式需为Outlook可识别的格式
    filters = []
    if criteria.get('subject_contains'):
        filters.append(f"@SQL=\"http://schemas.microsoft.com/mapi/proptag/0x0037001f\" LIKE '%{criteria['subject_contains']}%'")
    if criteria.get('from_email'):
        filters.append(f"@SQL=\"http://schemas.microsoft.com/mapi/proptag/0x0065001f\" LIKE '%{criteria['from_email']}%'")
    if criteria.get('received_after'):
        after_date = datetime.strptime(criteria['received_after'], '%Y-%m-%d').strftime('%m/%d/%Y')
        filters.append(f"[ReceivedTime] >= '{after_date}'")
    if criteria.get('received_before'):
        before_date = datetime.strptime(criteria['received_before'], '%Y-%m-%d').strftime('%m/%d/%Y')
        filters.append(f"[ReceivedTime] <= '{before_date}'")

    # 默认只筛选有附件的邮件
    if criteria.get('has_attachments', True):
        filters.append("[HasAttachments] = True")

    if not filters:
        # 无筛选条件时，默认获取最近10封有附件的邮件
        items = folder.Items
        items.Sort("[ReceivedTime]", True)  # 降序
        emails = []
        for i in range(min(10, items.Count)):
            if items[i + 1].HasAttachments:  # Items索引从1开始
                emails.append(items[i + 1])
        return emails

    # 应用所有筛选条件（用AND连接）
    filter_str = " AND ".join(filters)
    try:
        items = folder.Items.Restrict(filter_str)
        # 按时间排序
        items.Sort("[ReceivedTime]", True)
        return list(items)
    except Exception as e:
        print(f"筛选邮件出错: {e}")
        return []

def save_attachments(attachments, dest_folder):
    """保存附件到指定文件夹，返回保存的文件路径列表"""
    saved_paths = []
    for attachment in attachments:
        filename = attachment.FileName
        # 避免路径冲突，添加前缀
        safe_path = os.path.join(dest_folder, filename)
        # 如果文件已存在，添加数字后缀
        base, ext = os.path.splitext(safe_path)
        counter = 1
        while os.path.exists(safe_path):
            safe_path = f"{base}_{counter}{ext}"
            counter += 1
        attachment.SaveAsFile(safe_path)
        saved_paths.append(safe_path)
    return saved_paths

def send_email(recipient, subject, body, attachments=None):
    """发送邮件（使用默认账户）"""
    outlook = get_outlook_app()
    mail = outlook.CreateItem(0)  # 0 = olMailItem
    mail.To = recipient
    mail.Subject = subject
    mail.Body = body
    if attachments:
        for file_path in attachments:
            mail.Attachments.Add(file_path)
    mail.Send()
    return f"邮件已发送至 {recipient}"