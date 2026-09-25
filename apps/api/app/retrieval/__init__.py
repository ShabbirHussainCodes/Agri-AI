"""Phase 4 -- RAG v1 retrieval (docs/rag/rag-design.md section 1).

embedder.py  -- query-side multilingual-e5-small (ONNX, local CPU)
fusion.py    -- Reciprocal Rank Fusion, a pure function (no DB, no model)
hybrid.py    -- dense + lexical legs against public.chunks, fused with RRF,
                behind the metadata widening cascade
"""
