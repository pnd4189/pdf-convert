---
phase: 4
title: "Test with Problematic PDF"
status: pending
priority: P1
effort: "15min"
dependencies: [1, 2, 3]
---

# Phase 4: Test with Problematic PDF

## Overview
Re-run conversion on "Nhập môn tứ hóa bắc phái.pdf" and verify pages 5, 7 now contain full lá số content instead of brief captions.

## Requirements
- Clear Docling cache for this PDF
- Re-run conversion
- Verify pages 5, 7 contain significantly more content
- Verify text-heavy pages (e.g., pages 2-4) unchanged
- Verify no regression on other pages

## Implementation Steps

1. Delete Docling cache for this PDF:
```bash
rm /home/dung/ANTIGRAVITY/.agent/skills/pdf-vision-parser/scripts/.cache/docling/242380ca4ec488c5bfc892cf6d4da29d7a11a58d0e91793df883cb74a1aab10f_2.93.0.json
```

2. Re-run conversion:
```bash
cd /home/dung/ANTIGRAVITY && gemini -p "run skill /pdf-convert on 'TÀI LIỆU CONVERT (xóa sau khi convert)/Nhập môn tứ hóa bắc phái.pdf'"
```

3. Check pages 5, 7 in output JSON:
```bash
# Extract page 5 content
python3 -c "
import json
with open('SÁCH CONVERT/Nhập môn tứ hóa bắc phái.json') as f:
    data = json.load(f)
for page in data.get('split_level', []):
    if page.get('page_number') in [5, 7]:
        content = page.get('content', '')
        print(f'=== Page {page[\"page_number\"]} ===')
        print(f'Length: {len(content)} chars')
        print(content[:500])
        print('...')
        print()
"
```

4. Verify regression-free: check pages 2-4 (text-heavy) still have similar content lengths

5. Sync changes to VIBE_CODING copy:
```bash
cp /home/dung/ANTIGRAVITY/.agent/skills/pdf-vision-parser/scripts/ade_prompt_vision.txt /home/dung/VIBE_CODING/skill/pdf-vision-parser/scripts/
cp /home/dung/ANTIGRAVITY/.agent/skills/pdf-vision-parser/scripts/step2_gemini_refine.py /home/dung/VIBE_CODING/skill/pdf-vision-parser/scripts/
cp /home/dung/ANTIGRAVITY/.agent/skills/pdf-vision-parser/scripts/lib/gemini_client.py /home/dung/VIBE_CODING/skill/pdf-vision-parser/scripts/lib/
```

## Success Criteria
- [ ] Pages 5, 7 contain >500 chars of content (vs current 41-253 chars)
- [ ] Lá số chart text is transcribed (not just captioned)
- [ ] Text-heavy pages unchanged
- [ ] No new errors in step2 logs
- [ ] Changes synced to VIBE_CODING copy

## Risk Assessment
**Low** — test-only phase. If results are unsatisfactory, iterate on vision prompt wording.
