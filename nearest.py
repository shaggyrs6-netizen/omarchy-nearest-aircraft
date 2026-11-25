#!/usr/bin/env python3
"""Nearest airborne aircraft. Exact home coordinates and telemetry never enter logs."""
import argparse
import ctypes
import datetime as dt
import email.utils
import fcntl
from functools import lru_cache
import json
import math
import os
from pathlib import Path
import re
import selectors
import signal
import stat
import subprocess
import sys
import tempfile
import time
from urllib.parse import quote

INTERVAL = 10
MAX_AGE = 20
DEFAULT_RANGE_MILES = 70
MAX_RANGE_MILES = 100
MAX_BODY = 2_000_000
MAX_HEADERS = 65_536
MAX_LOCAL_STATE = 4096
MAX_WATCH_LIST = 511
PR_SET_PDEATHSIG = 1
stopping = False
DEFAULT_STATE = Path(os.environ.get('XDG_STATE_HOME', str(Path.home()/'.local/state'))) / 'nearest-aircraft'
# Small factual code cross-reference, checked against IATA on 8 November 2026.
# Regional codeshares deliberately retain their broadcast callsigns.
AIRLINES = {'BAW':'BA','AAL':'AA','DAL':'DL','SWA':'WN','UAL':'UA','ASA':'AS','JBU':'B6',
            'FDX':'FX','UPS':'5X','FFT':'F9','SCX':'SY','VIR':'VS','HAL':'HA','GTI':'5Y',
            'PAC':'PO','NCR':'N8'}
REGIONAL = {'SKW','RPA','ENY','JIA','PDT','EDV','ASH','GJS'}

def number(value):
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return False
    try:
        return math.isfinite(value)
    except OverflowError:
        return False

def identifier(value, length=16):
    if not isinstance(value,str): return ''
    value=value.strip().upper()
    return value if len(value)<=length and re.fullmatch(r'[A-Z0-9][A-Z0-9-]*',value) else ''

def distance_bearing(lat, lon, target_lat, target_lon):
    p1,p2=map(math.radians,(lat,target_lat));dl=math.radians(target_lon-lon)
    h=math.sin((p2-p1)/2)**2+math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2
    metres=2*6371008.8*math.asin(math.sqrt(min(1,max(0,h))))
    bearing=(math.degrees(math.atan2(math.sin(dl)*math.cos(p2),math.cos(p1)*math.sin(p2)-math.sin(p1)*math.cos(p2)*math.cos(dl)))+360)%360
    directions=('N','NNE','NE','ENE','E','ESE','SE','SSE','S','SSW','SW','WSW','W','WNW','NW','NNW')
    return metres,bearing,directions[int((bearing+11.25)/22.5)%16]

# NWS Memphis CWSU sector outlines (turbulence high/ultra-high KML).
# VHF frequencies: FAA Southeast Chart Supplement effective 29 Oct 2026,
# Memphis Center Nashville RCAG, cross-checked against the SFDPS sector display.
MEMPHIS_SECTOR_62 = (
    (-85.58333, 36.90000),
    (-85.40000, 36.18333),
    (-85.32083, 35.82500),
    (-85.28333, 35.65000),
    (-86.00000, 35.51667),
    (-86.94194, 35.34389),
    (-87.00000, 35.33333),
    (-87.23278, 35.45528),
    (-87.50750, 35.81028),
    (-87.46833, 36.17917),
    (-87.51667, 36.25000),
    (-87.30000, 36.25000),
    (-87.00000, 36.36667),
    (-85.58333, 36.90000),
)
MEMPHIS_SECTOR_61 = (
    (-87.63333, 37.39167),
    (-87.39722, 37.27500),
    (-86.91667, 37.28889),
    (-86.48333, 37.30000),
    (-86.38806, 37.30000),
    (-86.15000, 37.30000),
    (-86.00000, 37.19444),
    (-85.96361, 37.16667),
    (-85.58333, 36.90000),
    (-85.40000, 36.18333),
    (-85.32083, 35.82500),
    (-85.28333, 35.65000),
    (-86.00000, 35.51667),
    (-86.94194, 35.34389),
    (-87.00000, 35.33333),
    (-87.23278, 35.45528),
    (-87.50750, 35.81028),
    (-87.46833, 36.17917),
    (-87.51667, 36.25000),
    (-88.03861, 37.00972),
    (-87.63333, 37.39167),
)


