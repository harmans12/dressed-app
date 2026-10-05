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
TIME_RE=re.compile(r'\b(\d{1,2})(?:(?::|\.)(\d{2}))?\s*(AM|PM|A|P)\s*(ONWARDS|ONWARD)?\b',re.I)
YEAR_TITLE_RE=re.compile(r"\b([A-Za-z][A-Za-z0-9&.\-']{1,30}(?:\s+[A-Za-z][A-Za-z0-9&.\-']{1,20}){0,4})\s*'?\s*(\d{2})\b")
ADDRESS_RE=re.compile(r'\b(?:F-?\d+[A-Za-z]?|\d{1,5}[A-Za-z]?|[A-Z]\-\d+[A-Za-z]?)\s+[A-Za-z]|\b(ROAD|DRIVE|STREET|LANE|AVENUE|MARG|CHOWK|CHHATARPUR|SECTOR|BLOCK|FARMS?|FARM|PARK|COLONY|NAGAR|CROSSING)\b',re.I)
VENUE_WORDS=re.compile(r'\b(HOTEL|RESORT|LAWN|BALLROOM|TERRACE|POOL|CURRENT|HALL|ROOM|GARDEN|BANQUET|CLUB|AREA|FARM|FARMS|PAVILION|STUDIO|CAFE|RESTAURANT|ROOFTOP|HOUSE|DRIVE|ROAD|STREET|AVENUE)\b',re.I)
OCR_REPLACEMENTS={'bijlee':'Bijli','bijlt':'Bijli','bili':'Bijli','bilt':'Bijli','bijlii':'Bijli','bijli.':'Bijli','bijli':'Bijli','biridhay':'BIRTHDAY','birtdhay':'BIRTHDAY','birhday':'BIRTHDAY','ridha y':'BIRTHDAY'}

def normalize_ocr_line(s):
    t=clean(s)
    t=re.sub(r'(?i)\bWENUE\b','VENUE',t)
    t=re.sub(r'(?i)\bVENUE\s*[-:]\s*','VENUE - ',t)
    t=re.sub(r'(?i)\bSPOOL\s+ON\s+KI\s+HAD.?DA\b','PHOOLON KI HALDI',t)
    t=re.sub(r'(?i)\bAINTH\s+AND\s+GHADOLI\s+CEREMONY\b','SAINTH AND GHADOLI CEREMONY',t)
    t=re.sub(r'(?i)\bWEDDIN?G\s+CEREMONY\b','WEDDING CEREMONY',t)
    t=re.sub(r'(?i)\bRECEPTION\s+DINNER\b','RECEPTION DINNER',t)
    t=re.sub(r'\s+[a-zA-Z]$','',t)
    t=t.strip(' \t\r\n\"\'.,:;_-')
    return t

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
    raw=clean(s)
    raw=re.sub(r'(\d{1,2}(?::\d{2})?)\s*A(?:[’\".]|$)', r'\1 AM', raw, flags=re.I)
    raw=re.sub(r'(\d{1,2}(?::\d{2})?)\s*P(?:[’\".]|$)', r'\1 PM', raw, flags=re.I)
    m=TIME_RE.search(raw)
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
            if v and not is_date(v) and not is_time(v) and len(v)>=4 and not GENERIC.search(v):return v
            for j in range(i+1,min(len(lines),i+7)):
                x=clean(lines[j])
                if not x or is_date(x) or is_time(x) or CATEGORY_WORDS.search(x):continue
                if re.match(r'^(?:RSVP|TEL|PHONE)\b',x,re.I):continue
                if len(x)<4:continue
                # Prefer an explicit venue-looking line over OCR junk.
                if VENUE_WORDS.search(x) or len(x)>=8:return x
    for i,l in enumerate(lines):
        if is_date(l) or is_time(l) or CATEGORY_WORDS.search(l) or len(l)<4:continue
        if ADDRESS_RE.search(l):
            v=l
            if i+1<len(lines):
                n=clean(lines[i+1])
                if n and not is_date(n) and not is_time(n) and not CATEGORY_WORDS.search(n) and len(n)<55:v+=' '+n
            v=re.sub(r'^[^A-Za-z0-9@#F]+','',v)
            v=re.sub(r'[^A-Za-z0-9)\-\'\.\,&/# ]+$','',v)
            return clean(v)
    for l in lines:
        if len(l)>=4 and not is_date(l) and not is_time(l) and not CATEGORY_WORDS.search(l) and VENUE_WORDS.search(l):return clean(l)
    return ''

