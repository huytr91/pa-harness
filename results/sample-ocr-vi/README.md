# SAMPLE OCR beachhead — operational results

Exported: `2026-09-16T14:24:14.842614+00:00`

## Evidence level

Latency/RAM/success measured on contributor machine via PDF text-layer extract (pypdf). Not full scan-OCR (Tesseract/Paddle). Quality is relative cross-pipeline agreement, not ground-truth CER/accuracy. No PDF bytes or document text included. likely_scan_heuristic = mean extracted text_chars < 400.

**Hardware:** `Intel64 Family 6 Model 186 Stepping 3, GenuineIntel` · 10 cores · RAM `8-16GB` · GPU `none`

**Workload:** 16 PDFs × 3 runs × 2 pipelines = **96** measured runs.

## Observations (aggregated)

| pipeline | p50 ms | p95 ms | RAM MB | success | quality* | runs |
|----------|--------|--------|--------|---------|----------|------|
| `vn-pdf-extract-deep-v1` | 569.7 | 47396.2 | 256.4 | 100% | 0.464 | 48 |
| `vn-pdf-extract-lite-v1` | 340.3 | 18961.7 | 169.7 | 100% | 0.536 | 48 |

\*quality = relative cross-pipeline agreement on extracted text, **not** CER/accuracy.

## Per-pipeline extract detail

| pipeline | n | mean lat ms | p50 | p95 | RAM MB | mean text_chars | likely_scan share |
|----------|---|-------------|-----|-----|--------|-----------------|-------------------|
| `vn-pdf-extract-deep-v1` | 48 | 7823.8 | 569.7 | 47396.2 | 131.5 | 11296 | 56% |
| `vn-pdf-extract-lite-v1` | 48 | 4487.1 | 340.3 | 18961.7 | 107.2 | 2534 | 62% |

## Per-sample means

