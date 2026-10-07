# Retention manifest — cleanup completed

Ngày thực hiện: 2026-09-22

## Allowlist còn lại trong repo

- `data/raw/**` — 27 file, 18,399,064 bytes; hash trước/sau không đổi.
- `.gitignore`
- `README.md`
- File manifest này.

Git history trong `.git/` được giữ nguyên. Không commit và không push.

## Crawler

Không phát hiện crawler thực sự trong repo. Không có code gọi HTTP/API/browser hoặc download trực tiếp được giữ lại.

## Đã chuyển vào quarantine

Các pipeline ETL, processed/final data, notebooks, artifacts, tests, docs cũ, helper checklist và metadata workflow đã được chuyển khỏi repo vào:

`C:\tmp\interest-rate-forecast-quarantine-20260922-172624`

Quarantine có `moved_paths.txt`, `raw_hashes_before.csv` và `raw_hashes_after.csv` để đối chiếu/khôi phục.

## Verification

- Root ngoài allowlist: 0
- Path ngoài `data/raw` trong `data/`: 0
- Path ngoài manifest trong `docs/`: 0
- Raw file count trước/sau: `27 / 27`
- Raw byte count trước/sau: `18,399,064 / 18,399,064`
- Raw hashes unchanged: `True`
