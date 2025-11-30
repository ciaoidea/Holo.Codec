# Holographix.io 
# Holographic media and networking for extreme connectivity

[Holographix.io](https://www.holographix.io) is a foundational holographic media and networking architecture that treats data as a distributed field rather than a fragile file. Images, audio and sensor logs are exploded into overlapping holographic chunks that any node can cache, share and recombine, so the network behaves less like a rigid pipe between endpoints and more like a distributed nervous system: fuzzy at the edges, resilient to loss, and able to maintain a coherent picture of the world even when hardware, links or chunks go missing.

<img width="1049" height="900" alt="image" src="https://github.com/user-attachments/assets/8754e568-310f-4719-b5bd-0e4a5b243219" />


Instead of asking a single server for a perfect copy, robots, probes and edge devices contribute and consume fragments of shared “concept fields” and “organized experience fields”. Physical nodes become fuzzy participants in a larger perceptual fabric: each one holds only partial evidence, but the superposition of their chunks yields robust, adaptive awareness across the system, whether the underlying links are clean fibre, noisy radio, or deep‑space relays.

Instead of compressing a file into one fragile bitstream that must arrive perfectly, Holographix turns the file into many small *holographic* chunks. Each chunk carries a global low‑resolution view of the whole content plus a different slice of missing detail.  

If all chunks arrive, you reconstruct something very close to the original.  
If only a fraction survives, you still get a coherent but degraded version: a slightly blurred image instead of a corrupt JPEG, a softer audio track instead of silence.

The project is organised around two working components and one experimental one:

**holo.py** – the holographic media codec for images, audio and generic binaries  
**holo.net.py** – a UDP transport that pushes holographic chunks across extreme networks  
**HNet architecture (planned)** – a content‑centric holographic network built on top of the codec and UDP transport:
- **Holo.Field (planned)** – the local representation of a holographic “concept field” or “organized experience field” for a single object on a robot or server, responsible for stacking chunks, tracking quality and exposing the best available reconstruction to perception and AI modules.
- **Holo.Mesh (planned)** – the distributed overlay that synchronises these fields across many nodes, using Holo.Net as transport, so that robots, probes and edge devices can share holographic chunks of the same scene.

Together, these layers are designed as a next‑generation perceptual fabric for robots and other embodied agents with rich sensory awareness of their environment.

<img width="800" height="600" alt="image" src="https://github.com/user-attachments/assets/cf573e19-ec2c-4e24-9c26-db8515d514f2" />

<img width="800" height="600" alt="image" src="https://github.com/user-attachments/assets/42436e14-c1ec-49b6-97d6-ae157dad7b69" />


---

## How the holographic codec works

The codec always follows the same pattern, whether the input is an image or an audio track.

It first builds a coarse global approximation of the whole signal.  
For images this is a thumbnail resized back to the original resolution.  
For audio this is a track sampled at a small number of frames and linearly interpolated back to full length.

Then it computes the residual

`residual = original - coarse_up`

in 16‑bit integer space. This residual holds all the fine detail that is missing from the coarse view.

The residual array is flattened to a vector of length `N`. Instead of cutting this vector into contiguous blocks, the codec uses a golden‑ratio based permutation based on [The Golden Ration Theorem](https://doi.org/10.4236/apm.2023.139038)


The “golden ratio” here is not a slogan but the solution of a simple proportionality condition. If a segment of total length 1 is split into a longer part of length x and a shorter part of length 1 − x, the golden section is defined by

    whole : longer = longer : shorter
    1 : x = x : (1 − x)

which is equivalent to

    1 / x = x / (1 − x)
    x^2 + x − 1 = 0

The positive solution is x = (sqrt(5) − 1) / 2 ≈ 0.618.  
The classical golden ratio φ is then φ = 1 / x = (1 + sqrt(5)) / 2 ≈ 1.618, with the useful identity φ − 1 = 1 / φ ≈ 0.618. In the codec we use this golden fraction φ − 1 as the normalized step on the residual line, so that the permutation `perm[i] = (i * step) mod N` spreads neighbouring samples as evenly as possible, in line with the Golden Ratio Theorem.

<img width="591" height="256" alt="image" src="https://github.com/user-attachments/assets/235053ab-f4d8-4006-b033-16dac0e8ea9b" />


It picks a step `step ≈ (phi − 1) * N` with `phi = (1 + sqrt(5)) / 2`, adjusts it until `gcd(step, N) = 1`, and defines

`perm[i] = (i * step) mod N`

This produces a single cycle that visits every index exactly once while spreading neighbours very evenly.  

If you choose `B` chunks, chunk `b` takes the residual values at positions

`perm[b], perm[b + B], perm[b + 2B], ...`

so each chunk gets samples from all over the image or waveform, not from a single region.

Each chunk is then written as a small `.holo` file. Inside there is a static coarse representation (PNG for images, compressed int16 for audio) plus one compressed residual slice. All chunks share the same coarse part and each one carries a different slice of residual detail.

Decoding inverts this process. The decoder opens the first valid chunk, recovers dimensions and codec parameters, reconstructs the coarse approximation and allocates a flat residual array filled with zeros. It then regenerates the same golden permutation and, for every available chunk, decompresses the residual slice and writes values back into their positions. Missing slices simply leave zeros. Finally it reshapes the residual to the original shape and sums it with the coarse image or track, clipping into the valid range.

With all chunks present you get a reconstruction that closely matches the original media. With fewer chunks you still get a global percept: the coarse thumbnail provides the structure, while whatever residual happens to be known sharpens details where possible.

Images are handled using RGB uint8 arrays via Pillow and NumPy.  
Audio is handled as 16‑ or 24‑bit PCM WAV (24‑bit is internally converted to 16‑bit).

For generic binaries the same mechanism is applied to a coarse prefix plus the remaining bytes. This improves robustness to lost chunks but, obviously, you do not get graceful perceptual degradation: missing chunks usually mean a corrupted format. The binary mode is mainly there as a robustness and testing tool.

The codec also exposes an image stacking helper. Multiple frames of the same scene can be averaged pixel‑wise into a single deeper exposure and *that* image can then be encoded holographically. Each holographic chunk then carries a view of the stacked frame, so the network can gradually accumulate more photons from many noisy captures.

<img width="1184" height="864" alt="image" src="https://github.com/user-attachments/assets/4cc56a98-2e5b-4197-8724-1646257dcbd4" />

<img width="1184" height="864" alt="image" src="https://github.com/ciaoidea/Holographix.io/blob/main/simulation/ezgif-7a008ed1a76b8024.gif" />


---

## Installation

You need a recent Python 3 interpreter and a few standard scientific libraries.

Clone the repository and create a virtual environment:

```bash
git clone https://github.com/ciaoidea/Holo.Codec.git
cd Holo.Codec

python3 -m venv .venv
source .venv/bin/activate      # on Windows: .venv\Scripts\activate
````

Install the required Python packages:

```bash
pip install numpy pillow
```

The standard library `wave` module is used for audio input/output.
The networking layer only depends on `socket`, `struct` and other standard modules.

---

## Quick start: local holographic codec (`holo.py`)

The script `holo.py` behaves in a dual way:

If you give it a normal file name, it encodes that file into a holographic directory `<file>.holo`.
If you give it a `.holo` directory, it decodes it back to the original file format.

### Encode an image, audio file, or generic binary

```bash
# default chunk sizing
python3 holo.py image.png

# target chunks around 32 KB
python3 holo.py image.png 32

# audio
python3 holo.py track.wav 32

# generic binary (falls back to binary mode)
python3 holo.py archive.bin 32
```

After running one of these commands you will find a directory named `image.png.holo`, `track.wav.holo`, and so on. Inside there are the `chunk_XXXX.holo` files that carry the holographic representation of the original object.

The codec automatically detects the mode from the file extension.
Supported image formats include PNG, JPEG, BMP, GIF, TIFF.
WAV files must be PCM 16‑bit or 24‑bit.

### Decode from a `.holo` directory

```bash
# reconstruct image.png from image.png.holo
python3 holo.py image.png.holo

# reconstruct track.wav from track.wav.holo
python3 holo.py track.wav.holo
```

If the `.holo` directory name ends with the original file name plus `.holo`, the decoder restores that name by stripping the suffix. Otherwise it writes a file named `<dir>_dec`.

To experiment with graceful degradation you can manually delete some `chunk_XXXX.holo` files from the directory and run the decoder again. Fewer chunks produce a blurrier but still globally coherent reconstruction.

### Stack multiple image frames before encoding

If you have multiple frames of the same scene and want to integrate them into a deeper exposure, use the `--stack` mode:

```bash
python3 holo.py --stack 32 frame1.png frame2.png frame3.png
```

This command averages the frames pixel‑wise into `frame1_stack.png`, then encodes that stacked image into `frame1_stack.png.holo` with chunks around 32 KB. Each chunk now carries a view of the stacked, low‑noise frame.

<img width="800" height="600" alt="image" src="https://github.com/user-attachments/assets/d40ff353-4add-4314-82ae-a4d1db4f0994" />

---

## Quick start: holographic UDP transport (`holo.net.py`)

While `holo.py` works on local files, `holo.net.py` adds a simple UDP transport for moving holographic chunks across real networks. The network layer never touches the codec math; it relies entirely on `holo.py` to encode and decode and treats each chunk file as an opaque payload.

The tool has two sub‑commands, `tx` for transmit and `rx` for receive.

Open a receiver in one terminal:

```bash
python3 holo.net.py rx \
    --port 5000 \
    --base-dir . \
    --idle-timeout 60 \
    --payload 65507 \
    --decode-mode best
```

This listens on UDP port 5000, accepts packets up to the maximum UDP payload, and waits up to 60 seconds of silence before attempting reconstruction. In `best` mode it always decodes with whatever chunks are present.

Then, from another terminal or machine, send a file:

```bash
python3 holo.net.py tx image.png 192.168.1.50 \
    --port 5000 \
    --chunk-kb 32 \
    --loops 5 \
    --payload 1200 \
    --delay 0.002
```

In `tx` mode the tool first calls the codec to create `image.png.holo`. It then shuffles the chunk order, slices each chunk into segments that fit into the requested payload size, prepends an HNET header and sends the datagrams to the requested host and port.

Before each full pass over the chunks, a META packet is broadcast with the file name and total chunk count. This allows receivers that start listening mid‑transfer to learn what is being sent.

Once the last loop completes, the temporary `.holo` directory on the sender is deleted.

On the receiver side, as segments arrive they are grouped into complete chunks. Completed chunks are written to a temporary `.holo` directory that mirrors the codec layout. When the idle timeout fires, the receiver calls back into `holo.py` and asks it to decode the directory using all available chunks; in strict mode it only does so if the number of completed chunks matches the announced total.

The parameters let you adapt to many environments. Large payloads and few loops with a very small delay work well on a clean LAN. Small payloads, more loops and a larger delay are better suited to noisy radio links or deep‑space style channels where bit errors, MTU limits and modem buffering all matter.

---

## Conceptual third layer: HNet (Holographic Concept Network)

The codec and the UDP transport already give you an end‑to‑end path from a local file to a reconstructed file at the other end, with graceful degradation built in. This is still host‑centric: a sender addresses a receiver and ships a file.

The project also sketches a higher‑level layer called HNet. The idea is to treat holographic chunk clouds as named objects in a content‑centric network.

Instead of pointing at IP addresses and ports, applications would talk about URIs like

- `holo://mars/sol-1234/navcam/image-0042`
- `holo://dog/001`
- `holo://emergency/flood-zone-7/snapshot-03`

Each URI is mapped to a binary content identifier, for example by hashing the URI string plus codec version. Any node that holds chunks tagged with that content identifier can help reconstruct the object. Nodes cache and re‑serve chunks as they pass through, and a function like `stack()` can align and fuse holographic chunks from many sources into increasingly sharp reconstructions of the same underlying field.

When chunks come from multiple sensors, the mechanism behaves like a distributed synthetic aperture. Each device sees the scene from its own perspective and contributes its own holographic fragments; the network integrates them into a deeper, higher‑resolution field than any single instrument could produce alone.

HNet is not yet shipped as a concrete Python module in this repository. It is the natural next step built on top of `holo.py` and `holo.net.py`: a daemon that maintains a mapping from URIs to content IDs and local `.holo` directories, announces interests in specific objects, and uses the existing codec and transport to exchange and stack holographic chunks.


---

## Design goals and resilience

Holographix was not built as a toy format.  

The original goal is resilience: keep useful information flowing when everything else in the stack is failing – in emergencies, on weak radios, on deep‑space links, or in ad‑hoc swarms of small robots.

The codec and transport are meant to behave more like a living tissue than a brittle protocol. When bandwidth shrinks or packets vanish, they do not stop; they degrade gracefully, recombine whatever fragments are available, and try to maintain a coherent picture of the world from partial evidence. Physical nodes can appear, disappear, or move, but their holographic chunks remain in the field and can still be used by the rest of the network, the way pheromone trails guide ants until they evaporate.

<img width="800" height="800" alt="image" src="https://github.com/user-attachments/assets/2dbd1c2f-9bcb-497b-baeb-903ed0488665" />


This repository is the reference implementation of that idea. The golden‑ratio permutation, the residual representation and the UDP transport are written to be easy to read, modify and evolve, so the architecture can adapt to new radios, modems and sensor stacks instead of being frozen into one environment.

For safety‑critical systems you should treat this implementation as a complementary layer rather than the only one in the loop: run it alongside a conventional, proven telemetry stack. The conventional stack guarantees strict delivery when the channel behaves; Holographix is there to salvage meaning, preserve awareness and keep perception alive when the channel – or parts of the infrastructure – start to fail.

---

## License

The project header in `holo.py` refers to the `LICENSE` file in this repository. Redistribution and modification are governed by the terms described there.

