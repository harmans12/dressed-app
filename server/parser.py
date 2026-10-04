import re, calendar
from datetime import datetime
from typing import List, Dict, Any
from collections import Counter

MONTHS={m.lower():i for i,m in enumerate(calendar.month_name) if m}
MONTHS.update({m.lower():i for i,m in enumerate(calendar.month_abbr) if m})
WEEKDAYS={m.lower():i for i,m in enumerate(calendar.day_name)}
WEEKDAYS.update({m.lower():i for i,m in enumerate(calendar.day_abbr)})

GENERIC=re.compile(r'^\s*(?:venue|rsvp|warm regards|see you|cordially invites you|where the celebration begins|an evening of|an ode to|dress up|a night of|last hand of the season|please join|save the date|invites you to|you are invited)\b',re.I)
CATEGORY_WORDS=re.compile(r'\b(PARTY|NIGHT|SUNDOWNER|BRUNCH|DINNER|LUNCH|COCKTAIL|CEREMONY|MEHENDI|HALDI|SANGEET|RECEPTION|WEDDING|GATHERING|PUJA|POOJA|BIRTHDAY|ANNIVERSARY|ENGAGEMENT|ROKA|HOUSEWARMING)\b',re.I)
DATE_RE=re.compile(r"(?P<weekday>monday|tuesday|wednesday|thursday|friday|saturday|sunday|mon|tue|wed|thu|fri|sat|sun)?[^0-9]{0,18}(?P<day>\d{1,2})(?:st|nd|rd|th)?[^A-Za-z0-9]{0,8}(?P<month>jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)(?:[^0-9]{0,12}(?P<year>20\d{2}|'\s*\d{2}))?",re.I)
TIME_RE=re.compile(r'\b(\d{1,2})(?::(\d{2}))?\s*(AM|PM)\s*(ONWARDS|ONWARD)?\b',re.I)
YEAR_TITLE_RE=re.compile(r"\b([A-Za-z][A-Za-z0-9&.\-']{1,30}(?:\s+[A-Za-z][A-Za-z0-9&.\-']{1,20}){0,4})\s*'?\s*(\d{2})\b")
ADDRESS_RE=re.compile(r'\b(?:F-?\d+[A-Za-z]?|\d{1,5}[A-Za-z]?|[A-Z]\-\d+[A-Za-z]?)\s+[A-Za-z]|\b(ROAD|DRIVE|STREET|LANE|AVENUE|MARG|CHOWK|CHHATARPUR|SECTOR|BLOCK|FARMS?|FARM|PARK|COLONY|NAGAR|CROSSING)\b',re.I)
VENUE_WORDS=re.compile(r'\b(HOTEL|RESORT|LAWN|BALLROOM|TERRACE|POOL|CURRENT|HALL|ROOM|GARDEN|BANQUET|CLUB|AREA|FARM|FARMS|PAVILION|STUDIO|CAFE|RESTAURANT|ROOFTOP|HOUSE|DRIVE|ROAD|STREET|AVENUE)\b',re.I)
OCR_REPLACEMENTS={'bijlee':'Bijli','bijlt':'Bijli','bili':'Bijli','bilt':'Bijli','bijlii':'Bijli'}

def clean(s:str)->str:
    s=str(s or '').replace('\u00a0',' ').replace('\u2019',"'").replace('\u2018',"'").replace('\u201c','"').replace('\u201d','"').replace('\u2013','-').replace('\u2014','-')
    s=re.sub(r'\s+',' ',s).strip()
    return s.strip(' |:;,.')

def normalize_title(s:str)->str:
    t=clean(s)
    t=re.sub(r'^[^A-Za-z]+','',t)
    t=re.sub(r'[^A-Za-z0-9&.\'\-\s]+$','',t)
    # Remove common OCR prefix junk.
    t=re.sub(r'^(?:G|C|O|Q|Y|V)\s+(?=[A-Za-z])','',t)
    t=re.sub(r"\.\s*(?=['’]?\d{2}\b)", "", t)
    m=YEAR_TITLE_RE.search(t)
    if m:
        words=m.group(1).split()
        if words:
            words[0]=OCR_REPLACEMENTS.get(words[0].lower(),words[0])
            t=' '.join(words)+" '"+m.group(2)
    return clean(t)

