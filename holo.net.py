#!/usr/bin/env python3
import os
import sys
import socket
import struct
import random
import shutil
import time
import argparse
from dataclasses import dataclass, field
from typing import Dict, Optional

import holo  # holo.py must be in the same directory


MAGIC = b"HNET"
VERSION = 1

PKT_META = 0
PKT_DATA = 1

# magic(4s), version(1B), pkt_type(1B),
# transfer_id(4B), total_chunks(4B), chunk_index(4B),
# segment_index(2B), total_segments(2B)
HEADER_STRUCT = struct.Struct("!4sBBIIIHH")

# Defaults (all overridable from CLI)
DEFAULT_TX_MAX_PAYLOAD = 1400     # bytes per UDP datagram (header+data) on TX
DEFAULT_RX_MAX_PAYLOAD = 65507    # max UDP payload to accept on RX
DEFAULT_CHUNK_KB = 32             # holographic chunk size in KB
DEFAULT_LOOPS = 3                 # number of full passes over all chunks
DEFAULT_PORT = 5000               # UDP port
DEFAULT_DELAY = 0.0005            # seconds between datagrams on TX
DEFAULT_IDLE_TIMEOUT = 30.0       # seconds of inactivity on RX before decoding
DEFAULT_BASE_DIR = "."            # where reconstructed files go


# ===================== TX SIDE =====================


def encode_to_holo_dir(input_path: str, chunk_kb: int) -> str:
    """
    Use holo.py to create a fresh <file>.holo directory for this transfer.
    Any previous directory with the same name is removed to avoid mixing chunks.
    """
    mode = holo.detect_mode_from_extension(input_path)
    out_dir = input_path + ".holo"

    if os.path.isdir(out_dir):
        shutil.rmtree(out_dir)

    if mode == "image":
        holo.encode_image_holo_dir(
            input_path,
            out_dir,
            target_chunk_kb=chunk_kb,
        )
    elif mode == "audio":
        holo.encode_audio_holo_dir(
            input_path,
            out_dir,
            target_chunk_kb=chunk_kb,
        )
    else:
        holo.encode_binary_holo_dir(
            input_path,
            out_dir,
            target_chunk_kb=chunk_kb,
        )

    return out_dir


def iter_chunk_files(holo_dir: str):
    for fname in sorted(os.listdir(holo_dir)):
        if fname.startswith("chunk_") and fname.endswith(".holo"):
            yield os.path.join(holo_dir, fname)


def send_file(
    file_path: str,
    host: str,
    port: int,
    chunk_kb: int,
    loops: int,
    max_payload: int,
    delay: float,
):
    if not os.path.isfile(file_path):
        print(f"[tx] file not found: {file_path}")
        sys.exit(1)

    holo_dir = encode_to_holo_dir(file_path, chunk_kb)
    chunk_paths = list(iter_chunk_files(holo_dir))
    if not chunk_paths:
        print(f"[tx] no chunk_*.holo files in {holo_dir}")
        sys.exit(1)

    total_chunks = len(chunk_paths)
    transfer_id = random.randint(1, 2**32 - 1)
    file_name = os.path.basename(file_path)
    name_bytes = file_name.encode("utf-8")

    seg_payload_size = max_payload - HEADER_STRUCT.size
    if seg_payload_size <= 0:
        print("[tx] max_payload too small for the header")
        sys.exit(1)

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    print(f"[tx] sending '{file_name}' to {host}:{port}")
    print(f"[tx] holographic dir: {holo_dir} ({total_chunks} chunks)")
    print(f"[tx] transfer_id={transfer_id}, loops={loops}, chunk_kb={chunk_kb}")
    print(f"[tx] max_payload={max_payload}, delay={delay}s")

    meta_header = HEADER_STRUCT.pack(
        MAGIC,
        VERSION,
        PKT_META,
        transfer_id,
        total_chunks,
        0,
        0,
        0,
    )

    try:
        loops_left = loops
        loop_index = 0
        while loops_left > 0:
            loops_left -= 1
            loop_index += 1

            sock.sendto(meta_header + name_bytes, (host, port))
            print(f"[tx] META sent (loop {loop_index}/{loops})")

            indices = list(range(total_chunks))
            random.shuffle(indices)

            for idx in indices:
                chunk_path = chunk_paths[idx]
                with open(chunk_path, "rb") as f:
                    chunk_data = f.read()

                total_segments = max(
                    1, (len(chunk_data) + seg_payload_size - 1) // seg_payload_size
                )

                for seg_idx in range(total_segments):
                    start = seg_idx * seg_payload_size
                    end = start + seg_payload_size
                    payload = chunk_data[start:end]

                    header = HEADER_STRUCT.pack(
                        MAGIC,
                        VERSION,
                        PKT_DATA,
                        transfer_id,
                        total_chunks,
                        idx,
                        seg_idx,
                        total_segments,
                    )
                    packet = header + payload
                    sock.sendto(packet, (host, port))

                    if delay > 0.0:
                        time.sleep(delay)

            print(f"[tx] loop completed, remaining loops: {loops_left}")

        print("[tx] transmission finished")
    finally:
        sock.close()
        if os.path.isdir(holo_dir):
            try:
                shutil.rmtree(holo_dir)
                print(f"[tx] removed temporary dir {holo_dir}")
            except Exception as e:
                print(f"[tx] warning: could not remove {holo_dir}: {e}")