ATLANTA_NORTH_FINAL = (
    (33.6495344, -84.4390256, 90),   # 08L threshold, true course
    (33.6495421, -84.4094539, 270),  # 26R threshold, true course
)


def inside_sector(lat, lon, outline, *, inset=True):
    lon += 360 * round((outline[0][0] - lon) / 360)
    # Estimate distance to the boundary locally and leave a 5 NM margin.
    longitude_scale = math.cos(math.radians(lat))
    latitude_margin = 0 if inset else 5 / 60
    longitude_margin = latitude_margin / max(longitude_scale, 0.01)
    if not (min(point[0] for point in outline) - longitude_margin < lon < max(point[0] for point in outline) + longitude_margin
            and min(point[1] for point in outline) - latitude_margin < lat < max(point[1] for point in outline) + latitude_margin):
        return False
    inside = False
    for (lon_a, lat_a), (lon_b, lat_b) in zip(outline, outline[1:]):
        if (lat_a > lat) != (lat_b > lat):
            crossing = lon_a + (lon_b - lon_a) * (lat - lat_a) / (lat_b - lat_a)
            if lon < crossing:
                inside = not inside
        x, y = (lon_a - lon) * longitude_scale, lat_a - lat
        dx, dy = (lon_b - lon_a) * longitude_scale, lat_b - lat_a
        length_squared = dx * dx + dy * dy
        along = max(0, min(1, -(x * dx + y * dy) / length_squared)) if length_squared else 0
        if math.hypot(x + along * dx, y + along * dy) <= 5 / 60:
            return not inset
    return inside


def track_difference(track, course):
    return abs((track - course + 180) % 360 - 180)


@lru_cache(maxsize=1)
def atc_data():
    data = read_local(Path(__file__).with_name('atc_us.json'), {}, max_bytes=2_000_000, allow_root=True)
    if isinstance(data, dict) and isinstance(data.get('airports'), list) and isinstance(data.get('airspace'), list):
        return data['airports'], data['airspace']
    return (), ()


def center_hint(lat, lon, baro):
    for code, name, rings in atc_data()[1]:
        if not inside_sector(lat, lon, rings[0]) or any(inside_sector(lat, lon, hole, inset=False) for hole in rings[1:]):
            continue
        if code == 'ZME':
            # Leave room around altitude transitions and sector edges.
            if 25000 <= baro <= 33500 and inside_sector(lat, lon, MEMPHIS_SECTOR_62):
                return 'memphisSmyrna', code, name
            if baro >= 36000 and inside_sector(lat, lon, MEMPHIS_SECTOR_61):
                return 'memphisClarksville', code, name
            return 'memphis', code, name
        return 'center', code, name
    return '', '', ''


def atlanta_terminal_hint(lat, lon, baro, track, vertical_rate, distance_nm):
    if vertical_rate < 0:
        for runway_lat, runway_lon, course in ATLANTA_NORTH_FINAL:
            distance, to_threshold, _ = distance_bearing(lat, lon, runway_lat, runway_lon)
            threshold_nm = distance / 1852
            offset = math.radians(track_difference(to_threshold, course))
            # Keep well inside the parallel runway spacing. Also require the
            # aircraft to be approaching the threshold along the runway axis.
            if (track_difference(track, course) <= 12 and offset < math.pi / 2
                    and threshold_nm * math.sin(offset) <= 0.10):
                if 0.6 <= threshold_nm <= 1.7 and 1100 <= baro <= 1750:
                    return 'atlantaTowerNorth'
                if 3.5 <= threshold_nm <= 10 and 1900 <= baro <= 4500:
                    return 'atlantaFinalNorth'
    if distance_nm <= 4 and 1050 <= baro <= 1800:
        return 'atlantaTower'
    if 5 <= distance_nm <= 24 and 2100 <= baro <= 9000:
        return 'atlantaApproach' if vertical_rate < 0 else 'atlantaDeparture'
    return 'atlanta'


