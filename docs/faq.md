# FAQ

???+ question "Is CamReview an NVR or live monitor?"

    No. It processes recordings that already exist and then exits. It has no capture, live
    view, retention manager, database, web interface, scheduler, or multi-camera coordinator.
    Run `daily` from an operating-system scheduler for unattended retrospective review.

??? question "Does footage leave the machine?"

    CamReview sends no footage, frames, reports, or telemetry over the network. Local or
    mounted network paths are read directly. Classification runs locally, but Ultralytics
    may download weights when a bare model name is absent from the configured cache.

??? question "Which timestamp is authoritative?"

    The timestamp embedded in the filename is the local wall-clock start. CamReview adds
    each frame's presentation-timestamp offset to it. Filesystem timestamps and embedded
    creation metadata are ignored. Reports have no timezone offset, so daylight-saving folds
    remain ambiguous.

??? question "What does `unknown` mean?"

    Motion occurred, but no accepted moving COCO object was identified. The subject may be
    small, blurred, obscured, outside the model's classes, below the confidence threshold,
    or insufficiently overlapped with the motion mask.

??? question "Why are static objects listed but not used as categories?"

    Classification aims to identify the cause of motion. An always-visible parked car must
    not label unrelated movement. Accepted detections without enough changed-pixel overlap
    stay in JSON under `visible_objects`; overlapping objects appear under `objects` and
    determine categories.

??? question "What belongs to each category?"

    | Category | COCO classes |
    | --- | --- |
    | `person` | person |
    | `pet` | dog, cat |
    | `vehicle` | car, truck, bus, motorcycle, bicycle |
    | `animal` | bird, horse, sheep, cow, elephant, bear, zebra, giraffe |
    | `other` | another accepted moving COCO object |
    | `unknown` | no accepted moving object |

    Classification doesn't identify faces or distinguish individual people or pets.

??? question "Why does JSON contain events excluded from CSV or text?"

    JSON is the canonical evidence record. `--only` and `--exclude` affect CSV, text, and
    extraction without destroying events needed for later reprocessing.

??? question "Is rerunning `daily` safe?"

    Yes. Deterministic report names and atomic replacement prevent duplicate reports. Source
    copies with an existing destination of equal size are reused. Event clips are regenerated
    and replaced. The analysis itself runs again because CamReview has no incremental cache.

??? question "Does hardware decoding run motion detection on the GPU?"

    No. It offloads video decompression when a compatible backend can transfer frames to
    CPU-addressable memory. OpenCV MOG2 still runs on CPU. YOLO classification can use CUDA
    independently through PyTorch.

??? question "Can a Linux report be processed on Windows?"

    Yes. Event sources are normally relative to the scan root. Make the same relative tree
    available and pass its location with `--source-root`. The same approach works from
    Windows to Linux.

??? question "Why are accurate and fast extraction separate?"

    Accurate mode re-encodes H.264 and follows event boundaries closely. Fast mode
    stream-copies, but encoded streams can begin cleanly only at suitable keyframes. A fast
    clip can therefore start earlier than requested.