| pipeline | sample | mean lat ms | RAM MB | text_chars | likely_scan | success |
|----------|--------|-------------|--------|------------|-------------|---------|
| `vn-pdf-extract-deep-v1` | `20240423_20240419___dag___cbtt_bao_cao_thuong_nien_2023__ban_cbtt_.pdf` | 759.5 | 100.3 | 0 | yes | 100% |
| `vn-pdf-extract-lite-v1` | `20240423_20240419___dag___cbtt_bao_cao_thuong_nien_2023__ban_cbtt_.pdf` | 597.4 | 72.4 | 0 | yes | 100% |
| `vn-pdf-extract-deep-v1` | `2025_1581 + 1582_99-2025-TT-BTC.pdf` | 9015.3 | 96.3 | 40476 | no | 100% |
| `vn-pdf-extract-lite-v1` | `2025_1581 + 1582_99-2025-TT-BTC.pdf` | 557.7 | 71.7 | 9245 | no | 100% |
| `vn-pdf-extract-deep-v1` | `20260730-SHB-Bao-cao-tai-chinh-Q2.2026-Hop-nhat.pdf` | 155.5 | 89.2 | 0 | yes | 100% |
| `vn-pdf-extract-lite-v1` | `20260730-SHB-Bao-cao-tai-chinh-Q2.2026-Hop-nhat.pdf` | 73.1 | 71.7 | 0 | yes | 100% |
| `vn-pdf-extract-deep-v1` | `20260903___dgc___cbtt_nghi_quyet_hdqt_32_thong_qua_chot_dscd_tra_co_tuc_2025_2026.pdf` | 54.5 | 104.2 | 0 | yes | 100% |
| `vn-pdf-extract-lite-v1` | `20260903___dgc___cbtt_nghi_quyet_hdqt_32_thong_qua_chot_dscd_tra_co_tuc_2025_2026.pdf` | 39.8 | 82.3 | 0 | yes | 100% |
| `vn-pdf-extract-deep-v1` | `22-nhnn.pdf` | 5544.8 | 129.4 | 38988 | no | 100% |
| `vn-pdf-extract-lite-v1` | `22-nhnn.pdf` | 1298.0 | 121.4 | 10953 | no | 100% |
| `vn-pdf-extract-deep-v1` | `98-btc.pdf` | 276.5 | 115.6 | 0 | yes | 100% |
| `vn-pdf-extract-lite-v1` | `98-btc.pdf` | 196.3 | 96.8 | 0 | yes | 100% |
| `vn-pdf-extract-deep-v1` | `BCTN+2026+TV+21.4+VIEW+(1).pdf` | 62912.0 | 115.2 | 33385 | no | 100% |
| `vn-pdf-extract-lite-v1` | `BCTN+2026+TV+21.4+VIEW+(1).pdf` | 1048.2 | 114.1 | 44 | yes | 100% |
| `vn-pdf-extract-deep-v1` | `BCTN_2025_ad403f779b.pdf` | 38470.8 | 107.2 | 64340 | no | 100% |
| `vn-pdf-extract-lite-v1` | `BCTN_2025_ad403f779b.pdf` | 47980.9 | 107.2 | 17334 | no | 100% |
| `vn-pdf-extract-deep-v1` | `CEO_Baocaotaichinh_6T_2026_Soatxet_Hopnhat.pdf` | 948.5 | 141.3 | 0 | yes | 100% |
| `vn-pdf-extract-lite-v1` | `CEO_Baocaotaichinh_6T_2026_Soatxet_Hopnhat.pdf` | 519.0 | 116.9 | 0 | yes | 100% |
| `vn-pdf-extract-deep-v1` | `DXG_Baocaotaichinh_6T_2026_Soatxet_Hopnhat.pdf` | 357.5 | 141.4 | 0 | yes | 100% |
| `vn-pdf-extract-lite-v1` | `DXG_Baocaotaichinh_6T_2026_Soatxet_Hopnhat.pdf` | 160.9 | 146.8 | 0 | yes | 100% |
| `vn-pdf-extract-deep-v1` | `FPT_Baocaotaichinh_6T_2026_Soatxet_Congtyme.pdf` | 219.2 | 141.0 | 0 | yes | 100% |
| `vn-pdf-extract-lite-v1` | `FPT_Baocaotaichinh_6T_2026_Soatxet_Congtyme.pdf` | 144.7 | 129.8 | 0 | yes | 100% |
| `vn-pdf-extract-deep-v1` | `MBB_Baocaotaichinh_6T_2026_Soatxet_Hopnhat.pdf` | 579.4 | 154.4 | 1939 | no | 100% |
| `vn-pdf-extract-lite-v1` | `MBB_Baocaotaichinh_6T_2026_Soatxet_Hopnhat.pdf` | 1018.3 | 123.5 | 1939 | no | 100% |
| `vn-pdf-extract-deep-v1` | `MSB_Baocaotaichinh_Q2_2026_Hopnhat.pdf` | 83.3 | 163.7 | 0 | yes | 100% |
| `vn-pdf-extract-lite-v1` | `MSB_Baocaotaichinh_Q2_2026_Hopnhat.pdf` | 153.1 | 95.5 | 0 | yes | 100% |
| `vn-pdf-extract-deep-v1` | `MWG_Baocaotaichinh_6T_2026_Soatxet_Congtyme.pdf` | 2136.5 | 228.7 | 547 | no | 100% |
| `vn-pdf-extract-lite-v1` | `MWG_Baocaotaichinh_6T_2026_Soatxet_Congtyme.pdf` | 6347.2 | 137.7 | 547 | no | 100% |
| `vn-pdf-extract-deep-v1` | `toan-tien-tieu-hoc-tap-3-cac-phep-tinh.pdf` | 3550.9 | 166.4 | 1060 | no | 100% |
| `vn-pdf-extract-lite-v1` | `toan-tien-tieu-hoc-tap-3-cac-phep-tinh.pdf` | 11359.4 | 131.7 | 481 | no | 100% |
| `vn-pdf-extract-deep-v1` | `tt-111.pdf` | 117.0 | 110.0 | 0 | yes | 100% |
| `vn-pdf-extract-lite-v1` | `tt-111.pdf` | 298.8 | 95.2 | 0 | yes | 100% |

## Reproduce

```bash
cd pa-harness
python cli.py run \
  --problem problem.ocr-sample.yaml \
  --pipelines pipelines/vn-pdf-extract-lite-v1.yaml pipelines/vn-pdf-extract-deep-v1.yaml \
  --samples-dir ../SAMPLE \
  --db benchmarks-sample-full.duckdb \
  --runs 3
python export_sample_results.py benchmarks-sample-full.duckdb results/sample-ocr-vi
```

PDFs stay local (gitignored). Only metrics are published.
