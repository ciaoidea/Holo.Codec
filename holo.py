#!/usr/bin/env python3
# Holo.Codec – Holographic media codec for extreme connectivity
#
# Copyright (c) 2025 Physiks.net - Alessandro Rizzo
#
# This file is part of Holo.Codec.
# You may redistribute and/or modify it under the terms specified
# in the LICENSE file distributed with this project.

import os
import sys
import glob
import struct
import zlib
from io import BytesIO

import numpy as np
from PIL import Image
import wave

MAGIC_IMG = b"HOCH"
VERSION_IMG = 1

MAGIC_AUD = b"HOAU"
VERSION_AUD = 1

MAGIC_BIN = b"HOBI"
VERSION_BIN = 1


# ===================== IMAGES =====================


def load_image(path: str) -> np.ndarray:
    """Load an image from disk and convert it to RGB uint8."""
    img = Image.open(path).convert("RGB")
    return np.asarray(img, dtype=np.uint8)


def save_image(arr: np.ndarray, path: str) -> None:
    """Save an RGB uint8 array to disk as an image."""
    img = Image.fromarray(arr.astype(np.uint8), "RGB")
    img.save(path)


def stack_images_average(input_paths: list[str], output_path: str) -> None:
    """
    Stack multiple images (same size) by averaging them pixel-wise.

    This simulates a telescope integrating light over time:
    more frames -> deeper, less noisy image.
    """
    imgs = []
    base_shape = None

    for p in input_paths:
        if not os.path.isfile(p):
            print(f"[Holo] Skipping missing image: {p}")
            continue
        arr = load_image(p).astype(np.float32)
        if base_shape is None:
            base_shape = arr.shape
        else:
            if arr.shape != base_shape:
                raise ValueError(
                    f"Inconsistent frame shape: {p} has {arr.shape}, "
                    f"expected {base_shape}"
                )
        imgs.append(arr)

    if not imgs:
        raise ValueError("No valid images to stack")

    stack = np.mean(imgs, axis=0)
    stack = np.clip(stack, 0.0, 255.0).astype(np.uint8)
    save_image(stack, output_path)
    print(f"[Holo] Stacked {len(imgs)} images -> {output_path}")


def encode_image_holo_dir(
    input_path: str,
    out_dir: str,
    block_count: int = 32,
    coarse_max_side: int = 64,
    target_chunk_kb: int | None = None,
) -> None:
    """
    Encode an image into a holographic directory of chunks.

    Each chunk contains a copy of a global thumbnail and a disjoint slice
    of the residual (detail) information.
    """
    img = load_image(input_path)
    h, w, c = img.shape

    max_side = max(h, w)
    scale = min(1.0, float(coarse_max_side) / float(max_side))
    cw = max(1, int(round(w * scale)))
    ch = max(1, int(round(h * scale)))

    img_pil = Image.fromarray(img, "RGB")
    coarse_img = img_pil.resize((cw, ch), Image.BICUBIC)

    buf = BytesIO()
    coarse_img.save(buf, format="PNG")
    coarse_bytes = buf.getvalue()

    coarse_up = coarse_img.resize((w, h), Image.BICUBIC)
    coarse_up_arr = np.asarray(coarse_up, dtype=np.uint8)

    residual = img.astype(np.int16) - coarse_up_arr.astype(np.int16)
    residual_flat = residual.reshape(-1)

    if target_chunk_kb is not None:
        residual_bytes_total = residual_flat.size * 2  # int16 -> 2 bytes
        try:
            target_bytes = max(1, int(target_chunk_kb) * 1024)
        except ValueError:
            target_bytes = None

        if target_bytes is not None:
            header_overhead = 64  # header + margin
            overhead_approx = len(coarse_bytes) + header_overhead
            if target_bytes <= overhead_approx + 1:
                block_count = 1
            else:
                useful_per_chunk = target_bytes - overhead_approx
                block_count = int(np.ceil(residual_bytes_total / useful_per_chunk))
                block_count = max(1, min(block_count, residual_flat.size))

    os.makedirs(out_dir, exist_ok=True)

    for block_id in range(block_count):
        vals = residual_flat[block_id::block_count]
        vals_bytes = vals.astype("<i2").tobytes()
        comp_vals = zlib.compress(vals_bytes, level=9)

        header = bytearray()
        header += MAGIC_IMG
        header += struct.pack("B", VERSION_IMG)
        header += struct.pack(">I", h)
        header += struct.pack(">I", w)
        header += struct.pack("B", c)
        header += struct.pack(">I", block_count)
        header += struct.pack(">I", block_id)
        header += struct.pack(">I", len(coarse_bytes))
        header += struct.pack(">I", len(comp_vals))

        data = bytes(header) + coarse_bytes + comp_vals
        fname = os.path.join(out_dir, f"chunk_{block_id:04d}.holo")
        with open(fname, "wb") as f:
            f.write(data)