def terminal_candidates(lat, lon, baro, track, vertical_rate):
    moving = (number(track) and 0 <= track < 360 and number(vertical_rate)
              and 300 <= abs(vertical_rate) <= 8000)
    for code, name, airport_lat, airport_lon, elevation, towered in atc_data()[0]:
        if abs(airport_lat - lat) > 0.51:
            continue
        height = baro - elevation if number(baro) else None
        if height is not None and not -200 <= height <= 10000:
            continue
        distance, radial, _ = distance_bearing(airport_lat, airport_lon, lat, lon)
        distance_nm = distance / 1852
        if distance_nm > (30 if towered else 3):
            continue
        _, inbound, _ = distance_bearing(lat, lon, airport_lat, airport_lon)
        angle = track_difference(track, inbound if vertical_rate < 0 else (inbound + 180) % 360) if moving else 55
        aligned = moving and angle <= 55
        if distance_nm > (15 if towered else 3) and not aligned:
            continue
        if not towered and height is not None and height > 3000:
            continue
        if height is None and distance_nm > 5:
            continue
        # Prefer a plausible flight path over an airport merely alongside it.
        score = distance_nm + (angle / 10 if moving else 0) + (0 if towered else 2)
        yield score, code, name, towered, height, distance_nm, radial, aligned


def atc_lookup(lat, lon, baro, track, vertical_rate):
    if number(baro) and 20000 <= baro <= 60000:
        return center_hint(lat, lon, baro)

    candidates = sorted(terminal_candidates(lat, lon, baro, track, vertical_rate))
    if not candidates:
        return '', '', ''
    score, code, name, towered, height, distance_nm, radial, aligned = candidates[0]
    if len(candidates) > 1 and candidates[1][0] - score < 1:
        return '', '', ''

    hint = 'airport'
    if towered and aligned and height is not None:
        if distance_nm <= 4 and height <= 2000:
            hint = 'airportTower'
        elif 5 <= distance_nm and height <= 9000:
            hint = 'airportApproach' if vertical_rate < 0 else 'airportDeparture'

    if code == 'KATL':
        hint = atlanta_terminal_hint(lat, lon, baro, track, vertical_rate, distance_nm) if aligned and height is not None else 'atlanta'
    elif code == 'KBNA':
        hint = 'nashville'
        if aligned and height is not None:
            if distance_nm <= 4 and 750 <= baro <= 1500:
                hint = 'tower'
            elif 5 <= distance_nm and 2000 <= baro <= 9000:
                # FAA KBNA ILS/LOC RWY 2L: margin around the printed sector split.
                if 38 <= radial <= 188:
                    hint = 'approachEast'
                elif radial >= 205 or radial <= 21:
                    hint = 'approachWest'
    return hint, code, name


def display_identity(row):
    tail=identifier(row.get('r'),24);callsign=identifier(row.get('flight'))
    flags=row.get('dbFlags');military=number(flags) and flags==int(flags) and int(flags)>=0 and bool(int(flags)&1)
    if military:
        return tail or callsign or row['hex'].upper(), 'tail' if tail else 'callsign' if callsign else 'hex', True, ''
    match=re.fullmatch(r'([A-Z]{3})([0-9]{1,4})',callsign)
    if match and match[1] in AIRLINES and int(match[2])>0:
        flight=AIRLINES[match[1]]+str(int(match[2]))
        return flight,'airline',False,flight
    if callsign[:3] in AIRLINES or callsign[:3] in REGIONAL:
        return callsign or tail or row['hex'].upper(),'callsign',False,''
    return tail or callsign or row['hex'].upper(),'tail' if tail else 'callsign' if callsign else 'hex',False,''

