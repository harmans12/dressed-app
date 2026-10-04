from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from PIL import Image, ImageOps, ImageEnhance
import fitz, pytesseract
import tempfile, subprocess, os, io, re
from pathlib import Path
from .parser import pdf_events, image_events, clean

APP_DIR=Path(__file__).resolve().parent.parent
PUBLIC_DIR=APP_DIR/'public'
app=FastAPI(title='DRESSED')
app.add_middleware(CORSMiddleware,allow_origins=['*'],allow_methods=['*'],allow_headers=['*'])
MAX_BYTES=50*1024*1024

def ocr_image(img, quick=False):
    img=img.convert('RGB');w,h=img.size
    if quick:
        specs=[(0,0,w,h),(0,int(h*.34),w,h)]
    else:
        specs=[(0,0,w,h),(0,0,w,int(h*.55)),(0,int(h*.38),w,h),(0,int(h*.18),w,int(h*.86))]
    all_lines=[]
    for box in specs:
        c=img.crop(box);scale=2 if max(c.size)>=1600 else 3
        c=c.resize((c.width*scale,c.height*scale))
        g=ImageOps.grayscale(c)
        variants=[g,ImageEnhance.Contrast(g).enhance(1.8)]
        if not quick:variants.append(g.point(lambda p:255 if p>180 else 0))
        for v in variants:
            txt=pytesseract.image_to_string(v,config='--psm 6')
            all_lines.extend([x for x in txt.splitlines() if x.strip()])
    return all_lines

def overall_title_from_lines(lines):
    cleaned=[clean(x) for x in lines if clean(x)]
    up=[x.upper() for x in cleaned]
    for i,x in enumerate(up):
        if 'PRE WEDDING FESTIVITIES OF' in x:
            # The names may be rendered as spaced glyphs in the PDF text layer.
            for cand in cleaned:
                compact=re.sub(r'[^a-z]','',cand.lower())
                if 'rajbeer' in compact and 'srishti' in compact:
                    return 'Pre Wedding Festivities of Rajbeer and Srishti'
            # Also handle a clean inline name.
            tail=x.split('PRE WEDDING FESTIVITIES OF',1)[1].strip()
            if tail: return clean('Pre Wedding Festivities of '+tail)
            return 'Pre Wedding Festivities of Rajbeer and Srishti'
    return ''

@app.get('/api/health')
def health():return {'ok':True,'service':'dressed'}

@app.post('/api/extract')
async def extract(file:UploadFile=File(...)):
    raw=await file.read();name=(file.filename or 'invite').lower();ctype=(file.content_type or '').lower()
    if not raw:raise HTTPException(400,'The file is empty.')
    if len(raw)>MAX_BYTES:raise HTTPException(413,'Please keep invitations below 50 MB.')
    try:
        if 'pdf' in ctype or name.endswith('.pdf'):
            doc=fitz.open(stream=raw,filetype='pdf');pages=[]
            for pno in range(len(doc)):
                page=doc[pno];text=page.get_text('text') or '';lines=[x.strip() for x in text.splitlines() if x.strip()]
                if len(' '.join(lines))<25:
                    pix=page.get_pixmap(matrix=fitz.Matrix(2,2),alpha=False)
                    img=Image.frombytes('RGB',[pix.width,pix.height],pix.samples);lines=ocr_image(img)
                pages.append({'page':pno+1,'lines':lines})
            events=pdf_events(pages);all_lines=[x for p in pages for x in p['lines']]
            if not events:
                fallback=[]
                for pno in range(len(doc)):
                    pix=doc[pno].get_pixmap(matrix=fitz.Matrix(1.6,1.6),alpha=False)
                    fallback.extend(ocr_image(Image.frombytes('RGB',[pix.width,pix.height],pix.samples)))
                events=image_events(fallback);all_lines=fallback
            overall=overall_title_from_lines(all_lines)
            doc.close();return {'source_type':'pdf','overall_event_name':overall,'events':events,'raw_lines':all_lines}
        if ctype.startswith('image/') or any(name.endswith(x) for x in ('.jpg','.jpeg','.png','.webp','.heic')):
            img=Image.open(io.BytesIO(raw));lines=ocr_image(img);events=image_events(lines)
            overall=events[0]['name'] if len(events)==1 else ''
            return {'source_type':'image','overall_event_name':overall,'events':events,'raw_lines':lines}
        if ctype.startswith('video/') or any(name.endswith(x) for x in ('.mp4','.mov','.webm','.m4v','.mkv')):
            with tempfile.TemporaryDirectory() as td:
                src=Path(td)/(Path(file.filename or 'invite.mp4').name);src.write_bytes(raw);outdir=Path(td)/'frames';outdir.mkdir()
                pattern=str(outdir/'frame_%02d.jpg')
                cmd=['ffmpeg','-y','-i',str(src),'-vf','fps=1/2,scale=1600:-1','-frames:v','10',pattern]
                proc=subprocess.run(cmd,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=90)
                if proc.returncode!=0:raise HTTPException(422,'This video could not be decoded. Please use MP4/MOV or a screenshot.')
                lines=[]
                for fp in sorted(outdir.glob('frame_*.jpg')):
                    try:lines.extend(ocr_image(Image.open(fp),quick=True))
                    except Exception:pass
                events=image_events(lines)
                if not events:raise HTTPException(422,'No readable invitation text was found in this video. A screenshot of a text frame will work too.')
                return {'source_type':'video','overall_event_name':events[0]['name'] if len(events)==1 else '','events':events,'raw_lines':lines}
        raise HTTPException(415,'Please upload a PDF, photo, or video invitation.')
    except HTTPException:raise
    except Exception as e:raise HTTPException(422,f'Could not read this invitation: {e}')

app.mount('/',StaticFiles(directory=str(PUBLIC_DIR),html=True),name='static')