def decode_image_holo_dir(
    in_dir: str,
    output_path: str,
    max_chunks: int | None = None,
) -> None:
    """
    Decode an image from a holographic directory of chunks.

    If max_chunks is provided, only the first max_chunks chunks are used,
    producing a more degraded but still globally coherent reconstruction.
    """
    chunk_files = sorted(glob.glob(os.path.join(in_dir, "chunk_*.holo")))
    if not chunk_files:
        raise FileNotFoundError(f"No chunk_*.holo found in {in_dir}")

    if max_chunks is not None:
        chunk_files = chunk_files[:max_chunks]

    first = True
    h = w = c = block_count = None
    coarse_up_arr = None
    residual_flat = None

    for path in chunk_files:
        with open(path, "rb") as f:
            data = f.read()

        off = 0
        magic = data[off: off + 4]
        off += 4
        if magic != MAGIC_IMG:
            continue
        version = data[off]
        off += 1
        if version != VERSION_IMG:
            raise ValueError(f"Unsupported image chunk version in {path}")

        h_i = struct.unpack(">I", data[off: off + 4])[0]
        off += 4
        w_i = struct.unpack(">I", data[off: off + 4])[0]
        off += 4
        c_i = data[off]
        off += 1
        B_i = struct.unpack(">I", data[off: off + 4])[0]
        off += 4
        block_id = struct.unpack(">I", data[off: off + 4])[0]
        off += 4
        coarse_len = struct.unpack(">I", data[off: off + 4])[0]
        off += 4
        resid_len = struct.unpack(">I", data[off: off + 4])[0]
        off += 4

        coarse_bytes = data[off: off + coarse_len]
        off += coarse_len
        resid_comp = data[off: off + resid_len]

        if first:
            h, w, c = h_i, w_i, c_i
            block_count = B_i
            coarse_img = Image.open(BytesIO(coarse_bytes)).convert("RGB")
            coarse_up = coarse_img.resize((w, h), Image.BICUBIC)
            coarse_up_arr = np.asarray(coarse_up, dtype=np.int16)
            residual_flat = np.zeros(h * w * c, dtype=np.int16)
            first = False
        else:
            if (h_i, w_i, c_i, B_i) != (h, w, c, block_count):
                raise ValueError(f"Inconsistent image chunk: {path}")

        vals_bytes = zlib.decompress(resid_comp)
        vals = np.frombuffer(vals_bytes, dtype="<i2")
        residual_flat[block_id::block_count][: len(vals)] = vals

    residual = residual_flat.reshape(h, w, c)
    recon_int = coarse_up_arr + residual
    recon_int = np.clip(recon_int, 0, 255)
    recon = recon_int.astype(np.uint8)
    save_image(recon, output_path)


# ===================== WAV AUDIO =====================


def _read_wav_int16(path: str) -> tuple[np.ndarray, int, int]:
    """
    Read a WAV file and return (samples_int16, sample_rate, channels).

    Supports PCM 16-bit or PCM 24-bit (the latter is down-converted to 16-bit).
    """
    with wave.open(path, "rb") as wf:
        n_channels = wf.getnchannels()
        sampwidth = wf.getsampwidth()
        framerate = wf.getframerate()
        n_frames = wf.getnframes()
        raw = wf.readframes(n_frames)

    total_samples = n_frames * n_channels

    if sampwidth == 2:
        data = np.frombuffer(raw, dtype="<i2").astype(np.int16)
    elif sampwidth == 3:
        b = np.frombuffer(raw, dtype=np.uint8)
        if b.size != total_samples * 3:
            raise ValueError("Inconsistent 24-bit WAV data size")
        b = b.reshape(-1, 3)
        vals = (
            b[:, 0].astype(np.int32)
            | (b[:, 1].astype(np.int32) << 8)
            | (b[:, 2].astype(np.int32) << 16)
        )
        mask = 1 << 23
        vals = (vals ^ mask) - mask
        data = (vals >> 8).astype(np.int16)
    else:
        raise ValueError(
            f"Only PCM 16-bit or 24-bit WAV is supported, got sampwidth={sampwidth}"
        )

    data = data.reshape(-1, n_channels)
    return data, framerate, n_channels