def links(tail,flight,hexcode):
    fr24=('https://www.flightradar24.com/data/aircraft/'+quote(tail.lower(),safe='-') if tail else
          'https://www.flightradar24.com/data/flights/'+flight.lower() if flight else 'https://www.flightradar24.com/')
    adsbx='https://globe.adsbexchange.com/'+('?icao='+hexcode if re.fullmatch(r'[0-9a-f]{6}',hexcode) else '')
    return fr24,adsbx

def valid_range(value):
    return number(value) and value == int(value) and 1 <= value <= MAX_RANGE_MILES

EMERGENCY_CODES = ('7500', '7600', '7700')
API_BASE = 'https://opendata.adsb.fi/api'


def alert_priority(candidate):
    tier = 0 if candidate['emergencySquawk'] else 1 if candidate['watched'] else 2
    return tier, candidate['distanceMi'], candidate['hex']


def wide_alert_queries(watch_tails, squawk_codes, watch_any, squawk_any):
    if watch_any and watch_tails:
        tails = ','.join(sorted(watch_tails))
        yield f'{API_BASE}/v2/registration/{tails}', watch_tails, ()
    if squawk_any:
        for code in EMERGENCY_CODES:
            if code in squawk_codes:
                yield f'{API_BASE}/v2/sqk/{code}', (), (code,)


def nearest(data,home,now,range_miles=DEFAULT_RANGE_MILES,watch_tails=(),squawk_codes=EMERGENCY_CODES,*,alerts_only=False):
    if not valid_range(range_miles):raise ValueError("range")
    if not isinstance(data,dict) or not isinstance(data.get('ac'),list) or len(data['ac'])>5000:
        raise ValueError('schema')
    timestamp=data.get('now')
    if not number(timestamp) or not 1e12<timestamp<1e13: raise ValueError('clock')
    timestamp/=1000
    if now-timestamp>60 or timestamp-now>5:raise ValueError('clock')
    candidates=[];counts={'received':len(data['ac']),'eligible':0,'groundRejected':0,'staleRejected':0,'invalidRejected':0}
    seen=set()
    for row in data['ac']:
        if not isinstance(row,dict):counts['invalidRejected']+=1;continue
        code=row.get('hex','')
        if not isinstance(code,str) or not re.fullmatch(r'~?[0-9a-fA-F]{6}',code) or code.lower() in seen:
            counts['invalidRejected']+=1;continue
        if row.get('alt_baro')=='ground' or row.get('on_ground') is True or row.get('ground') is True or row.get('category') in ('C1','C2','C3'):
            counts['groundRejected']+=1;continue
        lat,lon,age=row.get('lat'),row.get('lon'),row.get('seen_pos')
        if not all(number(v) for v in (lat,lon,age)) or abs(lat)>90 or abs(lon)>180 or age<0:
            counts['invalidRejected']+=1;continue
        position_time=timestamp-age
        if now-position_time>MAX_AGE or position_time-now>5:
            counts['staleRejected']+=1;continue
        baro,geom=row.get('alt_baro'),row.get('alt_geom')
        altitude=baro if number(baro) and -2000<=baro<=65000 else None
        basis='barometric'
        if altitude is None and number(geom) and -2000<=geom<=100000:altitude=geom;basis='geometric'
        # Unknown air/ground state without a usable altitude is not evidence of flight.
        if altitude is None and row.get('on_ground') is not False:
            counts['invalidRejected']+=1;continue
        metres,bearing,direction=distance_bearing(home['latitude'],home['longitude'],lat,lon)
        if not alerts_only and metres>range_miles*1609.344:continue
        seen.add(code.lower());counts['eligible']+=1
        display,kind,military,flight=display_identity(dict(row,hex=code.lower()))
        tail=identifier(row.get('r'),24);callsign=identifier(row.get('flight'))
        fr24,adsbx=links(tail,flight,code.lower())
        squawk=row.get('squawk')
        emergency = str(squawk) if type(squawk) in (str, int) and squawk in (
            '7500', '7600', '7700', 7500, 7600, 7700
        ) else ''
        if emergency not in squawk_codes:
            emergency = ''
        watched=bool(tail and tail in watch_tails)
        if alerts_only and not (watched or emergency):continue
        candidates.append({'emergencySquawk':emergency,'watched':watched,'hex':code.lower(),'displayId':display,'idKind':kind,'tail':tail,'callsign':callsign,
            'military':military,'aircraftType':identifier(row.get('t'),12),'altitudeFt':altitude,'altitudeBasis':basis,
            'distanceMi':metres/1609.344,'bearingDeg':bearing,'direction':direction,'positionTime':position_time,
            'fr24Url':fr24,'adsbxUrl':adsbx, '_radio':(lat,lon,baro,row.get('track'),row.get('baro_rate'))})
    if not candidates:return None,counts
    result = min(candidates, key=alert_priority)
    result['atcHint'], result['atcCode'], result['atcName'] = atc_lookup(*result.pop('_radio'))
    return result,counts

