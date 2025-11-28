# Holo.Codec
# Holographic Media Codec for Extreme Networks
## Robust holographic audio-vision that never breaks.

<img width="1280" height="640" alt="Holo Codec" src="https://github.com/user-attachments/assets/0bbbe6a5-14bb-498c-ac55-62f2dfed5641" />

````markdown
# Holo.Codec – Holographic media codec for extreme connectivity

Holo.Codec is a small experimental codec and transport layer designed for situations where the network is unreliable, extremely slow, or both.  
Instead of compressing a file into one monolithic bitstream that breaks completely if you lose packets, Holo.Codec turns media into many small “holographic” chunks. Each chunk contains a global low‑resolution view of the whole content plus a different slice of the missing detail.

If you receive all the chunks you get a reconstruction that matches the original.  
If you only receive a fraction, you still get a coherent but degraded version: a slightly blurred image instead of a corrupt file, a softer audio track instead of silence. :contentReference[oaicite:0]{index=0}  

This repository is built around two main components:

- `holo.py` – the core holographic codec for images, audio, and generic binaries  
- `holo.net.py` – a UDP‑based transport that pushes holographic chunks across extreme networks, with parameters tuned from LAN up to deep‑space‑style links

---

## Core idea

The codec is built on a very simple concept applied carefully:

1. Rebuild a low‑resolution or low‑rate “coarse” representation of the whole signal.
2. Compute the residual (original minus coarse).
3. Distribute the residual across many chunks using a golden‑ratio‑based permutation so that each chunk carries a fair sample of detail spread over the whole file.
4. Store the coarse representation inside each chunk together with one residual slice.

On decoding, the coarse representation is reconstructed or upsampled once, then all residual slices that happen to be available are accumulated back into the right positions. Any missing slices simply mean that part of the residual is zero, so the decoder falls back to the coarse version in those places.

The result is that every chunk “knows” something about the entire signal. Losing chunks lowers resolution or SNR but does not localize damage to specific regions.

---

## Holographic image codec

Images are handled in RGB uint8 using Pillow and NumPy. :contentReference[oaicite:1]{index=1}  

Encoding (`encode_image_holo_dir`):

- The image is loaded and converted to RGB.  
- A global thumbnail is created by resizing the full image down to a small side (for example 64 pixels) with bicubic interpolation.  
- The thumbnail is upscaled back to the original size to form a coarse approximation of the image.  
- The residual is computed as `residual = original - coarse_up`, stored as int16 to keep the sign.  
- The residual is flattened into a one‑dimensional array of length `N = h * w * c`.  
- A golden permutation is built: a single‑cycle permutation of `0..N-1` obtained using a step close to `(phi - 1) * N`, adjusted to be coprime with `N` (where `phi` is the golden ratio).  
- The residual is split across `B` blocks by taking indices `perm[block_id :: B]`, so each block gets a well‑spread sample of the residual.  
- For each block, the residual slice is zlib‑compressed and packaged together with the thumbnail in a small binary file `chunk_XXXX.holo` that carries header, coarse PNG bytes, and compressed residual.

Decoding (`decode_image_holo_dir`):

- All available `chunk_*.holo` files in the directory are scanned.  
- From the first valid chunk, the decoder extracts dimensions, number of channels, number of blocks, version, and the thumbnail.  
- The thumbnail is upscaled to the original resolution to form the coarse image.  
- An array `residual_flat` is allocated and filled with zeros.  
- For each chunk, the residual slice is decompressed. Its positions in `residual_flat` are recovered using the same golden permutation and block index; values are written into their slots.  
- Once all chunks are processed, `residual_flat` is reshaped to `(h, w, c)` and summed with the coarse image, with clipping to `[0, 255]`.  

If you have all chunks, the reconstruction closely matches the original.  
If you have only some chunks, you still get a globally coherent image: the coarse structure comes from the thumbnail, the available chunks sharpen it wherever residual is known.

---

## Holographic audio codec

The audio side uses 16‑ or 24‑bit PCM WAV as input. 24‑bit signals are down‑converted to 16‑bit internally for a simpler residual representation. :contentReference[oaicite:2]{index=2}  