def month_num(s):
    s=clean(s).lower()
    for k,v in MONTHS.items():
        if s.startswith(k[:3]):return v
    return None

def parse_date(s,year_hint=None):
    m=DATE_RE.search(clean(s))
    if not m:return None
    day=int(m.group('day'));month=month_num(m.group('month'))
    if not month:return None
    raw=m.group('year')
    if raw:
        raw=raw.replace(' ','')
        year=int(raw[-4:]) if raw.startswith('20') else 2000+int(raw[-2:].replace("'",''))
    elif year_hint:year=int(year_hint)
    else:
        wd=(m.group('weekday') or '').lower();target=WEEKDAYS.get(wd);now=datetime.now().year;cs=[]
        if target is not None:
            for yy in range(now-8,now+9):
                try:
                    if datetime(yy,month,day).weekday()==target:cs.append(yy)
                except ValueError:pass
        year=min(cs,key=lambda x:abs(x-now)) if cs else now
    try:datetime(year,month,day)
    except ValueError:return None
    return {'date':f'{year:04d}-{month:02d}-{day:02d}','year':year,'day':day,'month':month,'weekday':m.group('weekday')}

def parse_time(s):
    m=TIME_RE.search(clean(s))
    if not m:return ''
    return f"{int(m.group(1))}:{int(m.group(2) or 0):02d} {m.group(3).upper()}" + (' onwards' if m.group(4) else '')

def is_date(s):return bool(parse_date(s))
def is_time(s):return bool(parse_time(s))
def is_venue_marker(s):return bool(re.search(r'^\s*(VENUE\s*[:\-]?|@)',clean(s),re.I))

def venue_from_lines(lines):
    lines=[clean(x) for x in lines if clean(x)]
    for i,l in enumerate(lines):
        if is_venue_marker(l):
            v=re.sub(r'^\s*(VENUE\s*[:\-]?|@)\s*','',l,flags=re.I).strip(' .:-')
            if v and not is_date(v) and not is_time(v):return v
            for j in range(i+1,min(len(lines),i+4)):
                x=clean(lines[j])
                if x and not is_date(x) and not is_time(x) and not CATEGORY_WORDS.search(x):return x
    for i,l in enumerate(lines):
        if is_date(l) or is_time(l) or CATEGORY_WORDS.search(l):continue
        if ADDRESS_RE.search(l):
            v=l
            if i+1<len(lines):
                n=clean(lines[i+1])
                if n and not is_date(n) and not is_time(n) and not CATEGORY_WORDS.search(n) and len(n)<55:v+=' '+n
            v=re.sub(r'^[^A-Za-z0-9@#F]+','',v)
            v=re.sub(r'[^A-Za-z0-9)\-\'\.\,&/# ]+$','',v)
            return clean(v)
    for l in lines:
        if not is_date(l) and not is_time(l) and not CATEGORY_WORDS.search(l) and VENUE_WORDS.search(l):return clean(l)
    return ''

def likely_title(s):
    t=clean(s)
    return bool(t and len(t)<=80 and not is_date(t) and not is_time(t) and not is_venue_marker(t) and not GENERIC.search(t) and not ADDRESS_RE.search(t) and not CATEGORY_WORDS.search(t))

def best_title(lines):
    vals=[clean(x) for x in lines if clean(x)]
    ys=[normalize_title(v) for v in vals if YEAR_TITLE_RE.search(v)]
    if ys:return Counter(ys).most_common(1)[0][0]
    candidates=[]
    for i,v in enumerate(vals[:12]):
        if likely_title(v):candidates.append((i,v))
    return normalize_title(candidates[0][1]) if candidates else ''

