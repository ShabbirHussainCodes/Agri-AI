"""Crop-photo diagnosis (Phase 7, ADR-0018).

A photo goes through, in this order: upload sanitising (imaging), a quality gate (quality), an ONNX
classifier with an out-of-distribution check (classifier), a vision-language model that looks at the same
photo independently (vlm), and a deterministic decision (decision) that is allowed to say "no". Only a
photo that survives all of that reaches the answer step, and the answer step is the same safety stack
as /ask (app/agent/finalize.py): doses only from a verified label card, never from a model.
"""