Encoding (`encode_audio_holo_dir`):

- The WAV is read into an `int16` array of shape `(frames, channels)`.  
- A coarse track is built by selecting a reduced number of frames (for example 2048) and then linearly interpolating them back to full length.  
- The residual is computed as `audio - coarse_up` in 16‑bit space.  
- The coarse track is compressed with zlib and stored once per chunk.  
- The residual is flattened and split across blocks with the same golden permutation strategy as images, then each residual slice is compressed and written to `chunk_XXXX.holo` with an audio header.

Decoding (`decode_audio_holo_dir`):

- All audio chunks are scanned.  
- From the first valid chunk the decoder recovers sample rate, channels, total frames, and coarse length, then rebuilds the coarse track by decompressing and linearly interpolating.  
- A residual array is allocated and filled with zeros.  
- For each chunk, the residual slice is decompressed and written into its positions according to version and permutation.  
- Residual and coarse are summed, clipped to the legal `int16` range, and written back as a WAV file.

With all chunks, the reconstructed audio is very close to the original PCM. With fewer chunks you effectively hear something closer to the coarse approximation plus a subset of the missing detail; the result is softer but globally meaningful.

---

## Holographic binary codec

Binary files are treated differently, since they do not have a perceptual notion of “slightly degraded but still useful”. :contentReference[oaicite:3]{index=3}  

Encoding (`encode_binary_holo_dir`):

- The file is split into a coarse prefix and the remaining bytes.  
- The coarse prefix is compressed once and stored in every chunk.  
- The remaining bytes are mapped into a NumPy `uint8` array, and a golden permutation is applied to distribute bytes across blocks.  
- Each block gets a slice of the permuted bytes, which is zlib‑compressed and stored as residual.

Decoding (`decode_binary_holo_dir`):

- All binary chunks are scanned; metadata and layout are verified.  
- The coarse prefix is reconstructed from the compressed copy.  
- The permuted residual is reassembled from any subset of available chunks.  
- The original byte sequence is reconstructed by inverting the permutation and concatenating coarse and residual.

Binary formats usually require all bytes to be correct, so partial chunk sets are not expected to produce meaningful files. The holographic layout still gives robustness against isolated bit errors and lets you detect inconsistencies, but graceful degradation is primarily meaningful for images and audio.

---

## Stacking images

Holo.Codec also supports stacking multiple images into a deeper exposure before encoding. :contentReference[oaicite:4]{index=4}  

The helper `stack_images_average` takes several frames with the same resolution, averages them pixel‑wise into a single image, and saves it. The resulting “stacked” frame has lower noise and higher effective dynamic range, similar to how a telescope integrates light over time. You can then encode this stacked image holographically, so every chunk carries a view of the deep combined frame.

There is also a `--stack` mode in `holo.py` that automates this process for PNG input.

Example:

```bash
python3 holo.py --stack 32 frame1.png frame2.png frame3.png
````

This stacks the PNGs into `frame1_stack.png` and then encodes that image into `frame1_stack.png.holo` with a target chunk size of 32 KB.

---

## Stand‑alone codec usage (`holo.py`)

The stand‑alone codec script supports a simple dual behaviour: encode when given a regular file, decode when given a `.holo` directory. 

Basic examples:

```bash
# encode an image, audio or binary into a .holo directory
python3 holo.py original_file         # default chunk sizing
python3 holo.py original_file 32      # target ~32 KB per chunk

# decode from a .holo directory back to the original file
python3 holo.py original_file.holo

