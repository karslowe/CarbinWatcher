# CarbinWatcher — Edge ML (v1)

On-device waste classification for **CarbinWatcher**, built at **DataHacks 2026** —
*Winner, Cloud Track* · *Winner, Best Model Trained on Impulse AI*.

This repo holds my contribution only: the edge vision pipeline.

Built with Karsten Lowe, Daniel Mathews, and Suvanjan Sitaula.

| | |
|---|---|
| **Submission** | [Devpost](https://devpost.com/software/carbinwatcher) |
| **Full v1 system** | [karslowe/CarbinWatcher](https://github.com/karslowe/CarbinWatcher) |
| **v2 — campus deployment** | [omkar-guru/carbinwatcher-campus](https://github.com/omkar-guru/carbinwatcher-campus) |



## What I built

A waste detector trained on a 20-class taxonomy across four disposal categories —
recycle, compost, landfill, hazardous — exported to ONNX and run locally on an
**Arduino UNO Q** with a USB webcam.

**Location-adaptive disposal.** Recycling rules differ between jurisdictions — the same
container is recyclable in one city and landfill in the next. So identification and
disposal are separate steps: the model determines *what* the object is on-device, then
the Gemini API maps that object to the correct bin for the user's location. Frames never
leave the device; only the predicted label and the location are sent.

MiDaS monocular depth estimation approximates disposal volume.

## Not mine

The cloud pipeline, dashboard, and CO₂ analytics were built by teammates — see the
[team repo](https://github.com/karslowe/CarbinWatcher).

---

## Models — read this before running anything

Two models are involved, and the repo does not contain the deployed one.

**YOLOv8x** — what `notebooks/train_classifier.ipynb` trains. 

**YOLOv8n** — what actually ran on the device. The x model could not hold frame rate on
the UNO Q, so a nano model was retrained on the same dataset and deployed instead.

### The reconstruction

The nano notebook is a reconstruction from memory of the nano training run.
The original was done from a copy of the x notebook on a remote machine I no longer have
access to, and neither its config nor its weights survive.

Weights for the x model are not tracked on this repo
---

## Layout

```
edge/         on-device inference and Arduino integration
models/       labels and class definitions
notebooks/    training and evaluation
```

Hackathon code — preserved as written rather than cleaned up after the fact.

---

## Where this sits

Everything here runs on the station itself: no network, no imagery leaving the device.
That works, but each station needs hardware capable of running the models, which makes
replicating it across a campus expensive.

[**v2**](https://github.com/omkar-guru/carbinwatcher-campus) addresses that by moving
inference to a shared server and reducing each station to an ESP32 and an LCD — trading
the on-device property demonstrated here for deployability at scale.

---

**Omkar Guru** · [github.com/omkar-guru](https://github.com/omkar-guru) ·
[linkedin.com/in/omkar-guru](https://linkedin.com/in/omkar-guru)