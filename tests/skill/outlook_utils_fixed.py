# outlook_utils_fixed.py - 修复Outlook筛选问题
import os
import win32com.client
from datetime import datetime, timedelta
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
    根据条件查找邮件（使用简单的手动筛选，避免SQL语法问题）
    criteria: dict，支持字段：
        - subject_contains: str
        - from_email: str (发件人包含)
        - received_after: str (YYYY-MM-DD)
        - received_before: str
        - has_attachments: bool (默认True)
    返回邮件对象列表
    """
    try:
        items = folder.Items
        items.Sort("[ReceivedTime]", True)  # 降序，最新的在前面
        
        filtered_emails = []
        count = 0
        max_emails_to_check = 50  # 最多检查50封邮件，避免性能问题
        
        for i in range(min(max_emails_to_check, items.Count)):
            # Items索引从1开始
            try:
                item = items[i + 1]
                
                # 检查是否有附件（如果要求有附件）
                if criteria.get('has_attachments', True) and not item.HasAttachments:
                    continue
                    
                # 检查主题是否包含关键词
                if criteria.get('subject_contains'):
                    subject = item.Subject or ""
                    if criteria['subject_contains'].lower() not in subject.lower():
                        continue
                
                # 检查发件人
                if criteria.get('from_email'):
                    sender = item.SenderEmailAddress or ""
                    if criteria['from_email'].lower() not in sender.lower():
                        continue
                
                # 检查接收时间
                received_time = item.ReceivedTime
                if criteria.get('received_after'):
                    after_date = datetime.strptime(criteria['received_after'], '%Y-%m-%d')
                    if received_time < after_date:
                        continue
                        
                if criteria.get('received_before'):
                    before_date = datetime.strptime(criteria['received_before'], '%Y-%m-%d')
                    if received_time > before_date:
                        continue
                
                # 所有条件都满足，添加到结果
                filtered_emails.append(item)
                count += 1
                
                # 限制最多返回10封邮件
                if count >= 10:
                    break
                    
            except Exception as e:
                print(f"处理邮件时出错（索引{i+1}）: {e}")
                continue
                
        return filtered_emails
        
    except Exception as e:
        print(f"查找邮件时出错: {e}")
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

def debug_find_emails():
    """调试邮件查找"""
    print("=" * 60)
    print("Outlook邮件调试")
    print("=" * 60)
    
    inbox = get_inbox()
    items = inbox.Items
    
    print(f"\n收件箱总邮件数: {items.Count}")
    
    # 按时间排序
    items.Sort("[ReceivedTime]", True)  # 降序，最新的在前面
    
    print("\n=== 最近20封邮件详情 ===")
    for i in range(min(20, items.Count)):
        try:
            item = items[i + 1]  # Items索引从1开始
            print(f"\n[{i+1}] 主题: {item.Subject}")
            print(f"    发件人: {item.SenderEmailAddress}")
            print(f"    接收时间: {item.ReceivedTime}")
            print(f"    有附件: {item.Attachments.Count - 1}")
            if item.Attachments.Count > 1:
                print(f"    附件数量: {item.Attachments.Count}")
        except Exception as e:
            print(f"    错误: {e}")
    
    # 测试搜索功能
    subject_keyword = "Weekly Summary Report"
    print(f"\n=== 搜索包含 '{subject_keyword}' 的邮件 ===")
    
    found_count = 0
    for i in range(min(items.Count, 100)):  # 检查更多邮件
        try:
            item = items[i + 1]
            
            # 检查主题是否包含关键词（不区分大小写）
            if item.Subject and subject_keyword.lower() in item.Subject.lower():
                found_count += 1
                print(f"\n找到 #{found_count}: ")
                print(f"    主题: {item.Subject}")
                print(f"    发件人: {item.SenderEmailAddress}")
                print(f"    接收时间: {item.ReceivedTime}")
                print(f"    有附件: {item.HasAttachments}")
                
        except Exception as e:
            continue
    
    if found_count == 0:
        print("\n未找到包含该关键词的邮件！")
        print("\n请检查：")
        print("1. 邮件是否在收件箱中（可能在其他文件夹）")
        print("2. 主题拼写是否正确")
        print("3. 邮件是否已被删除或移动")
    else:
        print(f"\n共找到 {found_count} 封包含该关键词的邮件")


if __name__ == "__main__":
    # 测试函数
    try:
        inbox = get_inbox()
        print(f"收件箱邮件总数: {inbox.Items.Count}")
        debug_find_emails()
        
        # 测试查找最近的邮件
        criteria = {
            'has_attachments': True,
            'subject_contains': 'test'
        }
        emails = find_emails(inbox, criteria)
        print(f"找到 {len(emails)} 封符合条件的邮件")
        
        if emails:
            for email in emails:
                print(f"主题: {email.Subject}, 发件人: {email.SenderEmailAddress}, 附件: {email.HasAttachments}")
    except Exception as e:
        print(f"测试失败: {e}")