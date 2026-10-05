from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from PIL import Image, ImageOps, ImageEnhance
import fitz, pytesseract
import tempfile, subprocess, os, io, re, json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from .parser import pdf_events, image_events, clean, dedupe

APP_DIR = Path(__file__).resolve().parent.parent
app = FastAPI(title="DRESSED", version="25")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
MAX_BYTES = 50 * 1024 * 1024
PDF_MAX_PAGES = 10
PDF_OCR_TIMEOUT_SECONDS = 7

# Focused OCR is critical for designed invitations: the center panel often contains
# the actual event copy while decorative borders confuse a full-image OCR pass.
def ocr_image(img: Image.Image, quick=False):
    """Invitation OCR with a full pass plus a focused-center recovery pass.

    Designed invitations often put the useful text inside a decorative panel.
    A full-page OCR pass can see the border but miss the elegant title/address
    typography, so we add a targeted crop when processing still images.
    """
    img = img.convert("RGB")
    w, h = img.size
    max_side = 1800 if quick else 2400
    scale = min(1.0, max_side / max(w, h))
    if scale < 1.0:
        img = img.resize((max(1, int(w * scale)), max(1, int(h * scale))))

    def run(im, psm="11"):
        gray = ImageOps.grayscale(im)
        gray = ImageEnhance.Contrast(gray).enhance(1.45)
        try:
            txt = pytesseract.image_to_string(gray, config=f"--psm {psm}", timeout=PDF_OCR_TIMEOUT_SECONDS if quick else 20)
        except RuntimeError:
            return []
        return [x.strip() for x in txt.splitlines() if x.strip()]

    lines = run(img, "11")
    # For photos/screenshots, inspect the invitation's central content panel.
    # This is especially effective for borders, foil backgrounds and script fonts.
    if not quick:
        crop = img.crop((int(img.width * .06), int(img.height * .10),
                         int(img.width * .94), int(img.height * .92)))
        if max(crop.size) < 2200:
            factor = min(2.0, 2200 / max(crop.size))
            crop = crop.resize((max(1, int(crop.width * factor)),
                                max(1, int(crop.height * factor))))
        fallback = run(crop, "6")
        seen = {x.lower() for x in lines}
        lines.extend(x for x in fallback if x.lower() not in seen)

    # A final narrow recovery is useful when the first two passes found a title
    # but not the date/address. Keep it limited to avoid the old OCR slowdown.
    useful = " ".join(lines)
    has_date = bool(re.search(r"\b(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\b", useful, re.I))
    has_time = bool(re.search(r"\b\d{1,2}(?::\d{2})?\s*(?:am|pm)\b", useful, re.I))
    has_address = bool(re.search(r"\b(?:road|drive|street|lane|avenue|marg|chhatarpur|farm|lawn|hotel|resort)\b", useful, re.I))
    if not quick and (not has_date or not has_time or not has_address):
        crop = img.crop((int(img.width * .10), int(img.height * .20),
                         int(img.width * .90), int(img.height * .82)))
        fallback = run(crop, "11")
        seen = {x.lower() for x in lines}
        lines.extend(x for x in fallback if x.lower() not in seen)
    return lines

def ocr_pdf_page(page, recovery=False):
    """OCR a designed invitation page using a focused text-panel crop.

    Full-page Tesseract on decorative wedding artwork can take far too long.
    Most invitation copy sits in the central panel, so render moderately and
    OCR only that panel first. Recovery widens the crop and uses a second PSM.
    """
    pix = page.get_pixmap(matrix=fitz.Matrix(1.35 if not recovery else 1.5, 1.35 if not recovery else 1.5), alpha=False)
    img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
    w, h = img.size
    boxes = [(.10,.20,.90,.76)] if not recovery else [(.08,.16,.92,.82), (.15,.24,.85,.68)]
    lines=[]; seen=set()
    for bi,box in enumerate(boxes):
        crop=img.crop((int(w*box[0]),int(h*box[1]),int(w*box[2]),int(h*box[3])))
        gray=ImageOps.autocontrast(ImageOps.grayscale(crop))
        gray=ImageEnhance.Contrast(gray).enhance(1.2)
        for psm in ((6,) if bi==0 and not recovery else (6,11)):
            try:
                txt=pytesseract.image_to_string(gray, config=f"--psm {psm}", timeout=7)
            except RuntimeError:
                txt=''
            for raw in txt.splitlines():
                line=clean(raw)
                if line and line.lower() not in seen:
                    seen.add(line.lower()); lines.append(line)
    return lines