def private_directory(directory):
    directory=Path(directory)
    if directory.is_symlink():raise ValueError('unsafe_state')
    directory.mkdir(mode=0o700,parents=True,exist_ok=True)
    if directory.stat().st_uid!=os.getuid():raise ValueError('unsafe_state')
    directory.chmod(0o700)
    return directory

def read_local(path, default=None, *, max_bytes=MAX_LOCAL_STATE, allow_root=False):
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW)
        try:
            info = os.fstat(fd)
            if not stat.S_ISREG(info.st_mode) or (info.st_uid != os.getuid() and not (allow_root and info.st_uid == 0)):
                return default
            if info.st_size > max_bytes:
                return default
            data = bytearray()
            while len(data) <= max_bytes:
                chunk = os.read(fd, min(65536, max_bytes + 1 - len(data)))
                if not chunk:
                    break
                data.extend(chunk)
        finally:
            os.close(fd)
        if len(data) > max_bytes:
            return default
        return json.loads(data.decode("utf-8"))
    except (OSError, ValueError):
        return default

def write_local(path,data):
    if path.is_symlink():raise ValueError('unsafe_state')
    fd,temp=tempfile.mkstemp(prefix='.write-',dir=path.parent)
    try:
        with os.fdopen(fd,'w') as f:
            os.fchmod(f.fileno(),0o600);json.dump(data,f,allow_nan=False);f.write('\n');f.flush();os.fsync(f.fileno())
        os.replace(temp,path)
    except BaseException:
        # Preserve an interrupted temporary write for inspection; never remove user data.
        raise

def valid_home(config):
    return (isinstance(config,dict) and config.get('schema')==1 and
        number(config.get('latitude')) and number(config.get('longitude')) and
        abs(config['latitude'])<=90 and abs(config['longitude'])<=180 and isinstance(config.get('enabled'),bool))

def control(directory,payload):
    if not isinstance(payload,dict):raise ValueError('invalid_input')
    directory=private_directory(directory);path=directory/'home.json'
    config=read_local(path,{})
    action=payload.get('action')
    if action=='home':
        config={'schema':1,'latitude':payload.get('latitude'),'longitude':payload.get('longitude'),'enabled':True,'revision':time.time_ns()}
        if not valid_home(config):raise ValueError('invalid_location')
    elif action in ('pause','resume') and valid_home(config):
        config=dict(config,enabled=action=='resume',revision=time.time_ns())
        if action=='resume':
            circuit=read_local(directory/'circuit.json',{})
            if isinstance(circuit,dict):
                circuit['blocked']=False;circuit['failures']=0
                circuit.pop('wideRetryAt', None)
                write_local(directory/'circuit.json',circuit)
    else:raise ValueError('location_required')
    write_local(path,config)
    return {'ok':True}

