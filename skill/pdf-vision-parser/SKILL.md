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
Thực hiện bằng driver tự động của Gemini CLI. Không dừng sau từng batch để chờ người dùng gõ "Tiếp tục"; nếu bị giới hạn quota/auth/QA thật sự thì dừng fail-fast và giữ workspace để resume.

## BƯỚC 1: TIỀN XỬ LÝ
- Slash command `/pdf-convert` chạy `bash /home/dung/.gemini/pdf-convert/auto_convert.sh "<input>" --name "<output_name>" --keep-temp`.
- Driver gọi `prepare_native_workspace.sh` để render/cache deterministic và tạo `native_manifest.json`. Output PNG dùng 1-indexed, zero-padded: `0001.png`, `0002.png`...

## BƯỚC 2: BÓC TÁCH THỊ GIÁC CHUẨN LANDING.AI (Vision Loop)
- Driver dùng Gemini CLI subprocess theo từng trang (`gemini -p`) để nhìn ảnh `page_X.png`. Mỗi subprocess chỉ nhận một trang nên không làm tràn context của chat đang chạy.
- Ghi Markdown ra `/tmp/pdf_convert_<output_name>/temp_md/page_X.md`. Skip file đã hợp lệ để resume.
- Dòng đầu tiên của mỗi file phải là `<!-- VISION_SOURCE: <đường_dẫn_png> -->` để chứng minh trang được xử lý từ ảnh render.
- CẤM tạo script kiểu `generate_md.py` để dump text từ Docling JSON sang Markdown. Không fallback text-only cho trang cần vision.
- Mọi trang trong `native_manifest.json.visual_candidates` bắt buộc phải được mở ảnh PNG và mô tả visual semantics chi tiết.

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
- Với biểu đồ/sơ đồ/tinh đồ/grid có chữ, KHÔNG chỉ chép caption hoặc label. Phải vừa chép mọi chữ đọc được, vừa thêm `<:: ... : figure ::>` mô tả chi tiết các nút/ô, vị trí tương đối, đường nối, mũi tên, nét đứt/liền, màu sắc/số thứ tự và quan hệ không gian.
- Nếu visual là bảng/lưới có cấu trúc, phải dùng HTML `<table>` cho dữ liệu ô; nếu có đường nối/mũi tên/quan hệ tổng thể ngoài ô bảng thì vẫn phải thêm ontology `figure`.

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

## Auth & Model — Automated Gemini CLI OAuth Driver

`/pdf-convert` dùng driver tự động `/home/dung/.gemini/pdf-convert/auto_convert.sh`.
Driver được phép gọi `gemini -p` theo từng trang vì đây là cách duy nhất để tài liệu
lớn chạy tới cuối mà không cần người dùng gõ "Tiếp tục" giữa các lượt chat.

Luồng đúng:

1. Chạy `prepare_native_workspace.sh` để Docling/render/cache deterministic.
2. Driver gọi `step2_gemini_refine.py` với `PDF_CONVERT_ALLOW_GEMINI_SUBPROCESS=1`.
3. Mỗi lời gọi Gemini chỉ xử lý một trang PNG và ghi `temp_md/page_N.md`.
4. Chạy QA bằng `native_manifest.json`; trang lỗi bị xóa và xử lý lại.
5. Chỉ merge JSON sau khi QA pass. Nếu quota/auth/QA vẫn fail sau retry, giữ workspace để resume.

Không dùng Google GenAI SDK, Vertex hoặc API key. `gemini_client.py` strip các biến
môi trường API-key/Vertex để ép subprocess dùng OAuth của Gemini CLI.

**Quota-aware model switch (interactive)**:

- Default vẫn dùng đúng model active trong CLI session (không tự ý đổi).
- Khi gặp `RESOURCE_EXHAUSTED/429`, driver gọi `_verify_quota_truly_exhausted()` (probe call) để loại false-positive.
- Nếu xác nhận exhausted thật, prompt qua `/dev/tty` liệt kê các model user **đã từng dùng** (lấy từ `~/.gemini/tmp/*/chats/*.jsonl` — không hardcode):
  ```
  ⚠️  QUOTA EXHAUSTED — model: gemini-3.1-pro-preview
  Pick a replacement model for the rest of this run:
    [1] gemini-2.5-pro
    [2] gemini-2.5-flash
    [q] Stop + keep workspace for resume
  Choose:
  ```
- Lựa chọn của user chỉ áp dụng **trong process hiện tại** (in-memory `_RESOLVED_MODEL_CACHE`); không ghi vào `~/.gemini/settings.json`, không phá CLI session.
- Nếu `/dev/tty` không khả dụng → ghi `QUOTA_PROMPT.json` vào workspace + exit để user resume bằng `GEMINI_MODEL=<chosen> /pdf-convert ...`.
- Nếu user chọn `q` hoặc không còn model thay thế → terminal quota → giữ workspace để resume sau.
- Mọi lần switch đều exclude các model đã exhausted khỏi list lần sau.

**Fail-fast visual guardrail**:

- `prepare_native_workspace.sh` tạo `native_manifest.json.visual_candidates` bằng cách so sánh PNG với bbox text/table từ Docling.
- `step2.75_qa_sweep.py --manifest native_manifest.json` sẽ FAIL nếu trang có visual candidate nhưng Markdown thiếu mô tả `figure`/HTML table phù hợp.
- QA cũng FAIL nếu trang nhắc tới hình/đồ/sơ đồ/biểu đồ nhưng thiếu `<:: mô tả chi tiết : figure ::>`.
