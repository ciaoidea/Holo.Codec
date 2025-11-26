#!/usr/bin/env python3
"""
Resilience test for Holo.Codec + golden permutation.

Usage:
    python3 test_resilience.py image.png \
        --block-count 32 \
        --trials 50

Crea image.png.holo (se non esiste già), poi per k = 1..B:
  - sceglie 'trials' volte un sottoinsieme casuale di k chunk
  - decodifica solo con quei chunk
  - calcola MSE e PSNR rispetto all'immagine originale
Scrive tutto in un CSV e stampa la media per ogni k.
"""

import os
import sys
import csv
import math
import shutil
import random
import tempfile

import numpy as np
from PIL import Image

import holo  # deve essere il tuo holo.py (stesso directory)


def load_rgb(path: str) -> np.ndarray:
    """Carica immagine e restituisce array uint8 shape (H, W, 3)."""
    img = Image.open(path).convert("RGB")
    return np.asarray(img, dtype=np.uint8)


def mse_psnr(orig: np.ndarray, recon: np.ndarray) -> tuple[float, float]:
    """Calcola MSE e PSNR in dB fra due immagini RGB uint8."""
    orig_f = orig.astype(np.float32)
    recon_f = recon.astype(np.float32)
    diff = orig_f - recon_f
    mse = float(np.mean(diff * diff))
    if mse <= 0.0:
        psnr = float("inf")
    else:
        max_val = 255.0
        psnr = 10.0 * math.log10((max_val * max_val) / mse)
    return mse, psnr


def ensure_holo_dir(input_path: str, block_count: int | None) -> str:
    """
    Se input_path.holo esiste lo riusa, altrimenti richiama encode_image_holo_dir.
    Restituisce il path della directory .holo.
    """
    out_dir = input_path + ".holo"
    if not os.path.isdir(out_dir):
        os.makedirs(out_dir, exist_ok=True)
        holo.encode_image_holo_dir(
            input_path=input_path,
            out_dir=out_dir,
            block_count=block_count if block_count is not None else 32,
        )
    return out_dir


def run_resilience_test(
    image_path: str,
    block_count: int | None = None,
    trials: int = 50,
    seed: int = 1234,
) -> None:
    random.seed(seed)

    orig = load_rgb(image_path)
    h, w, _ = orig.shape

    holo_dir = ensure_holo_dir(image_path, block_count)

    chunk_files = sorted(
        f for f in os.listdir(holo_dir) if f.startswith("chunk_") and f.endswith(".holo")
    )
    if not chunk_files:
        print(f"No chunk_*.holo in {holo_dir}")
        sys.exit(1)

    # uso i file presenti per determinare B
    B = len(chunk_files)
    print(f"[Test] Found {B} chunks in {holo_dir}")

    full_paths = [os.path.join(holo_dir, f) for f in chunk_files]

    base_name = os.path.splitext(os.path.basename(image_path))[0]
    csv_path = f"resilience_{base_name}.csv"

    with open(csv_path, "w", newline="") as csvfile:
        writer = csv.writer(csvfile)
        writer.writerow(["k_chunks", "trial", "mse", "psnr_db"])

        for k in range(1, B + 1):
            mse_vals = []
            psnr_vals = []
            print(f"[Test] k = {k}/{B}")

            for t in range(trials):
                chosen = random.sample(full_paths, k)

                # directory temporanea con solo i chunk scelti
                tmp_dir = tempfile.mkdtemp(prefix="holo_k{}_".format(k))
                try:
                    for src in chosen:
                        dst = os.path.join(tmp_dir, os.path.basename(src))
                        shutil.copy2(src, dst)

                    recon_path = os.path.join(tmp_dir, "recon.png")
                    holo.decode_image_holo_dir(tmp_dir, recon_path)

                    recon = load_rgb(recon_path)
                    if recon.shape != orig.shape:
                        print("[Warn] Shape mismatch, skipping one sample")
                        continue

                    mse, psnr = mse_psnr(orig, recon)
                    mse_vals.append(mse)
                    psnr_vals.append(psnr)
                    writer.writerow([k, t, mse, psnr])
                finally:
                    # pulizia della directory temporanea
                    shutil.rmtree(tmp_dir, ignore_errors=True)

            if mse_vals:
                mse_mean = sum(mse_vals) / len(mse_vals)
                psnr_mean = sum(psnr_vals) / len(psnr_vals)
                print(
                    f"[Result] k={k}  mean MSE={mse_mean:.2f}  "
                    f"mean PSNR={psnr_mean:.2f} dB  (samples={len(mse_vals)})"
                )
            else:
                print(f"[Result] k={k}  no valid samples")

    print(f"[Test] Done. Results written to {csv_path}")


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: python3 test_resilience.py image.png [block_count] [trials]")
        sys.exit(1)

    image_path = sys.argv[1]
    if not os.path.isfile(image_path):
        print("Input image not found:", image_path)
        sys.exit(1)

    block_count = None
    trials = 50

    if len(sys.argv) >= 3:
        try:
            block_count = int(sys.argv[2])
        except ValueError:
            print("block_count must be integer")
            sys.exit(1)

    if len(sys.argv) >= 4:
        try:
            trials = int(sys.argv[3])
        except ValueError:
            print("trials must be integer")
            sys.exit(1)

    run_resilience_test(image_path, block_count=block_count, trials=trials)


if __name__ == "__main__":
    main()