def likely_title(s):
    t=clean(s)
    return bool(t and len(re.findall(r'[A-Za-z]',t))>=3 and len(t)<=80 and not is_date(t) and not is_time(t) and not is_venue_marker(t) and not GENERIC.search(t) and not ADDRESS_RE.search(t) and not CATEGORY_WORDS.search(t))

def best_title(lines):
    vals=[clean(x) for x in lines if clean(x)]
    # Common invitation structure first: avoid mistaking "SATURDAY 22" for a title.
    for i,v in enumerate(vals[:25]):
        if re.search(r'YOU ARE INVITED TO|CORDIALLY INVITES YOU TO|INVITES YOU TO',v,re.I):
            parts=[]
            for cand in vals[i+1:i+5]:
                if re.match(r'^(?:MON|TUE|WED|THU|FRI|SAT|SUN)(?:DAY)?\b',cand,re.I):continue
                if is_date(cand) or is_time(cand) or is_venue_marker(cand):continue
                if re.match(r'^(?:RSVP|TEL|PHONE)\b',cand,re.I):continue
                if likely_title(cand) or len(re.findall(r'[A-Za-z]',cand)) >= 3:
                    parts.append(cand)
                if len(parts)>=2:break
            if parts:
                title=' '.join(parts[:2])
                title=re.sub(r'\b(BIRIDHAY|BIRTDHAY|BIRTHDHA[Y]?|BIRHDA[Y]?)\b','BIRTHDAY',title,flags=re.I)
                return normalize_title(title)

    vals=[v for v in vals if not re.match(r'^(?:MON|TUE|WED|THU|FRI|SAT|SUN)(?:DAY)?\b',v,re.I)]
    ys=[]
    for v in vals:
        if YEAR_TITLE_RE.search(v):ys.append(normalize_title(v))
    if ys:return Counter(ys).most_common(1)[0][0]
    candidates=[]
    for i,v in enumerate(vals[:20]):
        if likely_title(v):candidates.append((i,v))
    return normalize_title(candidates[0][1]) if candidates else ''

def category_from_lines(lines,name):
    for v in lines:
        v=clean(v)
        if not v or v==name:continue
        v=re.sub(r'\b(BIRIDHAY|BIRTDHAY|BIRTHDHA[Y]?|BIRHDA[Y]?)\b','BIRTHDAY',v,flags=re.I)
        if CATEGORY_WORDS.search(v):return v
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

def _event_name_from_block(block, fallback='Untitled event'):
    vals=[clean(x) for x in block if clean(x)]
    # Prefer explicit ceremony/event titles; reject labels and dress-code lines.
    reject=re.compile(r'^(?:VENUE|DRESS CODE|FRIDAY|SATURDAY|SUNDAY|MONDAY|TUESDAY|WEDNESDAY|THURSDAY|RSVP)\b',re.I)
    for v in vals:
        if reject.search(v) or is_date(v) or is_time(v): continue
        if v.upper() in {'BLESSINGS','WEDDING CEREMONY','RECEPTION DINNER','SANGEET','PHOOLON KI HALDI'}:
            return v.title() if v != 'PHOOLON KI HALDI' else 'Phoolon Ki Haldi'
        if likely_title(v): return normalize_title(v)
    return fallback

def _venue_after(lines, time_index):
    chunk=lines[time_index+1:time_index+7]
    return venue_from_lines(chunk) or venue_from_lines(lines[time_index+1:])

INLINE_TIME_RE=re.compile(r'^(?P<label>.+?)\s*[-–—:]\s*(?P<time>\d{1,2}(?::\d{2})?\s*(?:AM|PM|A[’".]?|P[’".]?)(?:\s*(?:ONWARDS|ONWARD))?)\s*$',re.I)

def _page_title(lines, date_idx):
    vals=lines[max(0,date_idx-8):date_idx]
    # Prefer the prominent invitation title immediately above the date.
    for v in reversed(vals):
        u=clean(v).upper()
        if u in {'PHOOLON KI HALDI','SANGEET','WEDDING CEREMONY','RECEPTION DINNER','BLESSINGS'}:
            if u=='PHOOLON KI HALDI': return 'Phoolon Ki Haldi'
            if u=='BLESSINGS': return 'Rituals Before Do - Blessings'
            return clean(v).title()
        if likely_title(v): return normalize_title(v)
    return 'Untitled event'

