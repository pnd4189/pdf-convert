---
name: pdf-vision-parser
description: Sử dụng kỹ năng này để chuyển đổi tài liệu PDF phức tạp thành Markdown và JSON. Kỹ năng này mô phỏng hoàn hảo kiến trúc Agentic Document Extraction (ADE) của Landing.AI với Cell-level Grounding, Normalized Coordinates và Expanded Ontology.
---

> **SLASH COMMAND:** Skill này được gọi qua lệnh `/pdf-convert` trên **Antigravity CLI (`agy`)**.
> - **Runtime:** agy đọc workflow tại `.agent/workflows/pdf-convert.md` + skill này tại `.agent/skills/pdf-vision-parser/SKILL.md`.
> - **Scripts:** `.agent/skills/pdf-vision-parser/scripts/` (gọi tắt `<skill-path>/scripts/`).
> - **Batch nhiều file:** `bash run-folder.sh <folder>` (mỗi PDF 1 phiên `agy -p`, tuần tự).

# BỐI CẢNH VÀ VAI TRÒ
Bạn là một AI Agent bóc tách tài liệu cấp độ Enterprise (mô phỏng mô hình nền tảng DPT-2 của Landing.AI), chạy bằng **chính model active của Antigravity CLI (`agy`)**. Nhiệm vụ của bạn là bóc tách file PDF thành định dạng "Visually Grounded Markdown" siêu sạch, và xuất file JSON phân cấp tích hợp Bản đồ Tọa độ (Grounding Map).

# RÀNG BUỘC KỸ THUẬT TỐI THƯỢNG
1. **KHÔNG DÙNG API KEY BÊN NGOÀI:** TUYỆT ĐỐI chỉ dùng "đôi mắt" Native Vision của IDE (`view_file`).
2. **KỶ LUẬT ZERO-HALLUCINATION:** Giả lập trạng thái `Temperature = 0.0`. Trích xuất văn bản, bảng biểu nguyên bản 100%. Không tóm tắt, không suy diễn.

# QUY TRÌNH THỰC THI TỰ ĐỘNG - AGENTIC WORKFLOW
Chính model active trong lượt slash-command này là "đôi mắt" bóc tách — tự nhìn ảnh và tự ghi Markdown. Không dùng driver subprocess gọi API. Không dừng sau từng chunk để chờ người dùng gõ "Tiếp tục"; nếu bị lỗi đọc trang thật sự hoặc QA không đạt thì dừng fail-fast và giữ workspace để resume.

## BƯỚC 1: TIỀN XỬ LÝ (CHỈ RENDER — KHÔNG GỌI API)
- Slash command `/pdf-convert` chạy `bash <skill-path>/scripts/prepare_native_workspace.sh "<input>" --name "<output_name>" --keep-temp`.
- **Nếu workspace `/tmp/pdf_convert_<output_name>/` đã có `native_manifest.json`** (batch wrapper `run-folder.sh` đã prepare sẵn) thì **BỎ QUA bước này** — chỉ đọc manifest và sang BƯỚC 2. Không chạy lại prepare, không đổi `<output_name>`.
- Script chỉ render/cache deterministic và tạo `native_manifest.json` (preprocessing thuần — không gọi model nào, không SDK, không API key). Output PNG dùng 1-indexed, zero-padded: `0001.png`, `0002.png`...
- Đọc `native_manifest.json` lấy `png_dir`, `md_dir`, `pages`, `visual_candidates`, `skip_native_extraction`.

## BƯỚC 2: BÓC TÁCH THỊ GIÁC CHUẨN LANDING.AI (Native Vision Loop)
- **BẮT BUỘC trước khi bóc trang đầu tiên:** đọc file `<skill-path>/scripts/ade_prompt_vision.txt` — đây là HỢP ĐỒNG ĐẦU RA canonical (MANDATORY OUTPUT CONTRACT + worked example byte-chuẩn). Thay `__PNG_DIR__`/`__MD_DIR__`/`__NPAGES__` bằng giá trị từ manifest và áp dụng NGUYÊN VĂN cho mọi trang. Mục "KỶ LUẬT TRÍCH XUẤT ADE" bên dưới là cùng một spec ở dạng diễn giải; khi nghi ngờ, format trong template thắng.
- Chính model active của agy dùng công cụ đọc-file/vision native (`view_file`) mở từng ảnh `png_dir/000N.png`. KHÔNG spawn subprocess gọi model ngoài. Xử lý theo chunk ~5-10 trang, xong trang nào buông trang đó nên không tràn context dù tài liệu 100+ trang.
- **KHÔNG dừng chờ người dùng gõ "Tiếp tục".** Lượt slash-command này chạy print mode không có người ngồi gõ tiếp — tự đi hết MỌI trang trong một phiên.
- Ghi Markdown ra `<md_dir>/page_X.md` (`/tmp/pdf_convert_<output_name>/temp_md/`). Skip file đã hợp lệ để resume.
- **Quy ước số trang (chống lệch):** `page_X.md` chứa trang ID `X` (zero-based), ứng với ảnh số `X+1`. Tức `page_0.md ↔ 0001.png`, `page_9.md ↔ 0010.png`. Tuyệt đối giữ đúng ánh xạ này, không ghi nội dung ảnh `000N.png` dưới nhãn `page_N.md`.
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
- Chạy `step3_merge.py --name "<output_name>"`. File kết quả lưu tại `/home/dung/ANTIGRAVITY/SÁCH CONVERT/<output_name>.json`.
- Xác minh file JSON được tạo thành công mới được dọn dẹp thư mục tạm.

