# Holo.Codec v1.0
# Holographic Media Codec for Extreme Networks

<img width="1280" height="640" alt="Holo Codec" src="https://github.com/user-attachments/assets/0bbbe6a5-14bb-498c-ac55-62f2dfed5641" />


Holo.Codec v1.0 is an experimental **holographic codec for images and audio** designed for
environments where connectivity is ultra–weak, intermittent, or one–way:

- deep‑space missions and planetary rovers  
- remote exploration (caves, polar regions, underwater)  
- disaster and emergency networks with high packet loss  

Any subset of the transmitted chunks reconstructs a **usable** version of the content.  
More chunks ⇒ more detail. Losing chunks never means “no image” or “no audio”, only
a smooth, graceful degradation in quality.

---

## Core idea

Traditional formats (PNG, JPEG, WAV) are “all‑or‑nothing”: if the right bytes are
missing, the file becomes unusable.

Holo.Codec restructures the content into a set of *holographic chunks*:

- a **coarse representation** of the entire signal (thumbnail for images,
  heavily downsampled track for audio)  
- plus **disjoint residual fragments** that refine local detail

Each chunk carries the same coarse view of the whole scene and a different subset of
residuals. On the receiver:

- with one chunk: you already see/hear the **entire** scene, at low fidelity  
- as more chunks arrive: residuals fill in, and the reconstruction converges
  towards the original  
- with all chunks: the reconstruction is (up to container details) essentially
  identical to the source

There is no single “critical” chunk. Every packet adds value; no packet is mandatory.

---

## Why it matters

Holo.Codec v1.0 is not a general‑purpose archival format. It shines where the dominant
constraint is **link quality**, not storage:

- long‑range or deep‑space links with very low SNR and limited visibility windows  
- one‑way broadcasts or beacons where acknowledgements and re‑transmissions are
  expensive or impossible  
- ad‑hoc or emergency networks where packet loss is high and unpredictable

Instead of “perfect or nothing”, Holo.Codec guarantees “**something useful, always**”:

- early chunks give operators situational awareness (terrain, obstacles, context)  
- additional chunks refine detail when time and link budget allow  
- if the link dies early, the ground still has images/audio that are scientifically
  and operationally useful, not corrupt files

Holo.Codec is meant to complement, not replace, classical channel codes (LDPC, turbo,
fountain codes, etc.): those keep individual chunks intact; Holo.Codec decides how
content is *distributed* across chunks so that any subset is meaningful.

Because the output is a set of numbered holographic chunks rather than a single
linear file, the transmission strategy can exploit **time, frequency and path
diversity** very naturally:

- chunks can be spread across multiple frequency bands or physical links (for example,
  different space‑ground paths); any subset of received chunks still reconstructs
  a valid image or audio track  
- chunks can be transmitted in cyclic schedules over time, so that receivers can
  attach to the stream at any point, immediately reconstruct a coarse version,
  and progressively improve quality as more unique chunk IDs are collected  
- chunks can be combined with erasure/FEC schemes at the transport level: channel
  coding keeps individual chunks correct, while the holographic layout ensures that
  **every** successfully received chunk contributes useful information, not just
  headers or fragile file structure

In other words, transport can freely replay, replicate or route chunks over
multiple channels and time windows; Holo.Codec guarantees that whatever survives
on the receiver side always forms the best possible approximation of the original
signal given the chunks available.

---

## Current capabilities

This prototype is implemented in Python and focuses on **perceptual media**:

- Images: PNG/JPEG/BMP input, holographic `.holo` directory of chunks,  
  reconstruction to a viewable image (PNG).  
- Audio: WAV PCM 16‑bit or 24‑bit input, holographic `.holo` directory,  
  reconstruction to WAV 16‑bit.  
- Binary files (including PDF, DOCX, etc.): experimental support aimed at
  “all‑chunks‑present” round‑trip; there is *no* structural resilience if you
  delete chunks (formats like PDF do not degrade gracefully).

The codec is intentionally simple:

- images: global thumbnail + pixel‑domain residuals  
- audio: coarse downsampled track + temporal residuals  
- chunking: residuals are interleaved across chunks so that each chunk refines
  different pixels/samples

This makes the structure easy to read and modify, and keeps the mathematics simple.
It is **not** yet tuned for optimal compression; it is a research prototype.

---

## Quick start

You only pass **one argument**: either an original file (encode) or a `.holo`
directory (decode).

### Images

```bash
# Encode: original -> holographic directory
python3 holo.py mars_panorama.png
# creates: mars_panorama.png.holo

# Decode: holographic directory -> reconstructed image
python3 holo.py mars_panorama.png.holo
# creates: mars_panorama.png  (reconstructed)
