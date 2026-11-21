import hashlib
import json
import re
from collections import Counter

from fastapi import HTTPException
from app.grading.schemas import word_count


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def validate_input(prompt, essay):
    count = word_count(essay)
    if not 50 <= count <= 1200:
        raise HTTPException(422, 'Bài viết cần có từ 50 đến 1.200 từ để được chấm.')
    words = re.findall(r"\w+", essay.casefold())
    frequencies = Counter(words)
    if frequencies and (max(frequencies.values()) / len(words) > .35 or len(frequencies) < 8):
        raise HTTPException(422, 'Bài viết có quá nhiều từ lặp lại. Hãy kiểm tra nội dung.')
    if len(re.findall(r'[^\w\s.,!?;:\x27"()\-—]', essay)) > len(essay) * .3:
        raise HTTPException(422, 'Không thể đọc nội dung bài viết. Hãy gửi văn bản tiếng Anh.')
    warnings = ['under_250_words'] if count < 250 else []
    chunks = lambda s: set(zip(*[re.findall(r'\w+', s.lower())[i:] for i in range(5)]))
    essay_chunks, prompt_chunks = chunks(essay), chunks(prompt)
    if essay_chunks and len(essay_chunks & prompt_chunks) / len(essay_chunks) > .5:
        warnings.append('high_prompt_copy_overlap')
    return count, warnings


def redact_pii(text):
    # Best effort only. Preserve length so existing character offsets remain meaningful.
    patterns = (r'[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}', r'(?<!\w)\+?\d[\d ().-]{7,}\d(?!\w)')
    for pattern in patterns:
        text = re.sub(pattern, lambda match: 'x' * len(match.group()), text)
    return text
from app.entitlements import get_user_quota_status