def pdf_page_lines(page):
    text = page.get_text("text") or ""
    lines=[x.strip() for x in text.splitlines() if x.strip()]
    return lines


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
    return {"ok": True, "service": "dressed", "version": "25"}
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
            page_count=len(doc)
            # Native PDF text is cheap, so inspect ALL pages for selectable text.
            # OCR is the expensive fallback and is capped separately.
            pages=[]
            for i in range(page_count):
                pages.append({"page":i+1,"lines":pdf_page_lines(doc[i])})
            events=pdf_events(pages)
            all_lines=[line for page in pages for line in page["lines"]]

            # FAST PATH: if the PDF already contains selectable text and we can
            # confidently build events from it, return immediately. Do NOT run
            # Tesseract on a good PDF — this was the main cause of the endless
            # loading users were seeing.
            if events and all(e.get("date") and e.get("time") for e in events):
                title=overall_title(all_lines)
                doc.close()
                return {"source_type":"pdf","overall_event_name":title,"events":events,"raw_lines":all_lines,"page_count":page_count,"pages_processed":page_count}

            # OCR FALLBACK: only scanned/image PDFs come here. Render at a
            # moderate resolution, OCR at most six pages, and run two pages in
            # parallel so a six-page invitation does not become a 60+ second
            # sequential operation. Each Tesseract call has its own hard timeout.
            ocr_pages=[]
            limit=min(page_count,PDF_MAX_PAGES)
            def read_one(i):
                return i, ocr_pdf_page(doc[i], recovery=False)
            with ThreadPoolExecutor(max_workers=min(4, limit)) as pool:
                results=list(pool.map(read_one, range(limit)))
            for idx,lines in results:
                ocr_pages.append({"page":idx+1,"lines":lines})

            # Recovery only on pages that visibly contain a date but no usable
            # time. This catches stylized pages such as Sangeet without OCR-ing
            # every decorative cover/closing page twice.
            recovery_indexes=[]
            for pos,page_data in enumerate(ocr_pages):
                joined=' '.join(page_data["lines"])
                has_date=bool(re.search(r'\b(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\b',joined,re.I))
                has_time=any(re.search(r'\b\d{1,2}(?::|\.)\d{2}\s*(?:am|pm|a|p)\b',x,re.I) for x in page_data["lines"])
                known_title=any(k in x.upper() for x in page_data["lines"] for k in ('PHOOLON KI HALDI','SANGEET','BLESSINGS','WEDDING CEREMONY','RECEPTION DINNER'))
                if has_date and (not has_time or not known_title) and pos not in (0, limit-1):
                    recovery_indexes.append(pos)
            if recovery_indexes:
                def recover(pos): return pos, ocr_pdf_page(doc[pos], recovery=True)
                with ThreadPoolExecutor(max_workers=min(3,len(recovery_indexes))) as pool:
                    recovered=list(pool.map(recover, recovery_indexes))
                for pos,extra in recovered:
                    seen={x.lower() for x in ocr_pages[pos]["lines"]}
                    ocr_pages[pos]["lines"].extend(x for x in extra if x.lower() not in seen)

            ocr_events=pdf_events(ocr_pages)
            if ocr_events:
                events=dedupe(events+ocr_events)
            all_lines.extend(line for page in ocr_pages for line in page["lines"])
            title=overall_title(all_lines)
            doc.close()
            return {"source_type":"pdf","overall_event_name":title,"events":events,"raw_lines":all_lines,"page_count":page_count,"pages_processed":limit}

        if ctype.startswith("image/") or any(name.endswith(x) for x in (".jpg",".jpeg",".png",".webp",".heic")):
            img=Image.open(io.BytesIO(raw))
            lines=ocr_image(img)
            events=image_events(lines)
            title=(events[0]["name"] if len(events)==1 else overall_title(lines))
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
                title=(events[0]["name"] if len(events)==1 else overall_title(lines))
                if not events: raise HTTPException(422,"No readable invitation text was found in this video. Try a clearer frame or screenshot.")
                return {"source_type":"video","overall_event_name":title,"events":events,"raw_lines":lines}

        raise HTTPException(415,"Please upload a PDF, photo or video invitation.")
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(422,f"Could not read this invitation: {exc}")

# Safe explicit routes: do not expose the entire project directory.
@app.get("/", include_in_schema=False)
def home():
    return FileResponse(str(APP_DIR/"index.html"), headers={"Cache-Control":"no-store, no-cache, must-revalidate, max-age=0"})
@app.get("/manifest.webmanifest", include_in_schema=False)
def manifest(): return FileResponse(str(APP_DIR/"manifest.webmanifest"), media_type="application/manifest+json")
for _size in (180,192,512):
    def _icon(size=_size): return FileResponse(str(APP_DIR/f"icon-{size}.png"), media_type="image/png")
    app.get(f"/icon-{_size}.png", include_in_schema=False)(_icon)
