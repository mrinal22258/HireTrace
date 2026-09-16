# PixelRAG Architecture Evaluation & Fallback Design Note

**Status:** ARCHITECTURAL SPECIFICATION ONLY — UNBUILT BY DESIGN  
**Date:** September 2026  
**Context:** Evaluation of PixelRAG (StarTrail-org/PixelRAG; Berkeley SkyLab/BAIR) for HireTrace document ingestion.

---

## 1. Executive Summary & Recommendation

**Decision: Do NOT adopt PixelRAG in the default ingestion path.**

PixelRAG replaces text extraction with visual page rendering (screenshot tiles) and visual-language embeddings using a fine-tuned `Qwen3-VL-Embedding-2B` model. While conceptually powerful for visual document retrieval across massive web corpora (e.g. 8.28M Wikipedia pages), its operational profile is diametrically opposed to HireTrace's low-latency, resource-bounded architecture:

1. **Massive Latency & Compute Penalty:**
   - Adds a **2B-parameter vision-language embedding model** to the critical ingestion path.
   - HireTrace's standard retrieval layer uses `all-MiniLM-L6-v2` (22M parameters) or `model2vec` static embeddings (~8M parameters). PixelRAG represents a **~90x to ~250x increase in embedding compute per chunk**.
   - Requires a headless Chromium render pass (`pixelshot`) per page before embedding can commence.
   - Official benchmarks report **~3 minutes to index a single multi-page PDF on Apple M-series silicon**. In HireTrace, evaluation of an entire multi-document dossier targets sub-30s latency.
2. **Mismatch with Target Document Scale:**
   - Resumes and interview notes are typically 1–3 pages of text. PixelRAG is engineered for cross-document visual retrieval across hundreds of pages.
3. **Air-Gapped & Local Privacy Constraint:**
   - Hosted PixelRAG API endpoints (`api.pixelrag.ai`) violate HireTrace's strict constraint that candidate PII and resumes never leave local hardware. Only self-hosted deployments are permissible.

---

## 2. Narrow Viable Use Case: Layout Scrambling & Scanned Images

The single scenario where PixelRAG provides distinct architectural value:
- **Pure scanned image PDFs (raster scans without text layers)** where OCR fails or is disabled.
- Heavily stylized multi-column magazine/design resumes where standard PDF stream extraction scrambles reading order into incoherent text spans.

For layout-aware reading order and table structure recovery, **Docling** (Part 3.6) solves 95% of these failure modes at a fraction of the compute and latency budget.

---

## 3. Opt-in Fallback Specification (If Needed in Future Releases)

If telemetry indicates a meaningful fraction (>5%) of applicant uploads are image-only scans that defeat both pdfplumber and Docling, PixelRAG may be activated strictly behind a feature flag:

### Architectural Shape:
- **Feature Flag:** `PIXELRAG_FALLBACK=1` (default: `0`, strictly disabled).
- **Trigger Condition:** Activated only when both primary parsers extract fewer than 80 characters from a binary PDF/DOCX file.
- **Isolation:** Runs as an external sidecar service (`pixelrag serve`) on a dedicated port, isolated from the core ASGI server process.
- **Rendering & Tiling:** Local `pixelshot <file> -o ./tiles --dpi 200` to tile pages.
- **Retrieval:** Isolated vector index queried only for the affected candidate.

---

## 4. Conclusion

HireTrace prioritizes **Docling** for layout reconstruction and **SentenceTransformers / Model2Vec** for rapid CPU retrieval. PixelRAG remains documented as an opt-in emergency fallback for image-only resumes.