> **Chế độ batch (wrapper `run-folder.sh`):** wrapper đã làm BƯỚC 1, tự inject thẳng nội dung `ade_prompt_vision.txt` vào phiên `agy -p` (không đi qua slash command này), và sẽ tự chạy BƯỚC 2.75 + BƯỚC 3. Phiên vision CHỈ làm BƯỚC 2 (ghi đủ `page_X.md`) rồi DỪNG — không chạy QA/merge, không dọn workspace.

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
| PDF (all) | ❌ bypassed | ✅ vision-only | render PNG → Gemini | Docling unreliable on OCR'd/scanned-like PDFs → always go vision-only |
| DOCX | ✅ | ✅ | — | Full pipeline; each section = page |
| PPTX | ✅ | ✅ | — | Each slide = page; title/body/image regions detected |
| EPUB | ✅ | ✅ / ⏭ | ✅ text-only skip | Text-only chapters bypass Gemini (≥70% token saving) |
| HTML | ✅ | ✅ | — | Inline images route through Gemini |
| Image (PNG/JPG/JPEG/GIF/WEBP/BMP/TIFF) | ❌ bypassed | ✅ vision-only | normalize → `0001.png` → Gemini | Pure pixel input — nothing for Docling structural extraction to add |

**Why PDF and Image skip Docling (since 2026-05-13):** sparse Docling
extraction on OCR'd PDFs caused `visual_audit` to flag every text page as an
"uncovered visual region", which led the auto-repair loop to spin until
exhausted. Standalone images are pure pixels — Docling adds zero structural
signal. Both formats now go vision-only: normalize/render to PNG (300 DPI for
PDFs) and let the active agy model do full vision extraction directly.
Docling stays load-bearing for DOCX/PPTX/EPUB where structural extraction is
trustworthy.

## Known Limits

- **DRM/encrypted PDF or EPUB**: not supported — error exit with clear message
- **PPTX with embedded video**: non-image media skipped with warning
- **PDFs with form fields**: out of scope (planned Phase 8)
- **Non-Latin scanned PDF**: OCR accuracy varies; Latin + CJK + Vietnamese tested
- **Peak RAM**: <12GB on 16GB system for 250-page PDFs with streaming enabled
- **Cache**: SHA-256 keyed, LRU 5GB cap, path `.cache/docling/`
- **`--fast` mode**: PDF-only, skips Docling (vision-only render path)
- **Resume**: deterministic workspace `/tmp/pdf_convert_<name>/` — re-run same command to resume failed pages only
- **Page-level caching**: the native loop skips pages whose `page_N.md` already exists and is valid
- **Retry**: re-open failed pages; QA loop deletes bad `page_N.md` and re-extracts them via native vision

## Auth & Model — Active-Model Native Vision (Antigravity CLI)

`/pdf-convert` dùng **chính model active của agy** trong lượt slash-command để nhìn
ảnh và bóc tách. KHÔNG gọi model qua subprocess, KHÔNG dùng SDK / Vertex / API key.
Native vision đi qua chính phiên agy đang chạy nên không tốn quota API riêng và
không dính rate-limit.

Luồng đúng (đều không gọi model ngoài):

1. `<skill-path>/scripts/prepare_native_workspace.sh` — render PNG + Docling cache + `native_manifest.json` (preprocessing thuần).
2. Model active tự `view_file` từng PNG, tự ghi `temp_md/page_N.md`, theo chunk ~5-10 trang, resume bằng cách skip file đã hợp lệ.
3. `step2.75_qa_sweep.py` — QA thuần Python; trang lỗi sửa lại bằng cách mở lại ảnh.
4. `step3_merge.py` — merge JSON thuần Python. Chỉ merge sau khi QA đạt 0 CRITICAL.
5. Nếu một trang thật sự không đọc được hoặc QA không đạt sau retry → fail-fast, giữ workspace để resume.

**Tại sao không cần "đọc 247 trang cùng lúc":** mỗi trang xử lý xong là ghi file rồi
buông khỏi context, nên tài liệu lớn vẫn chạy hết mà không tràn context.

**Chọn model:** mặc định pin `Gemini 3.1 Pro (High)` của agy (vision/ADE mạnh nhất);
batch chỉnh qua biến `PDF_MODEL` của `run-folder.sh`.

**Lưu ý:** Google đã khai tử Gemini CLI (binary `gemini` báo `IneligibleTierError`),
nên runtime DUY NHẤT là agy native vision ở trên. KHÔNG spawn bất kỳ subprocess nào
gọi model/API ngoài (Gemini CLI, SDK GenAI, Vertex, API key) và KHÔNG đi tìm/tái tạo
các script driver subprocess đã bị xóa. Nếu cần "bước kết thúc", đó là `step3_merge.py`
(hoặc wrapper batch tự lo) — không có script orchestrator nào khác để tìm.

**Fail-fast visual guardrail**:

- Cho DOCX/PPTX/EPUB/HTML/Image: `prepare_native_workspace.sh` tạo `native_manifest.json.visual_candidates` bằng cách so sánh PNG với bbox text/table từ Docling.
- Cho PDF: manifest set `skip_visual_audit=true` → bỏ check visual_candidate (không có Docling baseline đáng tin).
- `step2.75_qa_sweep.py` exit code 0 (PASS) | 1 (HARD: anchor/box/table/vision-provenance — repair được) | 2 (SOFT-only: figure/keyword — caller có thể accept).
- QA chỉ flag keyword khi có chỉ thị tham chiếu thị giác rõ ràng ("xem hình", "biểu đồ 2.3", "圖 3", "hình bên trái"...) — không match standalone "đồ"/"hình" trong văn xuôi chuyên môn.
- Nếu QA báo HARD fail, model active mở lại đúng trang đó và sửa `.md`; SOFT-only (figure/keyword) có thể accept rồi merge. Tránh lặp vô hạn: cùng một trang fail 2 lần liên tiếp thì dừng và giữ workspace để resume.
