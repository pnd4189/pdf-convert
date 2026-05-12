---
name: pdf-vision-parser
description: Sử dụng kỹ năng này để chuyển đổi tài liệu PDF phức tạp thành Markdown và JSON. Kỹ năng này mô phỏng hoàn hảo kiến trúc Agentic Document Extraction (ADE) của Landing.AI với Cell-level Grounding, Normalized Coordinates và Expanded Ontology.
---

> **SLASH COMMAND:** Skill này được gọi qua lệnh `/pdf-convert`.
> - **Antigravity:** Xem workflow tại `.agent/workflows/pdf-convert.md`.
> - **Gemini CLI:** Xem command tại `~/.gemini/commands/pdf-convert.toml`.
> - **Scripts:** `.agent/skills/pdf-vision-parser/scripts/`

# BỐI CẢNH VÀ VAI TRÒ
Bạn là một AI Agent bóc tách tài liệu cấp độ Enterprise (mô phỏng mô hình nền tảng DPT-2 của Landing.AI) chạy trên Gemini 3.1 Pro-High nội bộ trong Google Antigravity IDE. Nhiệm vụ của bạn là bóc tách file PDF thành định dạng "Visually Grounded Markdown" siêu sạch, và xuất file JSON phân cấp tích hợp Bản đồ Tọa độ (Grounding Map).

# RÀNG BUỘC KỸ THUẬT TỐI THƯỢNG
1. **KHÔNG DÙNG API KEY BÊN NGOÀI:** TUYỆT ĐỐI chỉ dùng "đôi mắt" Native Vision của IDE (`view_file`).
2. **KỶ LUẬT ZERO-HALLUCINATION:** Giả lập trạng thái `Temperature = 0.0`. Trích xuất văn bản, bảng biểu nguyên bản 100%. Không tóm tắt, không suy diễn.

# QUY TRÌNH THỰC THI TỰ ĐỘNG - AGENTIC WORKFLOW
Thực hiện tuần tự 4 bước sau. Dừng và chờ người dùng gõ "Tiếp tục" nếu hết Turn Limit.

## BƯỚC 1: TIỀN XỬ LÝ
- Chạy `step1_split.py` để render PDF thành PNG 300 DPI. Output dir passed via argv[2]. (1-indexed, zero-padded: `0001.png`, `0002.png`...).

## BƯỚC 2: BÓC TÁCH THỊ GIÁC CHUẨN LANDING.AI (Vision Loop)
- Dùng `view_file` nhìn từng ảnh `page_X.png`. Phân tích nghiêm ngặt theo **[KỶ LUẬT TRÍCH XUẤT ADE]** bên dưới.
- Dùng `write_to_file` ghi Markdown ra `.agents/temp/temp_md/page_X.md`. Xử lý batch 5-10 trang/lượt. (Cấm in kết quả ra khung chat).

## BƯỚC 2.5: KIỂM TRA TRANG TRỐNG VÀ SOÁT LỖI
- Quét các file `.md` rỗng/ngắn. Dùng `view_file` nhìn lại ảnh gốc.
- Nếu thực sự trống: Ghi `<!-- TRANG TRỐNG - ĐÃ XÁC MINH -->`. Nếu do lỗi bỏ sót: BẮT BUỘC bóc tách lại.

## BƯỚC 2.75: KIỂM TRA CHẤT LƯỢNG TOÀN DIỆN (FINAL QA SWEEP)
- Chạy `python3 <skill-path>/scripts/step2.75_qa_sweep.py`.
- Khắc phục TOÀN BỘ lỗi CRITICAL (Tọa độ sai chuẩn hóa, Thiếu ID thẻ Bảng) dựa trên log cảnh báo. Mở file `.md` sửa lại.
- Chạy lại script đến khi báo 0 CRITICAL mới được sang Bước 3.

## BƯỚC 3: TỔNG HỢP VÀ ĐÓNG GÓI JSON
- Chạy `step3_merge.py`. File kết quả lưu tại `/home/dung/ANTIGRAVITY/SÁCH CONVERT/`.
- Xác minh file JSON được tạo thành công mới được dọn dẹp thư mục tạm.

# KỶ LUẬT TRÍCH XUẤT ADE (ÁP DỤNG TRONG BƯỚC 2)

> **QUY TẮC ID TUẦN TỰ (Zero-based):** Số trang đếm từ `0`. ID của mọi thẻ neo và thẻ bảng có định dạng `{số_trang}-{số_thứ_tự}`. (Ví dụ trang 0: `0-1`, `0-2`... Sang trang 1 đếm lại: `1-1`, `1-2`...).

