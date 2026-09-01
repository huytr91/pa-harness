"""
hardware_detect.py — Tự động phát hiện Hardware Fingerprint cho pa-harness.

Bản sao có chủ đích của pa-interview-agent/hardware_detect.py, cùng nguyên
tắc cứng (03-gtm-opensource-strategy.md mục 5.1): "Hardware fingerprint tự
phát hiện, không tự khai". Lý do trùng lặp thay vì import chéo giữa 2 repo:
pa-harness và pa-interview-agent là 2 gói độc lập cho tới khi pa-schema được
tách riêng (xem pa-harness/README.md) — mỗi repo tự detect lại tại thời điểm
benchmark chạy, vì hardware fingerprint ghi vào observation phải là hardware
TẠI LÚC ĐO, không phải hardware lúc phỏng vấn (máy có thể khác nhau nếu
problem.yaml được chia sẻ giữa các máy).
"""

from __future__ import annotations

import os
import platform
import subprocess
from datetime import datetime, timezone
from typing import Optional

from schemas import GPUClass, HardwareFingerprint, RamBucket

try:
    import psutil
except ImportError:  # pragma: no cover
    psutil = None


def _ram_bucket(total_mb: int) -> RamBucket:
    gb = total_mb / 1024
    if gb < 8:
        return RamBucket.lt_8gb
    if gb < 16:
        return RamBucket.r_8_16
    if gb < 32:
        return RamBucket.r_16_32
    if gb < 64:
        return RamBucket.r_32_64
    return RamBucket.gt_64


def _classify_vram(vram_mb: int) -> GPUClass:
    if vram_mb >= 40_000:
        return GPUClass.datacenter
    if vram_mb >= 16_000:
        return GPUClass.high
    if vram_mb >= 8_000:
        return GPUClass.mid
    return GPUClass.entry


def _detect_nvidia_gpu() -> tuple[GPUClass, Optional[str], Optional[int]]:
    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0 and result.stdout.strip():
            first_line = result.stdout.strip().splitlines()[0]
            name, mem_str = [p.strip() for p in first_line.split(",")]
            vram_mb = int(mem_str)
            return _classify_vram(vram_mb), name, vram_mb
    except (FileNotFoundError, subprocess.TimeoutExpired, ValueError):
        pass
    return GPUClass.none, None, None


def detect_hardware() -> HardwareFingerprint:
    """Gọi 1 lần khi bắt đầu benchmark session — kết quả gắn vào MỌI
    observation sinh ra trong session đó."""
    if psutil is not None:
        cores = psutil.cpu_count(logical=False) or psutil.cpu_count(logical=True) or 1
        ram_total_mb = int(psutil.virtual_memory().total / (1024 * 1024))
    else:
        cores = os.cpu_count() or 1
        ram_total_mb = 0

    gpu_class, gpu_model, vram_mb = _detect_nvidia_gpu()

    return HardwareFingerprint(
        cpu_class=platform.processor() or platform.machine() or "unknown",
        cores=cores,
        ram_bucket=_ram_bucket(ram_total_mb),
        ram_total_mb=ram_total_mb,
        gpu_class=gpu_class,
        gpu_model=gpu_model,
        vram_mb=vram_mb,
        os=f"{platform.system()} {platform.release()}",
        detected_at=datetime.now(timezone.utc).isoformat(),
    )
