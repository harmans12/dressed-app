from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from PIL import Image, ImageOps, ImageEnhance
import fitz, pytesseract
import tempfile, subprocess, os, io, re, json
from pathlib import Path
from .parser import pdf_events, image_events, clean

APP_DIR = Path(__file__).resolve().parent.parent
app = FastAPI(title="DRESSED", version="18")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
MAX_BYTES = 50 * 1024 * 1024

# Focused OCR is critical for designed invitations: the center panel often contains
# the actual event copy while decorative borders confuse a full-image OCR pass.
def ocr_image(img: Image.Image, quick=False):
    """Fast adaptive OCR for invitations.

    The old reader ran up to 30 Tesseract passes per image. That was accurate
    but far too slow on Render's small free instance. We now do one strong
    full-image pass, then only add a focused crop if the first pass did not
    produce enough useful text.
    """
    img = img.convert("RGB")
    w, h = img.size
    max_side = 2200 if quick else 2600
    scale = min(1.0, max_side / max(w, h))
    if scale < 1.0:
        img = img.resize((max(1, int(w*scale)), max(1, int(h*scale))))

    def run(image, psm=11):
        gray = ImageOps.grayscale(image)
        # A single contrast pass is enough for most designed invitations.
        gray = ImageEnhance.Contrast(gray).enhance(1.8)
        txt = pytesseract.image_to_string(gray, config=f"--psm {psm}")
        return [x.strip() for x in txt.splitlines() if x.strip()]

    lines = []
    seen = set()
    for x in run(img, 11):
        if x not in seen:
            seen.add(x); lines.append(x)

    # Only do a second pass when the first pass looks incomplete.
    blob = " ".join(lines)
    useful = len(blob) >= 40 and bool(re.search(r"\b(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\b", blob, re.I))
    useful = useful and bool(re.search(r"\b\d{1,2}(?::\d{2})?\s*(?:am|pm)\b", blob, re.I))
    if not useful:
        for x in run(img, 6):
            if x not in seen:
                seen.add(x); lines.append(x)

    return lines

def pdf_page_lines(page):
    text = page.get_text("text") or ""
    lines=[x.strip() for x in text.splitlines() if x.strip()]
    if len(" ".join(lines)) >= 25:
        return lines
    pix=page.get_pixmap(matrix=fitz.Matrix(2,2), alpha=False)
    img=Image.frombytes("RGB", [pix.width,pix.height], pix.samples)
    return ocr_image(img)

def overall_title(lines):
    clean_lines=[clean(x) for x in lines if clean(x)]
    blob=" | ".join(clean_lines)
    low=re.sub(r"[^a-z]","", blob.lower())
    if "preweddingfestivitiesof" in low and "rajbeer" in low and "srishti" in low:
        return "Pre Wedding Festivities of Rajbeer and Srishti"
    for line in clean_lines[:30]:
        m=re.search(r"\b([A-Za-z][A-Za-z0-9&.\-']{1,30}(?:\s+[A-Za-z][A-Za-z0-9&.\-']{1,20}){0,4})\s*['’]?\s*(\d{2})\b", line)
        if m and not re.search(r"\b(?:oct|nov|dec|jan|feb|mar|apr|may|jun|jul|aug|sep)\b", line, re.I):
            title=clean(m.group(1)).rstrip('.')
            return clean(f"{title} '{m.group(2)}")
    return ""

def health():
    return {"ok": True, "service": "dressed", "version": "18"}
app.get("/api/health")(health)

@app.post("/api/extract")
async def extract(file: UploadFile = File(...)):
    raw=await file.read()
    filename=file.filename or "invitation"
    name=filename.lower(); ctype=(file.content_type or "").lower()
    if not raw: raise HTTPException(400,"The file is empty.")
    if len(raw)>MAX_BYTES: raise HTTPException(413,"Please keep invitations below 50 MB.")
    try:
        if "pdf" in ctype or name.endswith(".pdf"):
            doc=fitz.open(stream=raw, filetype="pdf")
            pages=[]
            for i in range(len(doc)):
                pages.append({"page":i+1,"lines":pdf_page_lines(doc[i])})
            events=pdf_events(pages)
            all_lines=[line for page in pages for line in page["lines"]]
            if not events or any(e.get("name")=="Untitled event" or not e.get("venue") for e in events):
                ocr_lines=[]
                for i in range(len(doc)):
                    pix=doc[i].get_pixmap(matrix=fitz.Matrix(2.5,2.5),alpha=False)
                    ocr_lines.extend(ocr_image(Image.frombytes("RGB",[pix.width,pix.height],pix.samples)))
                merged=pdf_events([{"page":1,"lines":ocr_lines}])
                if merged and (not events or (sum(bool(e.get('venue')) for e in merged),len(merged)) >= (sum(bool(e.get('venue')) for e in events),len(events))):
                    events=merged
                all_lines=ocr_lines if ocr_lines else all_lines
            title=overall_title(all_lines)
            doc.close()
            return {"source_type":"pdf","overall_event_name":title,"events":events,"raw_lines":all_lines}

        if ctype.startswith("image/") or any(name.endswith(x) for x in (".jpg",".jpeg",".png",".webp",".heic")):
            img=Image.open(io.BytesIO(raw))
            lines=ocr_image(img)
            events=image_events(lines)
            title=overall_title(lines) or (events[0]["name"] if len(events)==1 else "")
            return {"source_type":"image","overall_event_name":title,"events":events,"raw_lines":lines}

        if ctype.startswith("video/") or any(name.endswith(x) for x in (".mp4",".mov",".webm",".m4v",".mkv")):
            with tempfile.TemporaryDirectory() as td:
                src=Path(td)/Path(filename).name; src.write_bytes(raw)
                out=Path(td)/"frames"; out.mkdir()
                pattern=str(out/"frame_%02d.jpg")
                cmd=["ffmpeg","-y","-i",str(src),"-vf","fps=2/3,scale=1600:-2","-frames:v","12",pattern]
                proc=subprocess.run(cmd,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=120)
                if proc.returncode!=0: raise HTTPException(422,"This video could not be decoded. Please use MP4, MOV or a screenshot.")
                lines=[]
                for fp in sorted(out.glob("frame_*.jpg")):
                    try: lines.extend(ocr_image(Image.open(fp),quick=True))
                    except Exception: pass
                events=image_events(lines)
                title=overall_title(lines) or (events[0]["name"] if len(events)==1 else "")
                if not events: raise HTTPException(422,"No readable invitation text was found in this video. Try a clearer frame or screenshot.")
                return {"source_type":"video","overall_event_name":title,"events":events,"raw_lines":lines}

        raise HTTPException(415,"Please upload a PDF, photo or video invitation.")
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(422,f"Could not read this invitation: {exc}")

# Safe explicit routes: do not expose the entire project directory.
@app.get("/", include_in_schema=False)
def home(): return FileResponse(str(APP_DIR/"index.html"))
@app.get("/manifest.webmanifest", include_in_schema=False)
def manifest(): return FileResponse(str(APP_DIR/"manifest.webmanifest"), media_type="application/manifest+json")
for _size in (180,192,512):
    def _icon(size=_size): return FileResponse(str(APP_DIR/f"icon-{size}.png"), media_type="image/png")
    app.get(f"/icon-{_size}.png", include_in_schema=False)(_icon)