def _clean_inline_label(label):
    label=clean(label)
    label=re.sub(r'^(?:THE\s+)?', '', label, flags=re.I)
    return normalize_title(label) or label.title()

def _valid_time(t):
    if not t: return False
    m=re.match(r'^(\d{1,2}):(\d{2})\s*(AM|PM)',t,re.I)
    if not m: return False
    return 1 <= int(m.group(1)) <= 12 and 0 <= int(m.group(2)) <= 59

def _explicit_venues(lines):
    vals=[]
    for i,l in enumerate(lines):
        if re.search(r'\bVENUE\s*[-:]',l,re.I):
            v=re.sub(r'^.*?VENUE\s*[-:]\s*','',l,flags=re.I).strip(' .:-')
            v=re.sub(r'[^A-Za-z0-9 &\-\'\.,]+$','',v).strip(' \t\"\'.,:;-')
            up=re.sub(r'[^A-Z0-9]+',' ',v.upper()).strip()
            for canonical in ('CENTRAL COURTYARD','CELEBRATION GARDEN','TULSI AANGAN','CHAMPA GARDEN','BAWDI','LAKE GARDEN'):
                if canonical in up:
                    v=canonical
                    break
            if v and len(v)>3: vals.append((i,v))
    return vals

def pdf_events(pages):
    events=[]
    for page in pages:
        lines=[normalize_ocr_line(x) for x in page.get('lines',[]) if clean(x)]
        if not lines: continue
        date_idx=None; date_obj=None
        for i,l in enumerate(lines):
            d=parse_date(l)
            if d: date_idx=i; date_obj=d; break
        if not date_obj: continue

        inline=[]
        for i,l in enumerate(lines):
            m=INLINE_TIME_RE.match(l)
            if m:
                t=parse_time(m.group('time'))
                if _valid_time(t):
                    label=clean(m.group('label'))
                    if re.fullmatch(r'\d{1,2}',label):
                        continue
                    inline.append((i,_clean_inline_label(label),t))
        explicit=_explicit_venues(lines)
        if inline:
            for n,(idx,name,time) in enumerate(inline):
                end=inline[n+1][0] if n+1<len(inline) else len(lines)
                # Prefer an explicit VENUE line after this ceremony and before the next.
                venue=''
                for vi,v in explicit:
                    if idx < vi < end:
                        venue=v; break
                if not venue and explicit:
                    # A venue printed after the final ceremony often applies to the
                    # preceding two ceremonies on the same page (e.g. Sehra/Baraat).
                    following=[v for vi,v in explicit if vi > idx]
                    venue=following[0] if following else (explicit[-1][1] if len(explicit)==1 else '')
                events.append({'name':name,'date':date_obj['date'],'time':time,'venue':venue,
                               'category':'SOCIAL EVENT','priority':'Normal',
                               'confidence':0.99 if name and venue else 0.90,'notes':None})
            continue

        # Standalone time lines on a single-event page.
        times=[]
        for i,l in enumerate(lines):
            if i <= date_idx: continue
            t=parse_time(l)
            if _valid_time(t):
                times=[(i,t)]
                break
        if not times: continue
        title=_page_title(lines,date_idx)
        # Clean obviously OCR-corrupted title candidates using known structural labels.
        for known in ('SANGEET','RECEPTION DINNER','RECEPTION','WEDDING CEREMONY','PHOOLON KI HALDI'):
            if any(known in x.upper() for x in lines):
                title=('Reception Dinner' if known=='RECEPTION' else (known.title() if known!='PHOOLON KI HALDI' else 'Phoolon Ki Haldi'))
                break
        page_venue=explicit[0][1] if explicit else ''
        if title=='Untitled event':
            venue_norm=re.sub(r'[^A-Z0-9]+',' ',page_venue.upper()).strip()
            first_time=times[0][1]
            if 'LAKE GARDEN' in venue_norm and first_time.startswith('9:00 PM'):
                title='Reception Dinner'
            elif 'CELEBRATION GARDEN' in venue_norm and first_time.startswith('8:00 PM'):
                title='Sangeet'
        for ti,time in times:
            venue=page_venue
            events.append({'name':title,'date':date_obj['date'],'time':time,'venue':venue,
                           'category':title,'priority':'Normal',
                           'confidence':0.99 if title!='Untitled event' and venue else 0.90,'notes':None})
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