def _write_wav_int16(path: str, data: np.ndarray, framerate: int) -> None:
    """Write an int16 PCM array to a WAV file."""
    data = data.astype(np.int16)
    n_frames, n_channels = data.shape
    with wave.open(path, "wb") as wf:
        wf.setnchannels(n_channels)
        wf.setsampwidth(2)
        wf.setframerate(framerate)
        wf.writeframes(data.astype("<i2").tobytes())


def encode_audio_holo_dir(
    input_wav: str,
    out_dir: str,
    block_count: int = 16,
    coarse_max_frames: int = 2048,
    target_chunk_kb: int | None = None,
) -> None:
    """
    Encode a WAV file into a holographic directory of chunks.

    Each chunk carries a coarse downsampled version of the track and a slice
    of the residual information.
    """
    audio, sr, ch = _read_wav_int16(input_wav)
    n_frames = audio.shape[0]

    coarse_len = min(coarse_max_frames, n_frames)
    if coarse_len < 2:
        coarse_len = 2

    idx = np.linspace(0, n_frames - 1, coarse_len, dtype=np.int64)
    coarse = audio[idx]

    t = np.linspace(0, coarse_len - 1, n_frames, dtype=np.float64)
    k0 = np.floor(t).astype(np.int64)
    k1 = np.clip(k0 + 1, 0, coarse_len - 1)
    alpha = (t - k0).astype(np.float64)
    coarse_f = coarse.astype(np.float64)
    coarse_up = (1.0 - alpha)[:, None] * coarse_f[k0] + alpha[:, None] * coarse_f[k1]
    coarse_up = np.round(coarse_up).astype(np.int16)

    residual = (audio.astype(np.int32) - coarse_up.astype(np.int32)).astype(np.int16)
    residual_flat = residual.reshape(-1)

    coarse_bytes = coarse.astype("<i2").tobytes()
    coarse_comp = zlib.compress(coarse_bytes, level=9)

    if target_chunk_kb is not None:
        residual_bytes_total = residual_flat.size * 2  # int16
        try:
            target_bytes = max(1, int(target_chunk_kb) * 1024)
        except ValueError:
            target_bytes = None

        if target_bytes is not None:
            header_overhead = 64
            overhead_approx = len(coarse_comp) + header_overhead
            if target_bytes <= overhead_approx + 1:
                block_count = 1
            else:
                useful_per_chunk = target_bytes - overhead_approx
                block_count = int(np.ceil(residual_bytes_total / useful_per_chunk))
                block_count = max(1, min(block_count, residual_flat.size))

    os.makedirs(out_dir, exist_ok=True)

    for block_id in range(block_count):
        vals = residual_flat[block_id::block_count]
        vals_bytes = vals.astype("<i2").tobytes()
        resid_comp = zlib.compress(vals_bytes, level=9)

        header = bytearray()
        header += MAGIC_AUD
        header += struct.pack("B", VERSION_AUD)
        header += struct.pack("B", ch)
        header += struct.pack("B", 2)  # internal sampwidth
        header += struct.pack("B", 0)  # padding
        header += struct.pack(">I", sr)
        header += struct.pack(">I", n_frames)
        header += struct.pack(">I", block_count)
        header += struct.pack(">I", block_id)
        header += struct.pack(">I", coarse_len)
        header += struct.pack(">I", len(coarse_comp))
        header += struct.pack(">I", len(resid_comp))

        data = bytes(header) + coarse_comp + resid_comp
        fname = os.path.join(out_dir, f"chunk_{block_id:04d}.holo")
        with open(fname, "wb") as f:
            f.write(data)


