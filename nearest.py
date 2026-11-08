#!/usr/bin/env python3
"""Nearest airborne aircraft. Exact home coordinates and telemetry never enter logs."""
import argparse
import datetime as dt
import email.utils
import fcntl
import json
import math
import os
from pathlib import Path
import re
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
DEFAULT_STATE = Path(os.environ.get('XDG_STATE_HOME', str(Path.home()/'.local/state'))) / 'nearest-aircraft'
# Small factual code cross-reference, checked against IATA on 8 November 2026.
# Regional codeshares deliberately retain their broadcast callsigns.
AIRLINES = {'BAW':'BA','AAL':'AA','DAL':'DL','SWA':'WN','UAL':'UA','ASA':'AS','JBU':'B6',
            'FDX':'FX','UPS':'5X','FFT':'F9','SCX':'SY','VIR':'VS','HAL':'HA','GTI':'5Y',
            'PAC':'PO','NCR':'N8'}
REGIONAL = {'SKW','RPA','ENY','JIA','PDT','EDV','ASH','GJS'}

def number(value):
    return isinstance(value, (int,float)) and not isinstance(value,bool) and math.isfinite(value)

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

def nearest(data,home,now,range_miles=DEFAULT_RANGE_MILES):
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
        if metres>range_miles*1609.344:continue
        seen.add(code.lower());counts['eligible']+=1
        display,kind,military,flight=display_identity(dict(row,hex=code.lower()))
        tail=identifier(row.get('r'),24);callsign=identifier(row.get('flight'))
        fr24,adsbx=links(tail,flight,code.lower())
        candidates.append({'hex':code.lower(),'displayId':display,'idKind':kind,'tail':tail,'callsign':callsign,
            'military':military,'aircraftType':identifier(row.get('t'),12),'altitudeFt':altitude,'altitudeBasis':basis,
            'distanceMi':metres/1609.344,'bearingDeg':bearing,'direction':direction,'positionTime':position_time,
            'fr24Url':fr24,'adsbxUrl':adsbx,'_distance':metres})
    if not candidates:return None,counts
    result=min(candidates,key=lambda c:(c['_distance'],c['hex']))
    del result['_distance']
    return result,counts

def private_directory(directory):
    directory=Path(directory)
    if directory.is_symlink():raise ValueError('unsafe_state')
    directory.mkdir(mode=0o700,parents=True,exist_ok=True)
    if directory.stat().st_uid!=os.getuid():raise ValueError('unsafe_state')
    directory.chmod(0o700)
    return directory

def read_local(path,default=None):
    try:
        if path.is_symlink() or path.stat().st_uid!=os.getuid() or path.stat().st_size>4096:return default
        return json.loads(path.read_text())
    except (OSError,ValueError):return default

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
    return f'https://opendata.adsb.fi/api/v3/lat/{lat:.1f}/lon/{lon:.1f}/dist/{radius}'

class FeedError(Exception):
    def __init__(self,code,retry_after=0):self.code=code;self.retry_after=retry_after

def fetch(home,range_miles=DEFAULT_RANGE_MILES):
    command=['curl','--silent','--show-error','--include','--suppress-connect-headers','--max-time','8',
        '--connect-timeout','5','--max-filesize',str(MAX_BODY),'--max-redirs','0',
        '--user-agent','NearestAircraft/0.1 personal Omarchy bar widget',query_url(home,range_miles)]
    try:result=subprocess.run(command,capture_output=True,timeout=10,check=False)
    except (OSError,subprocess.TimeoutExpired):raise FeedError(0)
    if result.returncode:raise FeedError(0)
    try:
        header,body=result.stdout.split(b'\r\n\r\n',1)
        if len(header)>65536 or len(body)>MAX_BODY:raise ValueError()
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

def demo_snapshot(kind='airline'):
    now=time.time();row={'hex':'abc123','lat':36.201,'lon':-86.51,'seen_pos':0,'r':'N123AB','t':'B738','flight':'BAW232','alt_baro':31000}
    if kind=='ga':row.update(flight='N123AB',t='C172',alt_baro=3200)
    if kind=='military':row.update(flight='RCH123',r='10-0215',t='C17',dbFlags=1,alt_baro=18000)
    result,_=nearest({'now':now*1000,'ac':[row]},{'latitude':36.2,'longitude':-86.52},now)
    return dict(state('ok',True),nearest=result,demo=True)

def worker(directory,demo=False,range_miles=DEFAULT_RANGE_MILES):
    if demo:
        emit(demo_snapshot())
        while True:time.sleep(INTERVAL);emit(demo_snapshot())
    directory=private_directory(directory)
    fd=os.open(directory/'worker.lock',os.O_CREAT|os.O_RDWR|os.O_NOFOLLOW,0o600)
    try:fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
    except BlockingIOError:return 3
    parent=os.getppid();last_revision=None;last_state=None;last_fetch=0
    while os.getppid()==parent:
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
                data=fetch(home,range_miles);candidate,counts=nearest(data,home,time.time(),range_miles)
                circuit.update(failures=0,blocked=False)
                emit(dict(state('ok' if candidate else 'empty',True),nearest=candidate,counts=counts))
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
    parser.add_argument('--range-miles',type=int,default=DEFAULT_RANGE_MILES,choices=range(1,MAX_RANGE_MILES+1),metavar='1..100')
    parser.add_argument('--kind',choices=['airline','ga','military'],default='airline')
    args=parser.parse_args()
    if args.command=='demo':emit(demo_snapshot(args.kind));return 0
    if args.command=='control':
        try:
            raw=sys.stdin.buffer.readline(4097)
            if len(raw)>4096:raise ValueError('invalid_input')
            emit(control(args.state_dir,json.loads(raw)))
            return 0
        except (OSError,ValueError):emit({'ok':False,'error':'invalid_location_or_state'});return 1
    try:return worker(args.state_dir,args.demo,args.range_miles)
    except (OSError,ValueError,TypeError,OverflowError):emit(state('error'));return 1

if __name__=='__main__':
    try:raise SystemExit(main())
    except (BrokenPipeError,KeyboardInterrupt):pass