def query_url(home,range_miles=DEFAULT_RANGE_MILES):
    if not valid_range(range_miles):raise ValueError("range")
    # Only a coarse grid centre goes to the provider; exact ranking happens locally.
    lat,lon=round(home['latitude'],1),round(home['longitude'],1)
    offset=distance_bearing(home['latitude'],home['longitude'],lat,lon)[0]/1852
    radius=math.ceil(range_miles*1609.344/1852+offset)+1
    return f'{API_BASE}/v3/lat/{lat:.1f}/lon/{lon:.1f}/dist/{radius}'

class FeedError(Exception):
    def __init__(self,code,retry_after=0):self.code=code;self.retry_after=retry_after

def request_stop(_signal, _frame):
    global stopping
    stopping = True

def read_curl(command, shell_parent=None, request_config=None):
    worker_pid = os.getpid()
    libc = ctypes.CDLL(None, use_errno=True)

    def arm_parent_death():
        # The worker is single-threaded. Arm this before exec and check for
        # a worker exit between fork and prctl.
        if libc.prctl(PR_SET_PDEATHSIG, signal.SIGKILL, 0, 0, 0) != 0:
            os._exit(127)
        if os.getppid() != worker_pid:
            os._exit(127)

    deadline = time.monotonic() + 10
    child = subprocess.Popen(
        command, stdin=subprocess.PIPE if request_config is not None else subprocess.DEVNULL, stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL, preexec_fn=arm_parent_death,
    )
    output = bytearray()
    body_start = None
    try:
        if request_config is not None:
            with child.stdin:
                child.stdin.write(request_config)
        with selectors.DefaultSelector() as selector:
            selector.register(child.stdout, selectors.EVENT_READ)
            while True:
                if stopping or (shell_parent is not None and os.getppid() != shell_parent):
                    raise SystemExit(0)
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise FeedError(0)
                if not selector.get_map():
                    code = child.poll()
                    if code is not None:
                        if code:
                            raise FeedError(0)
                        return bytes(output)
                    time.sleep(min(remaining, 0.1))
                    continue
                if not selector.select(min(remaining, 0.1)):
                    continue
                limit = MAX_HEADERS + 4 if body_start is None else body_start + MAX_BODY
                chunk = os.read(child.stdout.fileno(), min(8192, limit - len(output) + 1))
                if not chunk:
                    selector.unregister(child.stdout)
                    continue
                output.extend(chunk)
                if body_start is None:
                    separator = output.find(b'\r\n\r\n')
                    if separator >= 0:
                        if separator > MAX_HEADERS:
                            raise FeedError(-1)
                        body_start = separator + 4
                    elif len(output) >= MAX_HEADERS + 4:
                        raise FeedError(-1)
                if body_start is not None and len(output) - body_start > MAX_BODY:
                    raise FeedError(-1)
    finally:
        child.stdout.close()
        if child.poll() is None:
            child.kill()
            child.wait(timeout=1)

def fetch(home,range_miles=DEFAULT_RANGE_MILES,shell_parent=None):
    return fetch_url(query_url(home,range_miles), shell_parent)


def fetch_url(url, shell_parent, timeout='8'):
    command=['curl','-q','--silent','--include','--suppress-connect-headers','--max-time',timeout,
        '--connect-timeout','5','--max-filesize',str(MAX_BODY),'--max-redirs','0',
        '--user-agent','NearestAircraft/0.1 personal Omarchy bar widget',
        '--config','-']
    # Keep registrations out of process arguments, even for coverage-wide requests.
    request_config = f'url = "{url}"\n'.encode('ascii')
    try:response=read_curl(command,shell_parent,request_config)
    except (OSError,subprocess.TimeoutExpired):raise FeedError(0)
    try:
        header,body=response.split(b'\r\n\r\n',1)
        if len(header)>MAX_HEADERS or len(body)>MAX_BODY:raise ValueError()
        status=int(header.splitlines()[0].split()[1])
        headers={line.split(b':',1)[0].lower():line.split(b':',1)[1].strip() for line in header.splitlines()[1:] if b':' in line}
        retry=0
        raw=headers.get(b'retry-after',b'').decode('ascii',errors='ignore')[:128]
        if raw.isdecimal():retry=float(raw)
        elif raw:
            try:retry=max(0,email.utils.parsedate_to_datetime(raw).timestamp()-time.time())
            except (ValueError,TypeError,OverflowError):pass
        if status!=200:raise FeedError(status,retry)
        return json.loads(body)
    except FeedError:raise
    except (ValueError,IndexError,UnicodeError):raise FeedError(-1)

