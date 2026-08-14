# Model adapters

Adapters normalize ONNX outputs into PerceptShift messages. They do not invent confidence semantics beyond what the adapter documents.

## Classification

- Expected input: NCHW or NHWC float tensor per adapter config.
- Output: class scores → `Classification` / `ClassificationArray`.
- `adapter_confidence` validity is explicit via `confidence_valid`.

## YOLO v8 detection

- Expected layouts vary by export path; do not assume all YOLO exports share one layout.
- Boxes are published in source-image pixel coordinates using half-open intervals `[x_min, x_max) × [y_min, y_max)`.
- Common export pitfalls: transposed outputs, letterbox metadata mismatch, class-score ordering.

## Raw tensor

- Pass-through for operators who post-process externally.
- Still subject to integrity, deadline, and resource gates.

Confidence is not correctness. Offline quality metrics remain offline-attested quality floors.
