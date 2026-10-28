import os

# torch (EasyOCR) and XGBoost each bundle libomp on macOS; two OpenMP pools in one process segfault.
os.environ.setdefault("OMP_NUM_THREADS", "1")