def decode_audio_holo_dir(
    in_dir: str,
    output_wav: str,
    max_chunks: int | None = None,
) -> None:
    """
    Decode a WAV file from a holographic directory of chunks.

    If max_chunks is provided, only that many chunks are used.
    """
    chunk_files = sorted(glob.glob(os.path.join(in_dir, "chunk_*.holo")))
    if not chunk_files:
        raise FileNotFoundError(f"No chunk_*.holo found in {in_dir}")

    if max_chunks is not None:
        chunk_files = chunk_files[:max_chunks]

    first = True
    sr = ch = n_frames = block_count = coarse_len = None
    coarse_up = None
    residual_flat = None

    for path in chunk_files:
        with open(path, "rb") as f:
            data = f.read()

        off = 0
        magic = data[off: off + 4]
        off += 4
        if magic != MAGIC_AUD:
            continue
        version = data[off]
        off += 1
        if version != VERSION_AUD:
            raise ValueError(f"Unsupported audio chunk version in {path}")
        ch_i = data[off]
        off += 1
        sampwidth = data[off]
        off += 1
        _pad = data[off]
        off += 1
        sr_i = struct.unpack(">I", data[off: off + 4])[0]
        off += 4
        n_frames_i = struct.unpack(">I", data[off: off + 4])[0]
        off += 4
        block_count_i = struct.unpack(">I", data[off: off + 4])[0]
        off += 4
        block_id = struct.unpack(">I", data[off: off + 4])[0]
        off += 4
        coarse_len_i = struct.unpack(">I", data[off: off + 4])[0]
        off += 4
        coarse_size = struct.unpack(">I", data[off: off + 4])[0]
        off += 4
        resid_size = struct.unpack(">I", data[off: off + 4])[0]
        off += 4

        coarse_comp = data[off: off + coarse_size]
        off += coarse_size
        resid_comp = data[off: off + resid_size]

        if first:
            if sampwidth != 2:
                raise ValueError(
                    "Audio chunk has unsupported sampwidth (expected 2 bytes)"
                )
            ch = ch_i
            sr = sr_i
            n_frames = n_frames_i
            block_count = block_count_i
            coarse_len = coarse_len_i

            coarse_bytes = zlib.decompress(coarse_comp)
            coarse = np.frombuffer(coarse_bytes, dtype="<i2").astype(np.int16)
            coarse = coarse.reshape(coarse_len, ch)

            t = np.linspace(0, coarse_len - 1, n_frames, dtype=np.float64)
            k0 = np.floor(t).astype(np.int64)
            k1 = np.clip(k0 + 1, 0, coarse_len - 1)
            alpha = (t - k0).astype(np.float64)
            coarse_f = coarse.astype(np.float64)
            coarse_up = (
                (1.0 - alpha)[:, None] * coarse_f[k0]
                + alpha[:, None] * coarse_f[k1]
            )
            coarse_up = np.round(coarse_up).astype(np.int16)

            residual_flat = np.zeros(n_frames * ch, dtype=np.int16)
            first = False
        else:
            if (ch_i, sr_i, n_frames_i, block_count_i, coarse_len_i) != (
                ch,
                sr,
                n_frames,
                block_count,
                coarse_len,
            ):
                raise ValueError(f"Inconsistent audio chunk: {path}")

        vals_bytes = zlib.decompress(resid_comp)
        vals = np.frombuffer(vals_bytes, dtype="<i2").astype(np.int16)

        positions = np.arange(
            block_id,
            block_id + len(vals) * block_count,
            block_count,
            dtype=np.int64,
        )
        positions = positions[positions < residual_flat.size]
        residual_flat[positions] = vals[: len(positions)]

    residual = residual_flat.reshape(n_frames, ch)
    recon_int = coarse_up.astype(np.int32) + residual.astype(np.int32)
    recon_int = np.clip(recon_int, -32768, 32767).astype(np.int16)
    _write_wav_int16(output_wav, recon_int, sr)


# ===================== GENERIC BINARY =====================