def state(code,configured=False,**extra):
    return dict(schema=1,state=code,configured=configured,nearest=None,generatedAt=time.time(),demo=False,**extra)

def emit(data):
    print(json.dumps(data,allow_nan=False,separators=(',',':')),flush=True)

def demo_snapshot(kind='airline', watch_tails=()):
    now=time.time();row={'hex':'abc123','lat':36.201,'lon':-86.51,'seen_pos':0,'r':'N123AB','t':'B738','flight':'BAW232','alt_baro':31000}
    if kind=='ga':row.update(flight='N123AB',t='C172',alt_baro=3200)
    if kind=='military':row.update(flight='RCH123',r='10-0215',t='C17',dbFlags=1,alt_baro=18000)
    result,_=nearest({'now':now*1000,'ac':[row]},{'latitude':36.2,'longitude':-86.52},now,watch_tails=watch_tails)
    return dict(state('ok',True),nearest=result,demo=True)

def worker(directory,demo=False,range_miles=DEFAULT_RANGE_MILES,watch_tails=(),squawk_codes=EMERGENCY_CODES,
           *,watch_any=False,squawk_any=False):
    if demo:
        emit(demo_snapshot(watch_tails=watch_tails))
        while True:time.sleep(INTERVAL);emit(demo_snapshot(watch_tails=watch_tails))
    directory=private_directory(directory)
    fd=os.open(directory/'worker.lock',os.O_CREAT|os.O_RDWR|os.O_NOFOLLOW,0o600)
    try:fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
    except BlockingIOError:return 3
    parent=os.getppid();last_revision=None;last_state=None;last_fetch=0
    wide_queries = tuple(wide_alert_queries(watch_tails, squawk_codes, watch_any, squawk_any))
    while not stopping and os.getppid()==parent:
        home=read_local(directory/'home.json')
        revision=home.get('revision') if valid_home(home) else None
        circuit=read_local(directory/'circuit.json',{})
        if not isinstance(circuit,dict):circuit={}
        configured=valid_home(home)
        if revision!=last_revision:
            last_revision=revision;last_state=None
        if not configured:code='configure'
        elif not home['enabled']:code='paused'
        elif circuit.get('blocked'):code='blocked'
        elif time.time()<float(circuit.get('nextAllowedAt',0)):code=None
        else:
            # Persist the budget across shell reloads and crashes before issuing the request.
            if time.monotonic()-last_fetch<INTERVAL:time.sleep(.5);continue
            last_fetch=time.monotonic();circuit['nextAllowedAt']=time.time()+INTERVAL
            write_local(directory/'circuit.json',circuit)
            try:
                data=fetch(home,range_miles,parent)
                candidate,counts=nearest(data,home,time.time(),range_miles,watch_tails,squawk_codes)
                circuit.update(failures=0,blocked=False)
                candidates = [candidate] if candidate else []
                wide_retry_at = circuit.get('wideRetryAt')
                wide_unavailable = bool(wide_queries and number(wide_retry_at) and time.time() < wide_retry_at)
                if wide_queries and not wide_unavailable:
                    for url, tails, codes in wide_queries:
                        time.sleep(1.05)
                        if stopping or os.getppid() != parent:
                            return 0
                        request_budget = time.time() + 1.1
                        if request_budget > circuit['nextAllowedAt']:
                            circuit['nextAllowedAt'] = request_budget
                            write_local(directory/'circuit.json',circuit)
                        try:
                            data = fetch_url(url, parent, timeout='2')
                            match, _ = nearest(data, home, time.time(), range_miles, tails, codes, alerts_only=True)
                            if match:
                                candidates.append(match)
                        except (FeedError, ValueError) as error:
                            wide_unavailable = True
                            delay = max(30, error.retry_after) if isinstance(error, FeedError) else 30
                            circuit['wideRetryAt'] = time.time() + delay
                            if isinstance(error, FeedError) and error.code == 429:
                                circuit['nextAllowedAt'] = max(circuit['nextAllowedAt'], circuit['wideRetryAt'])
                            if isinstance(error, FeedError) and 400 <= error.code < 500:
                                break
                    circuit['nextAllowedAt'] = max(circuit['nextAllowedAt'], time.time() + 1.05)
                now = time.time()
                candidate = min((item for item in candidates if now - item['positionTime'] <= MAX_AGE),
                                key=alert_priority, default=None)
                emit(dict(state('ok' if candidate else 'empty',True),nearest=candidate,counts=counts,
                          wideAlertUnavailable=wide_unavailable))
            except (FeedError,ValueError) as error:
                failures=min(3,int(circuit.get('failures',0))+1)
                status=error.code if isinstance(error,FeedError) else -1
                retry=error.retry_after if isinstance(error,FeedError) else 0
                blocked=400<=status<500 or failures>=3
                circuit.update(failures=failures,blocked=blocked,nextAllowedAt=max(circuit['nextAllowedAt'],time.time()+max(retry,20*2**(failures-1))))
                emit(state('blocked' if blocked else 'offline',True,httpStatus=status))
            write_local(directory/'circuit.json',circuit)
            last_state='requested';time.sleep(.5);continue
        if code and code!=last_state:emit(state(code,configured));last_state=code
        time.sleep(.5)
    return 0

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command',choices=['worker','control','demo'])
    parser.add_argument('--state-dir',type=Path,default=DEFAULT_STATE)
    parser.add_argument('--demo',action='store_true')
    parser.add_argument('--quiet-control', action='store_true')
    parser.add_argument('--range-miles',type=int,default=DEFAULT_RANGE_MILES,choices=range(1,MAX_RANGE_MILES+1),metavar='1..100')
    parser.add_argument('--kind',choices=['airline','ga','military'],default='airline')
    parser.add_argument('--watch-stdin',action='store_true',help='read one watchlist line from stdin at worker startup')
    parser.add_argument('--squawk-codes',default=','.join(EMERGENCY_CODES))
    parser.add_argument('--watch-any-range',action='store_true')
    parser.add_argument('--squawk-any-range',action='store_true')
    args=parser.parse_args()
    squawk_codes=set(args.squawk_codes.split(',')) & set(EMERGENCY_CODES)
    if args.command=='demo':emit(demo_snapshot(args.kind));return 0
    if args.command=='control':
        try:
            raw=sys.stdin.buffer.readline(4097)
            if len(raw)>4096:raise ValueError('invalid_input')
            result = control(args.state_dir, json.loads(raw))
            if not args.quiet_control:
                emit(result)
            return 0
        except (OSError, ValueError):
            if not args.quiet_control:
                emit({'ok':False,'error':'invalid_location_or_state'})
            return 1
    if not args.demo:
        signal.signal(signal.SIGTERM, request_stop)
    try:
        watch_tails = ()
        if args.watch_stdin:
            with sys.stdin.buffer as stream:
                line = stream.readline(MAX_WATCH_LIST + 2)
            if len(line) > MAX_WATCH_LIST + 1 or not line.endswith(b'\n'):
                raise ValueError('invalid_watchlist')
            watch_tails = {tail for token in line[:-1].decode('ascii').split(',') if (tail := identifier(token,24))}
        return worker(args.state_dir,args.demo,args.range_miles,watch_tails,squawk_codes,
                      watch_any=args.watch_any_range,squawk_any=args.squawk_any_range)
    except (OSError,ValueError,TypeError,OverflowError):emit(state('error'));return 1

if __name__=='__main__':
    try:raise SystemExit(main())
    except (BrokenPipeError,KeyboardInterrupt):pass
