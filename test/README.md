````markdown
# Resilience test for Holo.Codec + golden permutation

This folder is a small lab around the holographic codec.  
The idea is very concrete: take one image, encode it with the golden‑permutation version of Holo.Codec, then measure how well the image survives when only a subset of the chunks is available. The test script does this statistically and writes everything to a CSV, so you can look at curves and numbers instead of impressions.

The file `holo.py` should be the golden‑permutation codec (with `VERSION_IMG = 2`, `VERSION_AUD = 2`, `VERSION_BIN = 2`). The file `test.py` (or `test_resilience.py`) is the resilience tester.

---

## What the test actually does

When you run the test on an image, the script first makes sure the corresponding `.holo` directory exists. If not, it calls `encode_image_holo_dir` from `holo.py` to create the holographic chunks.

Assume the original image is `flower.jpg`. Encoding produces a directory `flower.jpg.holo` with `B` chunks (in the example here, `B = 32`). Each chunk contains:

- a coarse global thumbnail of the image,
- a golden‑permutation slice of the residual (the detail field).

Once the chunks exist, the script treats them as if they were travelling through an unreliable channel. For each integer `k` from 1 to `B`, it repeats the same experiment several times. In each trial it:

1. chooses at random a subset of `k` chunks out of the `B`,
2. copies those chunks into a temporary directory,
3. decodes an image using only that subset (via `decode_image_holo_dir`),
4. compares the reconstruction with the original.

The comparison is done on RGB pixels, computing the mean squared error (MSE) and the peak signal‑to‑noise ratio (PSNR) in decibels. Each reconstruction gives one line in a CSV file with the fields:

`k_chunks`, `trial`, `mse`, `psnr_db`.

The result is a dataset that tells you, for each `k`, how close the reconstruction is to the original when only `k` chunks survive. A codec behaves in a “holographic” and resilient manner if, for a given `k`, almost any subset of `k` chunks gives similar quality and if the average quality rises smoothly as `k` grows.

---

## Running the test

Put `holo.py`, `test.py` and your test image in the same directory. Then run for example:

```bash
python3 test.py flower.jpg
````

If `flower.jpg.holo` does not exist yet, the script will create it by calling `encode_image_holo_dir`.

By default the tester uses the existing number of chunks in the `.holo` directory and runs 50 random trials for each value of `k`. You can override the block count for encoding (if the `.holo` directory does not exist yet) and the number of trials by adding two integers:

```bash
python3 test.py flower.jpg 32 50
```

After the run, you get a CSV file named `resilience_<name>.csv`. For `flower.jpg` the file is called `resilience_flower.csv`.

---

## What is inside the CSV

Each row in the CSV corresponds to one reconstruction carried out with a particular number of chunks and a particular random choice of which chunks survived.

* `k_chunks` is the number of chunks used in that trial.
* `trial` is a counter identifying the random draw for that `k`.
* `mse` is the mean squared error between original and reconstructed image.
* `psnr_db` is the corresponding PSNR in decibels. When all chunks are present and the reconstruction is bit‑exact, PSNR is infinite.

Having all trials in one file lets you build both the average behaviour (mean MSE/PSNR as a function of `k`) and the spread (how much quality varies between different subsets of the same size).

---

## Example results on `flower.jpg`

On the sample image `flower.jpg` encoded into 32 chunks, the CSV shows a very clean pattern.

With only one chunk out of thirty‑two, the mean PSNR is about **23.65 dB** and the mean MSE is around **280.7**. The image at this point is clearly recognizable: the global structure is already there, although the fine detail is obviously degraded.

As `k` increases, the mean PSNR rises strictly monotonically. The script prints summary lines like:

```text
k =  1  mean PSNR ≈ 23.65 dB
k =  8  mean PSNR ≈ 24.76 dB
k = 16  mean PSNR ≈ 26.7  dB
k = 24  mean PSNR ≈ 29.5  dB
k = 31  mean PSNR ≈ 38.5  dB
```

With `k = 16` (half of the chunks) the reconstruction is already in the mid‑twenties of dB, which for a natural image means visually good. By the time you reach `k ≈ 24` you are around 30 dB, i.e. high‑quality. At `k = 31` the mean PSNR is close to **38.5 dB** with an MSE of only about **9**, essentially indistinguishable from the original to the eye. With all 32 chunks, the reconstruction is exactly equal to the original and PSNR is mathematically infinite.

An equally important detail is how narrow the distribution is for each `k`. For every value of `k` the standard deviation of PSNR across the 50 trials is tiny: a few thousandths of a dB at small `k`, and still below about **0.06 dB** even at `k = 31`. In practical terms, this means that for a fixed number of chunks, almost any random subset gives the same quality within a few hundredths of a decibel. The system does not have “special chunks” that carry disproportionate information: the chunks are statistically interchangeable.

---

## How to interpret resilience from these numbers

The PSNR curve as a function of `k` is exactly the kind of informational collapse one hopes to see in a holographic system.

Starting from `k = 1`, the image is already globally correct but noisy. As you add chunks, PSNR grows in a smooth, concave way. In the early region, each extra chunk reduces a roughly constant fraction of the residual energy. Since PSNR is logarithmic in MSE, when the residual energy becomes small the PSNR steps become larger and the curve bends upward, climbing sharply near full information. At `k = B` the residual energy is zero and the state is the exact original.

The very small standard deviation at each `k` is the other half of the story. It says that quality is determined almost entirely by **how many** chunks survive, not by **which** ones. The residual information has been spread uniformly over the chunk space by the golden permutation, so the loss pattern is almost irrelevant: stopping at `k = 10` chunks gives you essentially the same PSNR regardless of which ten chunks you got.

This is precisely the behaviour expected from a good holographic layout: no single chunk is critical or privileged; information loss behaves like a smooth increase of noise instead of a catastrophic cut‑out of regions.

---

## Did it reach the resilience goal?

Within the design choices of this codec, the answer is yes.

The test does not try to beat JPEG or AVIF in pure compression ratio, nor does it introduce extra redundancy like FEC or fountain codes. The benchmark here is different: keep the total information fixed and rearrange it over chunks so that any subset of chunks carries a fair, self‑similar view of the whole.

On that criterion the results on `flower.jpg` are very strong:

* average quality grows smoothly and strictly with the number of chunks,
* there are no pathological “steps” or special chunks,
* for a given `k` the spread of quality is extremely small, meaning the chunks are effectively interchangeable.

In other words, the golden permutation does what it was designed to do: it turns the residual field into something that is uniformly shared across chunks, and the codec behaves as a resilient, holographic representation under random chunk erasures.

Calling it “the best possible scheme in absolute terms” would require formal proofs and systematic comparisons against every conceivable interleaver and every channel model. What can be said from the data here is more modest and more precise: for a codec that does not add explicit redundancy and only reorders the residual into fixed chunks, this golden‑permutation layout shows the kind of near‑ideal resilience one wants to see. The CSV in this folder is not just a log; it is the experimental footprint of that behaviour.

```
::contentReference[oaicite:0]{index=0}
```