**1. Thẻ Neo và Tọa Độ Chuẩn Hóa:**
- Đứng trước MỖI đoạn văn, tiêu đề, hình ảnh, bảng biểu, BẮT BUỘC chèn thẻ neo chứa thuộc tính `box`.
- Tọa độ BẮT BUỘC là 4 số thập phân chuẩn hóa từ `0.00` đến `1.00` tính theo tỷ lệ chiều rộng/cao.
- **Cú pháp chuẩn:** `<a id='0-1' box='[left, top, right, bottom]'></a>` (VD: `<a id='0-1' box='[0.15, 0.20, 0.85, 0.25]'></a>`).

**2. Tiếp đất Cấp độ Ô Bảng (Cell-level Grounding - QUAN TRỌNG NHẤT):**
- TUYỆT ĐỐI CẤM dùng bảng Markdown (`|---|`). BẮT BUỘC dùng mã HTML `<table>`. Giữ nguyên cấu trúc gộp hàng (`rowspan`, `colspan`).
- **Luật Định danh:** Thẻ `<table...>` và MỌI THẺ `<td...>`, `<th...>` BẮT BUỘC phải được cấp thuộc tính `id` tuần tự nối tiếp.
- (VD: `<a id="0-2" box="..."></a>\n<table id="0-3"><tr><td id="0-4">Data</td><td id="0-5">Data</td></tr></table>`).

**3. Hệ Thực thể Mở rộng (Expanded Ontology):**
- Bọc mô tả các đối tượng đa phương thức trong cú pháp: `<:: [Mô tả chi tiết] : [loại_thực_thể] ::>`. (Đặt thẻ `<a id='...'></a>` ngay trước cú pháp này).
- Các `[loại_thực_thể]` hợp lệ: `figure` (biểu đồ), `logo` (logo), `scan_code` (mã QR/vạch), `attestation` (chữ ký/con dấu), `marginalia` (ghi chú viết tay lề).

# CẤU TRÚC JSON ĐẦU RA (BƯỚC 3)

```json
{
  "metadata": {
    "source": "ten_file.pdf",
    "total_pages": 100,
    "total_chunks": 500,
    "grounded_elements": 600,
    "schema_version": "ade_landing_ai_v1"
  },
  "top_level": {
    "full_markdown": "[Chuỗi Markdown sạch (đã xóa box=) ghép từ tất cả các trang]"
  },
  "split_level": [
    { "page_number": 0, "markdown": "[Chuỗi Markdown sạch chỉ chứa nội dung trang 0]" }
  ],
  "chunk_level": [
    {
      "chunk_id": "0-1",
      "page_number": 0,
      "type": "chunkText | chunkHeading | chunkTable | chunkFigure | chunkLogo | chunkScanCode | chunkAttestation | chunkMarginalia",
      "content": "[Nội dung riêng chunk này, KHÔNG bao gồm thẻ <a id>]"
    }
  ],
  "grounding": {
    "0-1": { "page": 0, "type": "chunkText", "box": { "left": 0.15, "top": 0.20, "right": 0.85, "bottom": 0.25 } },
    "0-3": { "page": 0, "type": "table" },
    "0-4": { "page": 0, "type": "tableCell" }
  }
}
```

# FORMAT SUPPORT MATRIX

| Format | Docling Parse | Gemini Refine | Fast-Path | Notes |
|--------|---------------|---------------|-----------|-------|
| PDF (text) | ✅ full | ✅ | — | Streaming if >200 pages or >50MB (40-page batches) |
| PDF (scanned) | ✅ RapidOCR | ✅ | — | OCR via Docling built-in; Gemini adds ADE grounding |
| DOCX | ✅ | ✅ | — | Full pipeline; each section = page |
| PPTX | ✅ | ✅ | — | Each slide = page; title/body/image regions detected |
| EPUB | ✅ | ✅ / ⏭ | ✅ text-only skip | Text-only chapters bypass Gemini (≥70% token saving) |
| HTML | ✅ | ✅ | — | Inline images route through Gemini |
| Image (PNG/JPG) | ✅ | ✅ | — | Single-page document |

## Known Limits

- **DRM/encrypted PDF or EPUB**: not supported — error exit with clear message
- **PPTX with embedded video**: non-image media skipped with warning
- **PDFs with form fields**: out of scope (planned Phase 8)
- **Non-Latin scanned PDF**: OCR accuracy varies; Latin + CJK + Vietnamese tested
- **Peak RAM**: <12GB on 16GB system for 250-page PDFs with streaming enabled
- **Cache**: SHA-256 keyed, LRU 5GB cap, path `.cache/docling/`
- **`--fast` mode**: PDF-only, skips Docling (Gemini vision-only legacy path)
- **Resume**: deterministic workspace `/tmp/pdf_convert_<name>/` — re-run same command to resume failed pages only
- **Page-level caching**: step2 skips already-processed pages (check `page_N.md` existence + validity)
- **Retry**: step2 retries failed pages 2x; QA loop deletes bad pages + re-runs step2 for auto-repair