def encode_binary_holo_dir(
    input_path: str,
    out_dir: str,
    block_count: int = 32,
    coarse_len: int = 1024,
    target_chunk_kb: int | None = None,
) -> None:
    """
    Encode a generic binary file into a holographic directory.

    For non-perceptual formats this only provides robustness when *all* chunks
    are present; deleting chunks will typically corrupt the format.
    """
    with open(input_path, "rb") as f:
        data = f.read()

    L = len(data)
    if L == 0:
        raise ValueError("Empty file, nothing to encode")

    coarse_len = min(coarse_len, L)
    coarse = data[:coarse_len]
    rest = data[coarse_len:]
    rest_arr = np.frombuffer(rest, dtype=np.uint8)

    coarse_comp = zlib.compress(coarse, level=9)

    if target_chunk_kb is not None:
        residual_bytes_total = rest_arr.size
        try:
            target_bytes = max(1, int(target_chunk_kb) * 1024)
        except ValueError:
            target_bytes = None

        if target_bytes is not None:
            header_overhead = 64
            overhead_approx = len(coarse_comp) + header_overhead
            if target_bytes <= overhead_approx + 1:
                block_count = 1
            else:
                useful_per_chunk = target_bytes - overhead_approx
                block_count = int(np.ceil(residual_bytes_total / useful_per_chunk))
                max_blocks = max(1, residual_bytes_total)
                block_count = max(1, min(block_count, max_blocks))

    os.makedirs(out_dir, exist_ok=True)

    for block_id in range(block_count):
        vals = rest_arr[block_id::block_count]
        vals_bytes = vals.tobytes()
        comp_vals = zlib.compress(vals_bytes, level=9)

        header = bytearray()
        header += MAGIC_BIN
        header += struct.pack("B", VERSION_BIN)
        header += struct.pack(">Q", L)
        header += struct.pack(">I", block_count)
        header += struct.pack(">I", block_id)
        header += struct.pack(">I", coarse_len)
        header += struct.pack(">I", len(coarse_comp))
        header += struct.pack(">I", len(comp_vals))

        data_out = bytes(header) + coarse_comp + comp_vals
        fname = os.path.join(out_dir, f"chunk_{block_id:04d}.holo")
        with open(fname, "wb") as f:
            f.write(data_out)


def decode_binary_holo_dir(
    in_dir: str,
    output_path: str,
    max_chunks: int | None = None,
) -> None:
    """
    Decode a generic binary file from a holographic directory.

    This expects that all chunks are available for a valid reconstruction.
    """
    chunk_files = sorted(glob.glob(os.path.join(in_dir, "chunk_*.holo")))
    if not chunk_files:
        raise FileNotFoundError(f"No chunk_*.holo found in {in_dir}")

    if max_chunks is not None:
        chunk_files = chunk_files[:max_chunks]

    first = True
    L = block_count = coarse_len = None
    coarse = None
    rest_arr = None

    for path in chunk_files:
        with open(path, "rb") as f:
            data = f.read()

        off = 0
        magic = data[off: off + 4]
        off += 4
        if magic != MAGIC_BIN:
            continue
        version = data[off]
        off += 1
        if version != VERSION_BIN:
            raise ValueError(f"Unsupported binary chunk version in {path}")

        L_i = struct.unpack(">Q", data[off: off + 8])[0]
        off += 8
        B_i = struct.unpack(">I", data[off: off + 4])[0]
        off += 4
        block_id = struct.unpack(">I", data[off: off + 4])[0]
        off += 4
        coarse_len_i = struct.unpack(">I", data[off: off + 4])[0]
        off += 4
        coarse_size = struct.unpack(">I", data[off: off + 4])[0]
        off += 4
        resid_size = struct.unpack(">I", data[off: off + 4])[0]
        off += 4

        coarse_comp = data[off: off + coarse_size]
        off += coarse_size
        resid_comp = data[off: off + resid_size]

        if first:
            L = L_i
            block_count = B_i
            coarse_len = coarse_len_i
            coarse = zlib.decompress(coarse_comp)
            rest_len = L - coarse_len
            rest_arr = np.zeros(rest_len, dtype=np.uint8)
            first = False
        else:
            if (L_i, B_i, coarse_len_i) != (L, block_count, coarse_len):
                raise ValueError(f"Inconsistent binary chunk in {path}")

        vals_bytes = zlib.decompress(resid_comp)
        vals = np.frombuffer(vals_bytes, dtype=np.uint8)
        rest_arr[block_id::block_count][: len(vals)] = vals

    out = bytearray(L)
    out[:coarse_len] = coarse[:coarse_len]
    out[coarse_len:] = rest_arr.tobytes()

    with open(output_path, "wb") as f:
        f.write(out)