# ===================== RX SIDE =====================


@dataclass
class ChunkAssembly:
    total_segments: int
    segments: Dict[int, bytes] = field(default_factory=dict)
    complete: bool = False

    def add_segment(self, seg_idx: int, total_segments: int, data: bytes) -> bool:
        if self.complete:
            return False
        if total_segments != self.total_segments:
            return False
        if seg_idx in self.segments:
            return False
        self.segments[seg_idx] = data
        if len(self.segments) == self.total_segments:
            self.complete = True
            return True
        return False

    def build(self) -> bytes:
        if not self.complete:
            raise RuntimeError("Chunk not complete")
        return b"".join(self.segments[i] for i in range(self.total_segments))


@dataclass
class TransferState:
    transfer_id: int
    total_chunks: Optional[int] = None
    file_name: Optional[str] = None
    chunks: Dict[int, ChunkAssembly] = field(default_factory=dict)
    holo_dir: Optional[str] = None


def create_transfer_dir(base_dir: str, transfer_id: int) -> str:
    dirname = f"transfer_{transfer_id}.holo"
    holo_dir = os.path.join(base_dir, dirname)
    if os.path.isdir(holo_dir):
        shutil.rmtree(holo_dir)
    os.makedirs(holo_dir, exist_ok=True)
    return holo_dir


def maybe_rename_dir_for_filename(base_dir: str, transfer: TransferState) -> None:
    if not transfer.file_name or not transfer.holo_dir:
        return

    new_dir = os.path.join(base_dir, transfer.file_name + ".holo")
    if os.path.abspath(new_dir) == os.path.abspath(transfer.holo_dir):
        return

    if os.path.isdir(new_dir):
        shutil.rmtree(new_dir)
    os.rename(transfer.holo_dir, new_dir)
    transfer.holo_dir = new_dir


def decode_transfer(
    base_dir: str,
    transfer: TransferState,
    decode_mode: str,
) -> None:
    if not transfer.holo_dir:
        print("[rx] no holographic directory to decode")
        return

    holo_dir = transfer.holo_dir
    chunk_files = [
        name for name in os.listdir(holo_dir)
        if name.startswith("chunk_") and name.endswith(".holo")
    ]
    if not chunk_files:
        print("[rx] no completed chunks, nothing to decode")
        return

    mode = holo.detect_mode_from_chunk(holo_dir)

    if transfer.file_name:
        out_path = os.path.join(base_dir, transfer.file_name)
    else:
        base_name = os.path.basename(holo_dir.rstrip(os.sep))
        if base_name.endswith(".holo"):
            base_name = base_name[:-5]
        if mode == "image":
            out_path = os.path.join(base_dir, base_name + ".png")
        elif mode == "audio":
            out_path = os.path.join(base_dir, base_name + ".wav")
        else:
            out_path = os.path.join(base_dir, base_name + ".bin")

    complete_chunks = sum(1 for c in transfer.chunks.values() if c.complete)
    total_chunks = transfer.total_chunks

    if total_chunks is not None:
        frac = complete_chunks / float(total_chunks) if total_chunks else 0.0
        print(
            f"[rx] chunks complete: {complete_chunks}/{total_chunks} "
            f"({frac:.3f} fraction)"
        )
        if decode_mode == "strict" and complete_chunks < total_chunks:
            print("[rx] strict mode: not all chunks present, skipping decode")
            return
    else:
        print("[rx] chunks complete: unknown total_chunks")

    success = False
    try:
        if mode == "image":
            holo.decode_image_holo_dir(holo_dir, out_path)
        elif mode == "audio":
            holo.decode_audio_holo_dir(holo_dir, out_path)
        else:
            holo.decode_binary_holo_dir(holo_dir, out_path)

        print(f"[rx] reconstructed file: {out_path}")
        success = True
    finally:
        if success and os.path.isdir(holo_dir):
            try:
                shutil.rmtree(holo_dir)
                print(f"[rx] removed temporary dir {holo_dir}")
            except Exception as e:
                print(f"[rx] warning: could not remove {holo_dir}: {e}")


