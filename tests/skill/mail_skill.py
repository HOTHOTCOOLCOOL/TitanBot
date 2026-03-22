# main_skill.py
import os
import tempfile
from pathlib import Path
from datetime import datetime
from outlook_utils import get_inbox, find_emails, save_attachments, send_email
from attachment_parser import parse_attachment
from analyzer import analyze_content

def process_emails_attachments(
    subject_contains=None,
    from_email=None,
    received_after=None,
    received_before=None,
    analysis_type="summary",
    recipient_email=None,
    save_results_to=None
):
    """
    查找符合条件的邮件，提取附件，解析并分析，最后将分析结果发送邮件。
    参数说明：
        subject_contains: 邮件主题包含的关键词（可选）
        from_email: 发件人包含的邮箱地址（可选）
        received_after: 接收日期之后，格式 YYYY-MM-DD（可选）
        received_before: 接收日期之前（可选）
        analysis_type: 分析类型，可选 summary / keywords / full
        recipient_email: 结果接收邮箱（必填）
        save_results_to: 本地保存分析结果的目录，默认桌面（可选）
    返回操作结果字符串。
    """
    if not recipient_email:
        return "错误：必须提供收件人邮箱 (recipient_email)"

    # 构建搜索条件
    criteria = {
        'subject_contains': subject_contains,
        'from_email': from_email,
        'received_after': received_after,
        'received_before': received_before,
        'has_attachments': True
    }
    # 去除值为None的项
    criteria = {k: v for k, v in criteria.items() if v is not None}

    try:
        inbox = get_inbox()
        emails = find_emails(inbox, criteria)
    except Exception as e:
        return f"查找邮件失败: {e}"

    if not emails:
        return "未找到符合条件的邮件。"

    # 确定保存路径
    if save_results_to:
        save_dir = Path(save_results_to)
    else:
        save_dir = Path.home() / "Desktop"
    save_dir.mkdir(parents=True, exist_ok=True)

    processed_count = 0
    report_lines = []

    for email in emails:
        # 为每封邮件创建一个临时目录存放附件
        with tempfile.TemporaryDirectory() as tmpdir:
            attachments = email.Attachments
            if attachments.Count == 0:
                continue  # 理论上不会发生，因为已筛选
            saved_files = save_attachments(attachments, tmpdir)
            email_info = f"邮件主题: {email.Subject}, 发件人: {email.SenderEmailAddress}, 接收时间: {email.ReceivedTime}"
            report_lines.append(email_info)

            for file_path in saved_files:
                # 解析附件内容
                content = parse_attachment(file_path)
                # 分析内容
                analysis_result = analyze_content(content, analysis_type)
                # 保存分析结果到文件
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                base_name = os.path.basename(file_path)
                result_filename = f"analysis_{base_name}_{timestamp}.txt"
                result_path = save_dir / result_filename
                with open(result_path, 'w', encoding='utf-8') as f:
                    f.write(f"原始附件: {base_name}\n")
                    f.write(f"邮件信息: {email_info}\n")
                    f.write("="*50 + "\n")
                    f.write(analysis_result)

                report_lines.append(f"  附件 {base_name} 分析结果已保存至: {result_path}")
                processed_count += 1

    # 生成汇总报告
    summary = f"共处理 {processed_count} 个附件。\n" + "\n".join(report_lines)

    # 发送邮件（将汇总报告作为正文，附件可选是否附上分析结果文件）
    # 这里简单将摘要作为邮件正文发送，如果需要可附上所有结果文件
    send_email(recipient_email, "邮件附件分析完成", summary)  # 可扩展附件

    return f"处理完成！结果已保存至 {save_dir}，并发送邮件至 {recipient_email}。"

def main():
    result = process_emails_attachments(
        subject_contains="Weekly Summary Report",
        from_email="davidliu@valueretailchina.com",
        analysis_type="summary",
        recipient_email="DAVIDMSN@HOTMAIL.COM"
    )
    print(result)

if __name__ == "__main__":
    main()