# ===================== AUTOMATIC DISPATCH =====================


def detect_mode_from_extension(path: str) -> str:
    """Infer mode (image/audio/binary) from file extension."""
    ext = os.path.splitext(path)[1].lower()
    if ext in (".png", ".jpg", ".jpeg", ".bmp", ".gif", ".tif", ".tiff"):
        return "image"
    if ext == ".wav":
        return "audio"
    return "binary"


def detect_mode_from_chunk(in_dir: str) -> str:
    """Infer mode from the magic bytes of the first chunk in a .holo directory."""
    chunk_files = sorted(glob.glob(os.path.join(in_dir, "chunk_*.holo")))
    if not chunk_files:
        raise FileNotFoundError(f"No chunk_*.holo found in {in_dir}")
    with open(chunk_files[0], "rb") as f:
        magic = f.read(4)
    if magic == MAGIC_IMG:
        return "image"
    if magic == MAGIC_AUD:
        return "audio"
    if magic == MAGIC_BIN:
        return "binary"
    raise ValueError("Unknown chunk type (unexpected magic bytes)")


def main() -> None:
    # Special mode: stack multiple PNGs into one image, then encode holographically
    if len(sys.argv) >= 4 and sys.argv[1] == "--stack":
        try:
            chunk_kb = int(sys.argv[2])
        except ValueError:
            print("Usage: python3 holo.py --stack <chunk_kb> <frame1.png> [frame2.png ...]")
            sys.exit(1)

        frame_paths = sys.argv[3:]
        if not frame_paths:
            print("Usage: python3 holo.py --stack <chunk_kb> <frame1.png> [frame2.png ...]")
            sys.exit(1)

        first = frame_paths[0]
        base, _ = os.path.splitext(first)
        stacked_png = base + "_stack.png"
        out_dir = stacked_png + ".holo"

        print(f"[Holo] Stacking frames into {stacked_png}")
        stack_images_average(frame_paths, stacked_png)

        print(f"[Holo] Encoding stacked image into {out_dir}")
        encode_image_holo_dir(
            input_path=stacked_png,
            out_dir=out_dir,
            target_chunk_kb=chunk_kb,
        )
        sys.exit(0)

    if len(sys.argv) not in (2, 3):
        print("Simple usage:")
        print("  python3 holo.py original_file [chunk_kb]      # creates original_file.holo (directory)")
        print("  python3 holo.py original_file.holo           # reconstructs original_file")
        print("  python3 holo.py --stack chunk_kb frame1.png [frame2.png ...]  # stack+encode")
        sys.exit(1)

    target = sys.argv[1]
    chunk_kb: int | None = None

    if len(sys.argv) == 3:
        try:
            chunk_kb = int(sys.argv[2])
        except ValueError:
            print("Invalid chunk_kb value, must be an integer (KB).")
            sys.exit(1)

    if os.path.isfile(target):
        # Encode
        input_path = target
        out_dir = input_path + ".holo"
        mode = detect_mode_from_extension(input_path)

        if mode == "image":
            encode_image_holo_dir(input_path, out_dir, target_chunk_kb=chunk_kb)
        elif mode == "audio":
            encode_audio_holo_dir(input_path, out_dir, target_chunk_kb=chunk_kb)
        else:
            encode_binary_holo_dir(input_path, out_dir, target_chunk_kb=chunk_kb)

    elif os.path.isdir(target):
        # Decode
        in_dir = target.rstrip("/")
        if in_dir.endswith(".holo"):
            output_path = in_dir[:-5]  # strip ".holo" and restore original name
        else:
            output_path = in_dir + "_dec"  # fallback

        mode = detect_mode_from_chunk(in_dir)

        if mode == "image":
            decode_image_holo_dir(in_dir, output_path)
        elif mode == "audio":
            decode_audio_holo_dir(in_dir, output_path)
        else:
            decode_binary_holo_dir(in_dir, output_path)
    else:
        print("Path not found:", target)
        sys.exit(1)


if __name__ == "__main__":
    main()