def receive(
    port: int,
    base_dir: str,
    idle_timeout: float,
    max_payload: int,
    decode_mode: str,
) -> None:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("0.0.0.0", port))
    sock.settimeout(1.0)

    transfer: Optional[TransferState] = None
    last_packet_time: Optional[float] = None

    print(f"[rx] listening on 0.0.0.0:{port} (idle_timeout={idle_timeout}s)")

    try:
        while True:
            now = time.time()
            if last_packet_time is not None and idle_timeout > 0:
                if now - last_packet_time > idle_timeout:
                    print("[rx] idle timeout, stopping receive loop")
                    break

            try:
                data, addr = sock.recvfrom(max_payload)
            except socket.timeout:
                continue

            last_packet_time = time.time()

            if len(data) < HEADER_STRUCT.size:
                continue

            header = data[: HEADER_STRUCT.size]
            payload = data[HEADER_STRUCT.size:]

            (
                magic,
                version,
                pkt_type,
                transfer_id,
                total_chunks,
                chunk_idx,
                seg_idx,
                total_segments,
            ) = HEADER_STRUCT.unpack(header)

            if magic != MAGIC or version != VERSION:
                continue

            if transfer is None or transfer.transfer_id != transfer_id:
                transfer = TransferState(transfer_id=transfer_id, total_chunks=total_chunks)
                transfer.holo_dir = create_transfer_dir(base_dir, transfer_id)
                print(
                    f"[rx] new transfer_id={transfer_id} from {addr}, "
                    f"total_chunks={total_chunks}, dir={transfer.holo_dir}"
                )

            if pkt_type == PKT_META:
                name = payload.decode("utf-8", errors="ignore").strip()
                if name:
                    transfer.file_name = os.path.basename(name)
                if total_chunks:
                    transfer.total_chunks = total_chunks
                maybe_rename_dir_for_filename(base_dir, transfer)
                print(
                    f"[rx] META: file_name='{transfer.file_name}', "
                    f"total_chunks={transfer.total_chunks}, "
                    f"holo_dir={transfer.holo_dir}"
                )
                continue

            if transfer.total_chunks is None and total_chunks:
                transfer.total_chunks = total_chunks

            if total_segments <= 0:
                continue

            if chunk_idx not in transfer.chunks:
                transfer.chunks[chunk_idx] = ChunkAssembly(total_segments=total_segments)
            chunk = transfer.chunks[chunk_idx]

            completed_now = chunk.add_segment(seg_idx, total_segments, payload)
            if completed_now:
                holo_dir = transfer.holo_dir or create_transfer_dir(base_dir, transfer_id)
                fname = os.path.join(holo_dir, f"chunk_{chunk_idx:04d}.holo")
                with open(fname, "wb") as f:
                    f.write(chunk.build())

                complete_chunks = sum(1 for c in transfer.chunks.values() if c.complete)
                tot = transfer.total_chunks or "?"
                print(
                    f"[rx] completed chunk {chunk_idx}, "
                    f"complete={complete_chunks}/{tot}"
                )
    finally:
        sock.close()

    if transfer is None:
        print("[rx] no transfer received")
        return

    decode_transfer(base_dir, transfer, decode_mode)


# ===================== CLI DISPATCH =====================


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Holographic UDP transport for holo.py",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )

    sub = p.add_subparsers(dest="mode", required=True)

    tx = sub.add_parser("tx", help="transmit a file holographically")
    tx.add_argument("file", help="input file (image/audio/binary)")
    tx.add_argument("host", help="destination host (IP or name)")
    tx.add_argument(
        "--port",
        type=int,
        default=DEFAULT_PORT,
        help="destination UDP port",
    )
    tx.add_argument(
        "--chunk-kb",
        type=int,
        default=DEFAULT_CHUNK_KB,
        help="target holographic chunk size in KB",
    )
    tx.add_argument(
        "--loops",
        type=int,
        default=DEFAULT_LOOPS,
        help="number of full passes over all chunks",
    )
    tx.add_argument(
        "--payload",
        type=int,
        default=DEFAULT_TX_MAX_PAYLOAD,
        help="max UDP payload size (bytes, header+data)",
    )
    tx.add_argument(
        "--delay",
        type=float,
        default=DEFAULT_DELAY,
        help="delay between datagrams in seconds",
    )

    rx = sub.add_parser("rx", help="receive and reconstruct")
    rx.add_argument(
        "--port",
        type=int,
        default=DEFAULT_PORT,
        help="UDP port to listen on",
    )
    rx.add_argument(
        "--base-dir",
        default=DEFAULT_BASE_DIR,
        help="directory where reconstructed files are written",
    )
    rx.add_argument(
        "--idle-timeout",
        type=float,
        default=DEFAULT_IDLE_TIMEOUT,
        help="stop after this many seconds without packets (0 = never)",
    )
    rx.add_argument(
        "--payload",
        type=int,
        default=DEFAULT_RX_MAX_PAYLOAD,
        help="max UDP payload to accept (bytes)",
    )
    rx.add_argument(
        "--decode-mode",
        choices=("best", "strict"),
        default="best",
        help="best = always decode with available chunks; strict = decode only if all chunks are present",
    )

    return p


def main():
    parser = build_parser()
    args = parser.parse_args()

    if args.mode == "tx":
        send_file(
            file_path=args.file,
            host=args.host,
            port=args.port,
            chunk_kb=args.chunk_kb,
            loops=args.loops,
            max_payload=args.payload,
            delay=args.delay,
        )
    elif args.mode == "rx":
        receive(
            port=args.port,
            base_dir=args.base_dir,
            idle_timeout=args.idle_timeout,
            max_payload=args.payload,
            decode_mode=args.decode_mode,
        )
    else:
        parser.error("mode must be 'tx' or 'rx'")


if __name__ == "__main__":
    main()

