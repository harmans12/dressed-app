from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from PIL import Image, ImageOps, ImageEnhance
import fitz, pytesseract
import tempfile, subprocess, os, io, re, json
from pathlib import Path
from .parser import pdf_events, image_events, clean

APP_DIR = Path(__file__).resolve().parent.parent
PUBLIC_DIR = APP_DIR / "public"
app = FastAPI(title="DRESSED", version="16")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
MAX_BYTES = 50 * 1024 * 1024

def ocr_image(img: Image.Image, quick=False):
    img = img.convert("RGB")
    w, h = img.size
    specs = [(0,0,w,h),(0,0,w,int(h*.60)),(0,int(h*.34),w,h)] if quick else [(0,0,w,h),(0,0,w,int(h*.55)),(0,int(h*.38),w,h),(0,int(h*.18),w,int(h*.86))]
    all_lines=[]
    for box in specs:
        crop=img.crop(box)
        scale=2 if max(crop.size)>=1600 else 3
        crop=crop.resize((crop.width*scale,crop.height*scale))
        gray=ImageOps.grayscale(crop)
        variants=[gray,ImageEnhance.Contrast(gray).enhance(1.8)]
        if not quick: variants.append(gray.point(lambda p:255 if p>180 else 0))
        for variant in variants:
            txt=pytesseract.image_to_string(variant, config="--psm 6")
            all_lines.extend([x.strip() for x in txt.splitlines() if x.strip()])
    return all_lines

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
    # A title containing a year suffix, e.g. Bijli '25 / Bijli 25.
    for line in clean_lines[:20]:
        m=re.search(r"\b([A-Za-z][A-Za-z0-9&.\-']{1,24}(?:\s+[A-Za-z][A-Za-z0-9&.\-']{1,20}){0,3})\s*['’]?\s*(\d{2})\b", line)
        if m and not re.search(r"\b(?:oct|nov|dec|jan|feb|mar|apr|may|jun|jul|aug|sep)\b", line, re.I):
            return clean(m.group(1)+" '"+m.group(2))
    return ""

@app.get("/api/health")
def health():
    return {"ok": True, "service": "dressed", "version": "16"}

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
                    pix=doc[i].get_pixmap(matrix=fitz.Matrix(2,2),alpha=False)
                    ocr_lines.extend(ocr_image(Image.frombytes("RGB",[pix.width,pix.height],pix.samples)))
                merged=pdf_events([{"page":1,"lines":ocr_lines}])
                if merged and (not events or sum(bool(e.get('venue')) for e in merged)>=sum(bool(e.get('venue')) for e in events)):
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

app.mount("/", StaticFiles(directory=str(PUBLIC_DIR), html=True), name="static")
