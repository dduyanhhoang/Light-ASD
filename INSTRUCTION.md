# Hướng dẫn Pipeline Gán nhãn Active Speaker Detection

Hướng dẫn đầy đủ từ chạy inference trên video mới đến gán nhãn kết quả để đánh giá mô hình.

---

## Yêu cầu

Cài [uv](https://docs.astral.sh/uv/getting-started/installation/) và clone repo này. Sau đó cài dependencies:

```bash
uv sync
```

Cần có `ffmpeg` trên máy:

```bash
# Ubuntu / Debian
sudo apt install ffmpeg

# macOS
brew install ffmpeg
```

File weight pretrained phải ở `weight/pretrain_AVA_CVPR.model`. Tải riêng nếu chưa có.

---

## Bước 1 — Chạy pipeline inference

Đặt file video vào thư mục `demo/`, sau đó chạy:

```bash
uv run python Columbia_test.py \
    --videoName <tên_video> \
    --videoFolder demo \
    --pretrainModel weight/pretrain_AVA_CVPR.model
```

Thay `<tên_video>` bằng tên file **không có đuôi** (ví dụ với `demo/video.mp4` thì dùng `--videoName video`).

Pipeline sẽ tạo ra thư mục `demo/<tên_video>/` với cấu trúc:

```
demo/<tên_video>/
├── pyavi/
│   ├── audio.wav        # audio trích xuất (16kHz mono)
│   ├── video.avi        # video re-encode ở 25fps
│   ├── video_only.avi   # video kết quả với bounding box (không có audio)
│   └── video_out.avi    # video kết quả với bounding box + audio
├── pyframes/            # toàn bộ frame video dạng JPEG (000001.jpg …)
├── pycrop/              # clip mặt đã crop theo từng track (00000.avi + .wav …)
└── pywork/
    ├── scene.pckl       # thời điểm chuyển cảnh
    ├── faces.pckl       # kết quả phát hiện mặt theo từng frame
    ├── tracks.pckl      # face tracks (chuỗi bbox liên tục)
    └── scores.pckl      # điểm ASD theo từng frame của mỗi track
```

**Thời gian chạy:** tùy theo độ dài video và phần cứng. Bước phát hiện mặt chậm nhất (~300–500 frame/giây trên GPU).

---

## Bước 2 — Xuất file CSV gán nhãn

Chuyển kết quả pipeline thành CSV đã được điền sẵn dự đoán của mô hình:

```bash
uv run python export_annotations.py --videoFolder demo/<tên_video>
```

Tạo ra `demo/<tên_video>/annotations.csv` với một hàng cho mỗi face-frame:

| cột | mô tả |
|---|---|
| `track_id` | chỉ số track mặt |
| `frame` | số frame trong video (đếm từ 0) |
| `x1 y1 x2 y2` | bounding box trong tọa độ video gốc |
| `model_score` | điểm ASD thô — dương = đang nói |
| `speaking` | nhãn gợi ý (0/1) từ điểm mô hình, **cần chỉnh cột này** |

---

## Bước 3 — Chạy công cụ gán nhãn

```bash
uv run python annotate.py --videoFolder demo/<tên_video>
```

Mở trình duyệt và truy cập **http://localhost:5000**.

### Giao diện

- **Sidebar trái** — danh sách tất cả track mặt kèm thanh % đang nói; click để tải track
- **Canvas giữa** — frame video đầy đủ với bounding box (xanh lá = đang nói, đỏ = không nói), điểm score hiển thị góc trên
- **Timeline** — đồ thị score (trên) và nhãn speaking (dưới); kéo để chọn vùng frame
- **Thanh điều khiển** — nút play/pause, 🔊 tắt tiếng, thanh âm lượng

### Phím tắt

| Phím | Hành động |
|---|---|
| `Space` | Play / Pause |
| `← / →` | Frame trước / sau |
| `Shift + ← / →` | Nhảy 10 frame |
| `S` | Đánh dấu vùng chọn (hoặc frame hiện tại) là **Đang nói** |
| `N` | Đánh dấu vùng chọn (hoặc frame hiện tại) là **Không nói** |
| `Esc` | Xóa vùng chọn |
| `Ctrl+S` | Lưu vào CSV |

---

## Hướng dẫn gán nhãn

Cột `speaking` đã được **điền sẵn bởi mô hình** — chỉ cần sửa những chỗ sai.

**Quy trình hiệu quả:**
1. Nhấn `Space` để phát track kèm âm thanh
2. Quan sát màu bounding box và lắng nghe — hai thứ phải khớp nhau
3. Chỗ nào không khớp thì dừng lại, kéo trên timeline để chọn vùng sai, nhấn `S` hoặc `N` để sửa
4. `Ctrl+S` để lưu rồi chuyển sang track tiếp theo

**Tập trung sửa ở đâu:**
- Vùng score gần 0 (−0,5 đến +0,5) trên timeline — mô hình không chắc chắn ở đây
- Frame bị flip ngắn giữa câu (mô hình đôi khi giảm về 0 trong khoảng ngừng tự nhiên khi nói)
- Nhiều mặt trong frame — mô hình có thể gán nhầm người đang nói

**Có thể bỏ qua:**
- Track nào score luôn mạnh (>1,0 hoặc <−1,0) xuyên suốt — mô hình thường đúng
- Track rất ngắn (<10 frame) — ảnh hưởng không đáng kể đến kết quả đánh giá

**Lưu thường xuyên.** Công cụ đọc lại CSV đã lưu khi khởi động lại, tiến độ không bị mất.

---

## Bước 4 — Đánh giá (sau khi gán nhãn xong)

Sau khi `annotations.csv` đã được gán nhãn đầy đủ, tính F1 và accuracy:

```bash
uv run python evaluate.py --videoFolder demo/<tên_video>
```

> **Lưu ý:** `evaluate.py` chưa được viết. Script này sẽ đọc cột `speaking` đã sửa và so sánh trực tiếp với dự đoán `score > 0` của mô hình — không cần khớp identity hay IoU vì nhãn đã được căn chỉnh theo track.