def category_from_lines(lines,name):
    for v in lines:
        v=clean(v)
        if v and v!=name and CATEGORY_WORDS.search(v):return v
    return 'SOCIAL EVENT'

def dedupe(events):
    out=[];by={}
    for e in events:
        key=(e['date'],e.get('time','').lower())
        if key in by:
            idx=by[key];old=out[idx]
            # Keep the richer record.
            if (len(e.get('venue',''))+len(e.get('name',''))) > (len(old.get('venue',''))+len(old.get('name',''))):out[idx]=e
        else:by[key]=len(out);out.append(e)
    return out

def pdf_events(pages):
    events=[]
    for page in pages:
        lines=[clean(x) for x in page.get('lines',[]) if clean(x)]
        for di,line in enumerate(lines):
            d=parse_date(line)
            if not d:continue
            ti=None;time=''
            for j in range(di,min(len(lines),di+7)):
                tt=parse_time(lines[j])
                if tt:ti=j;time=tt;break
            if ti is None:continue
            # Page-local designed invitation layout.
            after=lines[ti+1:]
            before=lines[max(0,di-8):di]
            name=''
            for cand in after[:5]:
                if likely_title(cand):name=normalize_title(cand);break
            if not name:
                for cand in reversed(before):
                    if likely_title(cand):name=normalize_title(cand);break
            if not name:
                for cand in before+after:
                    if YEAR_TITLE_RE.search(cand):name=normalize_title(cand);break
            venue=venue_from_lines(lines[ti+1:ti+12]) or venue_from_lines(lines)
            category=category_from_lines(lines,name)
            events.append({'name':name or 'Untitled event','date':d['date'],'time':time,'venue':venue,'category':category,'priority':'Normal','confidence':0.99 if name and venue else (0.88 if name else 0.65),'notes':None})
    return dedupe(events)

def image_events(lines):
    vals=[clean(x) for x in lines if clean(x)]
    if not vals:return []
    # Choose a year-bearing title first. Avoid date/time/address lines.
    title=best_title(vals)
    # Candidate dates: count by day/month, regardless of OCR punctuation.
    dc=[]
    for i,v in enumerate(vals):
        d=parse_date(v)
        if d:dc.append((i,d))
    if not dc:
        # Some OCR loses the weekday; search joined text.
        blob=' | '.join(vals)
        d=parse_date(blob)
        if d:dc=[(0,d)]
    if not dc:return []
    counts=Counter((d['day'],d['month']) for _,d in dc)
    day,month=counts.most_common(1)[0][0]
    chosen=next(d for _,d in dc if d['day']==day and d['month']==month)
    ym=YEAR_TITLE_RE.search(title or '')
    if ym: chosen['year']=2000+int(ym.group(2));chosen['date']=f"{chosen['year']:04d}-{month:02d}-{day:02d}"
    tc=Counter(parse_time(v) for v in vals if parse_time(v))
    time=tc.most_common(1)[0][0] if tc else ''
    # Strong address extraction from raw OCR, which is often split across lines.
    venue=venue_from_lines(vals)
    # Prefer a clean address pattern over a noisy OCR line.
    blob=' '.join(vals)
    m=re.search(r'((?:F-?\d+[A-Z]?|\d{1,5}[A-Za-z]?)\s+[A-Za-z][A-Za-z ]{2,55}?(?:Drive|Road|Street|Lane))',blob,re.I)
    if m:
        venue=clean(m.group(1))
        loc=re.search(r'\b(Chhatarpur|Chattarpur)\b',blob,re.I)
        if loc:venue+=' '+loc.group(1)
    venue=re.sub(r'^[^A-Za-z0-9F]+','',venue)
    venue=re.sub(r'[^A-Za-z0-9)\-\'\.\,&/# ]+$','',venue)
    return [{'name':title or 'Untitled event','date':chosen['date'],'time':time,'venue':clean(venue),'category':category_from_lines(vals,title),'priority':'Normal','confidence':0.97 if title and venue else (0.88 if title else 0.65),'notes':None}]
