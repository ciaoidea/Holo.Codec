# Holo.Codec
# Holographic Media Codec for Extreme Networks

<img width="1280" height="640" alt="Holo Codec" src="https://github.com/user-attachments/assets/0bbbe6a5-14bb-498c-ac55-62f2dfed5641" />

Holo.Codec is an experimental **holographic codec for images and audio**, **designed for environments where connectivity is ultra-weak, intermittent, or one-way, and to support the exploration of otherwise inaccessible places**.

Internally it is fully digital, but its behaviour under disturbance is **hybrid in spirit**: as chunks are lost the quality degrades smoothly, in a way that resembles analog observations or long-exposure telescopes integrating light over time, rather than the abrupt “all-or-nothing” failure typical of conventional digital formats.

- deep-space missions and planetary rovers  
- remote exploration (caves, polar regions, underwater)  
- disaster and emergency networks with high packet loss  

Any subset of the transmitted chunks reconstructs a **usable** version of the content.  
More chunks ⇒ more detail. Losing chunks never means “no image” or “no audio”, only
a smooth, graceful degradation in quality.

---

## Core idea

Traditional formats (PNG, JPEG, WAV) are “all-or-nothing”: if the right bytes are
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

Holo.Codec is not a general-purpose archival format. It shines where the dominant
constraint is **link quality**, not storage:

- long-range or deep-space links with very low SNR and limited visibility windows  
- one-way broadcasts or beacons where acknowledgements and re-transmissions are
  expensive or impossible  
- ad-hoc or emergency networks where packet loss is high and unpredictable

In these conditions it behaves like a **digital system with analog-like results**:
as interference and packet loss increase, the reconstruction quality decays gracefully
instead of collapsing. Even under heavy disturbance the operator still sees or hears
a meaningful approximation of the scene, rather than a corrupt or unreadable file.

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
  different space-ground paths); any subset of received chunks still reconstructs
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
- Audio: WAV PCM 16-bit or 24-bit input, holographic `.holo` directory,  
  reconstruction to WAV 16-bit.  
- Binary files (including PDF, DOCX, etc.): experimental support aimed at
  “all-chunks-present” round-trip; there is *no* structural resilience if you
  delete chunks (formats like PDF do not degrade gracefully).

The codec is intentionally simple:

- images: global thumbnail + pixel-domain residuals  
- audio: coarse downsampled track + temporal residuals  
- chunking: residuals are interleaved across chunks so that each chunk refines
  different pixels/samples

This makes the structure easy to read and modify, and keeps the mathematics simple.
It is **not** yet tuned for optimal compression; it is a research prototype.

---

## Amateur packet radio and extreme RF links

Holo.Codec sits above classical amateur packet-radio protocols (AX.25, KISS, VARA, etc.).
The radio link still transports ordinary binary frames; Holo.Codec only changes how
images and audio are mapped into those frames.

On the sender, a normal media file is converted into a holographic directory:

```bash
# Example: holographic image for packet radio, ~20 KB per chunk
python3 holo.py test_image.png 20
# creates: test_image.png.holo with many chunk_XXXX.holo files
````

Each `chunk_XXXX.holo` file becomes an independent payload for the radio link. Frames
can be sent in any order, repeated cyclically, or distributed across multiple
frequencies or relays; every successfully received chunk contributes immediately to
the reconstruction at the receiver.

On the receiving side, collected chunks are stored into a directory named
`test_image.png.holo` and decoded:

```bash
python3 holo.py test_image.png.holo
# reconstructs test_image.png from whatever chunks were received
```

Even if only a fraction of the chunks survive fading, collisions or QRM, the operator
still recovers a globally correct image or audio track, with quality that improves
as more chunk indices are accumulated over time. This behaviour is especially useful
for simplex beacons, satellite experiments, and weak-signal HF links where ARQ and
full reliability are impractical.

<img width="800" height="533" alt="HAM" src="https://github.com/user-attachments/assets/142f4f96-0b88-4d8a-b1f2-36b75272dc0a" />

---

## Progressive telescope imaging and long exposures

Telescopes that integrate light progressively over many short exposures already
produce images that “emerge” from noise as photons accumulate. Holo.Codec can be
applied on top of this process by treating the stacked or partially stacked image
as a signal to be encoded holographically.

Instead of downlinking a single, fragile FITS file or a sequence of raw sub-frames,
the on-board system can produce a set of holographic chunks:

* a coarse, low-resolution map of the field of view
* residual information that captures faint structures and fine detail, spread
  across many chunks

Ground stations that receive only a subset of those chunks still reconstruct a
scientifically meaningful view of the sky: bright sources and large-scale structure
appear early, while fainter galaxies and subtle features gradually emerge as more
chunks are collected over multiple passes. In this way the digital data stream
behaves like an extended optical exposure, with robustness against interruptions
and radiation-induced link failures that would otherwise destroy a conventional
digital file.

![spiral_galaxy_ngc_3982](https://github.com/user-attachments/assets/e54cc636-5720-4458-9545-2a8c1200b027)


---

## Quick start

You pass the input path and, optionally, a target chunk size in kilobytes:

* first argument: original file (encode) or `.holo` directory (decode)
* optional second argument: integer `chunk_kb` ≈ target size per holographic chunk

Smaller `chunk_kb` means more, smaller chunks (better robustness on unstable links,
higher overhead); larger `chunk_kb` means fewer, bigger chunks.

### Images

```bash
# Encode: original -> holographic directory
python3 holo.py mars_panorama.png
# creates: mars_panorama.png.holo

# Encode with ~20 KB target chunk size per holographic chunk
python3 holo.py mars_panorama.png 20
# creates: mars_panorama.png.holo with many smaller chunk_XXXX.holo files

# Decode: holographic directory -> reconstructed image
python3 holo.py mars_panorama.png.holo
# creates: mars_panorama.png  (reconstructed)