# stack multiple PNG frames then encode holographically
python3 holo.py --stack 32 frame1.png frame2.png frame3.png
```

The codec infers the mode (image, audio, binary) either from the file extension or from the magic bytes stored inside the holographic chunks.

---

## HoloNet: holographic UDP transport (`holo.net.py`)

While `holo.py` works on local files and directories, `holo.net.py` adds a simple network layer that sends and receives holographic chunks over UDP. The network layer never touches the codec math: it delegates all encoding and decoding to `holo.py` and focuses solely on chunk transport.

The basic design is as follows.

On transmit (“tx” mode):

* The input file is encoded into `<file>.holo` using `holo.py`.
* Each `chunk_XXXX.holo` file is treated as an opaque payload.
* A custom HNET header (magic, version, packet type, transfer id, total chunk count, chunk index, segment index, segment count) is prepended.
* The chunk data is sliced into datagrams small enough to fit the configured UDP payload size.
* Each datagram is sent via `socket(AF_INET, SOCK_DGRAM)` to the chosen host and port.
* At the beginning of each loop over chunks, a META packet is sent containing the file name and total chunk count. This allows receivers that start late to discover the name and layout.
* The local `<file>.holo` directory is treated as temporary and removed when the transmission finishes.

On receive (“rx” mode):

* UDP packets are read from the configured port, subject to a maximum packet size and an idle timeout.
* META packets create or update a `TransferState` structure with transfer id, total chunk count, file name, and holographic directory. A temporary directory `transfer_<id>.holo` is created at first, then renamed to `<filename>.holo` when the real name is known.
* DATA packets are assembled into complete chunk files using the segment indices stored in the HNET header.
* As chunks are completed, they are written to the holographic directory using the same `chunk_XXXX.holo` naming convention as `holo.py`.
* Once the receiver decides to stop (for example because of idle timeout), it asks `holo.py` to decode the holographic directory using all available chunks, either in best‑effort mode (always decode with whatever is present) or in strict mode (only decode when all chunks are present).
* After a successful decode, the temporary `.holo` directory is removed and only the reconstructed file remains.

Because every chunk contains a thumbnail or coarse version plus a different slice of residual, the network layer remains agnostic to the type of media. Whatever fraction of chunks survives the network path is enough for some level of reconstruction.

---

## HoloNet command‑line interface

The network script is built as a small command‑line tool with two sub‑commands: `tx` for transmit and `rx` for receive.

Transmit example:

```bash
python3 holo.net.py tx image.png 192.168.1.50 \
    --port 5000 \
    --chunk-kb 32 \
    --loops 5 \
    --payload 1200 \
    --delay 0.002
```

Receive example:

```bash
python3 holo.net.py rx \
    --port 5000 \
    --base-dir . \
    --idle-timeout 60 \
    --payload 65507 \
    --decode-mode best
```

Parameters are there so you can adapt to very different environments.

On a clean LAN you might use larger payloads (around 1400 bytes), fewer loops, and a very small delay.
On a noisy radio or deep‑space‑style link you can shrink payload size to match the physical MTU, increase the number of loops to add redundancy, and space packets out with a larger delay so that the physical modem or TNC is not overwhelmed.

The receiver’s idle timeout controls how long it keeps listening after the last packet before attempting reconstruction. In best‑effort mode it will always try to decode with whatever chunks are present and report the fraction of chunks used. In strict mode it will only decode when the number of completed chunks matches the advertised total.

---

## Adapting to extreme networks

The codec and HoloNet transport are deliberately minimal: they rely on the holographic layout rather than heavy transport‑layer machinery. That makes them well suited as an application layer on top of very different network substrates:

classical IP networks over Ethernet or Wi‑Fi,
IP carried over AX.25 packet radio links,
or simulated deep‑space channels where loss, latency, and bit rate are all extreme.

In all these cases the approach is to treat whatever comes from below as a best‑effort datagram channel. HoloNet does not demand that every packet arrives. Instead it exploits the golden permutation and the coarse‑plus‑residual structure to get the highest perceptual quality it can from the bits that survive.

The codec itself remains the same; only the HoloNet parameters change as you move from a local lab network to an “interstellar” one.

---

## Dependencies and license

The core codec requires Python 3 and a few standard scientific and imaging libraries:

NumPy
Pillow
The standard `wave` module for PCM audio I/O

The network layer relies only on the Python standard library (`socket`, `struct`, etc.). If you build a GUI around it, you may want an additional toolkit such as PyQt, but the codec itself is independent from any GUI framework.

The project header in `holo.py` references a LICENSE file. Redistribution and modification are governed by the terms described there. 

If you use this codec for experiments on emergency or deep‑space communication, treat it as a research tool rather than a formally verified system: it is designed to explore the trade‑off between redundancy, graceful degradation, and perceptual quality per bit, not to replace proven mission‑critical telemetry stacks.

