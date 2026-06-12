import re

def normalize_report_markdown(text: str) -> str:
    if not text:
        return ""

    # Replace headings with numbering
    # We want to replace headers like:
    # "### 1) Insight chính", "### 1. Insight chính", "### Insight chính", etc.
    # We will do replacement using regexes to clean up numbering on key headers.
    
    # Define heading patterns with potential numbering
    heading_patterns = [
        (r'###\s*(?:\d+[\)\.]\s*)?Insight chính', '### Nhận định chính'),
        (r'###\s*(?:\d+[\)\.]\s*)?Nhận định chính', '### Nhận định chính'),
        (r'###\s*(?:\d+[\)\.]\s*)?Bằng chứng số liệu ngắn gọn', '### Bảng số liệu tóm tắt'),
        (r'###\s*(?:\d+[\)\.]\s*)?Bằng chứng số liệu', '### Cơ sở số liệu'),
        (r'###\s*(?:\d+[\)\.]\s*)?Các mốc bất thường', '### Các biến động đáng chú ý'),
        (r'###\s*(?:\d+[\)\.]\s*)?Diễn giải ý nghĩa tài chính', '### Diễn giải tài chính'),
        (r'###\s*(?:\d+[\)\.]\s*)?Diễn giải sau biểu đồ để chốt insight', '### Diễn giải tài chính'),
        (r'###\s*(?:\d+[\)\.]\s*)?Kết luận điều hành', '### Nhận định tổng hợp'),
        (r'###\s*(?:\d+[\)\.]\s*)?Cơ sở số liệu', '### Cơ sở số liệu'),
        (r'###\s*(?:\d+[\)\.]\s*)?Các biến động đáng chú ý', '### Các biến động đáng chú ý'),
        (r'###\s*(?:\d+[\)\.]\s*)?Bảng số liệu tóm tắt', '### Bảng số liệu tóm tắt'),
        (r'###\s*(?:\d+[\)\.]\s*)?Diễn giải tài chính', '### Diễn giải tài chính'),
        (r'###\s*(?:\d+[\)\.]\s*)?Nội dung cần theo dõi', '### Nội dung cần theo dõi'),
    ]
    
    lines = text.split('\n')
    for i, line in enumerate(lines):
        # Apply heading patterns specifically to lines starting with ###
        if line.strip().startswith('###'):
            for pattern, repl in heading_patterns:
                if re.match(r'^\s*' + pattern, line):
                    lines[i] = repl
                    break
        else:
            # For non-heading occurrences of these terms (e.g. inside text)
            # but we should be careful to avoid destroying tables or specific words.
            pass

    text = '\n'.join(lines)

    # General replacements of terms
    replacements = [
        ("### 1) Insight chính", "### Nhận định chính"),
        ("### Insight chính", "### Nhận định chính"),
        ("1) Insight chính", "### Nhận định chính"),
        ("Insight chính", "Nhận định chính"),
        
        ("Bằng chứng số liệu ngắn gọn", "Bảng số liệu tóm tắt"),
        ("Bằng chứng số liệu", "Cơ sở số liệu"),
        ("Các mốc bất thường", "Các biến động đáng chú ý"),
        ("Diễn giải ý nghĩa tài chính", "Diễn giải tài chính"),
        ("Diễn giải sau biểu đồ để chốt insight", "Diễn giải tài chính"),
        ("Kết luận điều hành", "Nhận định tổng hợp"),
        
        ("tiền bị kẹt", "vốn lưu động bị ứ đọng"),
        ("vốn bị giam", "vốn lưu động bị ứ đọng"),
        ("bật tăng mạnh", "tăng đáng kể"),
        ("bứt phá mạnh", "tăng rõ rệt"),
        ("đi ngang", "duy trì tương đối ổn định"),
        ("dòng tiền thật", "dòng tiền từ hoạt động kinh doanh"),
        ("tiền thật", "dòng tiền thu về"),
        ("doanh nghiệp khỏe", "tình hình tài chính an toàn"),
    ]

    for old, new in replacements:
        # Avoid replacing keys in a way that breaks markdown links or formatting if they are exactly mapped
        text = text.replace(old, new)

    return text

def normalize_all_sections(sections: dict[str, str]) -> dict[str, str]:
    return {key: normalize_report_markdown(value) for key, value in sections.items()}
