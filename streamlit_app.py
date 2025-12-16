import streamlit as st
import hashlib
import io
import json
import re
import time
from typing import List, Dict, Any

from classifier import classify_chunk

from pypdf import PdfReader
import docx2txt

st.set_page_config(page_title="MNPI Detector — Demo", layout="wide")

def load_document_bytes(uploaded_file) -> str:
    name = uploaded_file.name.lower()
    if name.endswith(".pdf"):
        reader = PdfReader(io.BytesIO(uploaded_file.read()))
        pages = [p.extract_text() or "" for p in reader.pages]
        return "\n".join(pages)
    elif name.endswith(".docx"):
        with open("._temp_upload.docx", "wb") as f:
            f.write(uploaded_file.getbuffer())
        return docx2txt.process("._temp_upload.docx")
    else:
        return uploaded_file.getvalue().decode("utf-8", errors="ignore")

def sha256_of_text(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()

def redact_sensitive_tokens(s: str) -> str:
    if not isinstance(s, str):
        return s
    s = re.sub(r'\$\s?[\d\.,]+', '[REDACTED]', s)
    s = re.sub(r'\b\d{1,3}(?:,\d{3})*(?:\.\d+)?\b', '[REDACTED]', s)
    s = re.sub(r'\b\d{4}-\d{2}-\d{2}\b', '[REDACTED]', s)
    s = re.sub(r'\b(January|February|March|April|May|June|July|August|September|October|November|December)\b \d{1,2}, \d{4}', '[REDACTED]', s, flags=re.IGNORECASE)
    if len(s) > 240:
        s = s[:237] + "..."
    return s

def render_result_card(chunk_hash: str, idx: int, res: Dict[str, Any]):
    categories = ", ".join(res.get("categories", []))
    evidence = redact_sensitive_tokens(res.get("evidence_summary", ""))
    confidence = res.get("confidence", 0.0)
    risk = res.get("risk_level", "low")
    action = res.get("recommended_action", "human_review")

    html = f"""
    <div style="border-radius:8px; padding:14px; margin-bottom:10px; box-shadow: 0 2px 6px rgba(0,0,0,0.08);">
      <div style="display:flex; justify-content:space-between; align-items:flex-start;">
        <div style="font-weight:600;">Chunk {idx} — <span style="font-weight:400; color:#666;">{chunk_hash[:10]}...</span></div>
        <div style="font-size:13px; color:#444;">Risk: <strong style="color:{ 'crimson' if risk=='high' else ('orange' if risk=='medium' else 'green')}">{risk.upper()}</strong></div>
      </div>
      <div style="margin-top:8px; font-size:14px;">Categories: <em style="color:#333;">{categories or 'None'}</em></div>
      <div style="margin-top:8px;">
        <div style="background:#eee; border-radius:6px; height:12px; width:100%;">
          <div style="height:12px; border-radius:6px; width:{int(confidence*100)}%; background: linear-gradient(90deg,#4caf50,#8bc34a);"></div>
        </div>
        <div style="font-size:12px; color:#666; margin-top:4px;">Confidence: {confidence:.2f}</div>
      </div>
      <div style="margin-top:10px; color:#222;">
        <strong>Evidence (redacted, high-level):</strong>
        <div style="margin-top:6px; color:#333;">{evidence}</div>
      </div>
      <div style="margin-top:10px; display:flex; gap:8px;">
        <button style="background:#1976d2; color:white; padding:6px 10px; border-radius:6px; border:none; cursor:pointer;">Request Human Review</button>
        <button style="background:#e0e0e0; color:#111; padding:6px 10px; border-radius:6px; border:none;">Mark as Reviewed</button>
      </div>
    </div>
    """
    st.markdown(html, unsafe_allow_html=True)


st.title("🔎 MNPI Detector")
st.sidebar.header("Options & Safety")

with st.sidebar:
    st.markdown("**Safety checklist**")
    st.checkbox("Do not upload real confidential documents", value=True, key="chk1")
    st.checkbox("Do not display or persist raw document text", value=True, key="chk2")
    st.markdown("---")
    st.markdown("Model settings (adjust for speed/accuracy if using local model)")
    max_tokens = st.number_input("Max tokens (local LLM)", value=256, min_value=64, max_value=2048, step=64)
    temperature = st.slider("Temperature", 0.0, 1.0, 0.0, 0.05)

st.markdown("Upload a PDF / DOCX / TXT file to analyze for potential MNPI.")
uploaded = st.file_uploader("Choose document", type=["pdf", "docx", "txt"])

if uploaded is not None:
    st.info(f"File uploaded: {uploaded.name}. Processing will NOT show raw content.")
    text = load_document_bytes(uploaded)

    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    chunks: List[str] = []
    current = ""
    max_chars = 3000  
    for p in paragraphs:
        if len(current) + len(p) + 1 > max_chars:
            chunks.append(current)
            current = p
        else:
            current = (current + "\n\n" + p).strip()
    if current:
        chunks.append(current)

    st.write(f"Document split into **{len(chunks)}** chunks (no raw text shown).")

    status = st.empty()
    results: List[Dict[str, Any]] = []
    progress = st.progress(0)

    try:
        pass
    except Exception:
        pass

    for i, chunk in enumerate(chunks, start=1):
        status.text(f"Analyzing chunk {i}/{len(chunks)}...")
        chunk_hash = sha256_of_text(chunk)
        start = time.time()
        res = classify_chunk(chunk)
        elapsed = time.time() - start

        res["evidence_summary"] = redact_sensitive_tokens(res.get("evidence_summary", ""))
        res["chunk_hash"] = chunk_hash
        res["chunk_index"] = i
        res["analysis_time_seconds"] = round(elapsed, 2)

        results.append(res)

        render_result_card(chunk_hash, i, res)

        progress.progress(int(i / len(chunks) * 100))

    status.text("Analysis complete.")
    progress.empty()

    st.markdown("### Sanitized Results (no raw text)")
    simple_rows = []
    for r in results:
        simple_rows.append({
            "chunk_index": r.get("chunk_index"),
            "chunk_hash": r.get("chunk_hash")[:12] + "...",
            "mnpi": r.get("mnpi"),
            "categories": ";".join(r.get("categories", [])),
            "confidence": r.get("confidence"),
            "risk": r.get("risk_level"),
            "action": r.get("recommended_action")
        })
    st.table(simple_rows)

    safe_report = {
        "document_name": uploaded.name,
        "timestamp": time.time(),
        "results": results
    }
    st.download_button("Download sanitized report (JSON)", data=json.dumps(safe_report, indent=2), file_name="mnpi_report.json", mime="application/json")

    st.success("Remember: do NOT share raw documents or raw chunk text. This demo stores only sanitized summaries.")
else:
    st.info("No file uploaded yet. Upload a sample to begin.")
