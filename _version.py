"""Một chỗ duy nhất khai báo harness_version — ghi vào MỌI observation (GTM
mục 4.3: "để biết observation chạy bằng phiên bản đo nào, quan trọng khi
schema/protocol thay đổi"). Tăng số này mỗi khi thay đổi cách đo (không phải
mỗi lần sửa code linh tinh) — vd. đổi cách tính peak_ram, đổi số run mặc định."""

HARNESS_VERSION = "0.1.0"

# Định danh protocol benchmark — dùng làm `benchmark_id` trong Observation.
# Đổi khi thay đổi PHƯƠNG PHÁP đo (vd. tăng min run_count từ 3 lên 5), không
# đổi mỗi khi sửa bug.
BENCHMARK_PROTOCOL_ID = "pa-harness-standard-v0"
