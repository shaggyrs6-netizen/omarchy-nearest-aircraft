import importlib.util
import json
import math
import os
from pathlib import Path
import select
import stat
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parent.parent
spec=importlib.util.spec_from_file_location('nearest',ROOT/'nearest.py')
n=importlib.util.module_from_spec(spec);spec.loader.exec_module(n)
NOW=1794129000
HOME={'latitude':36.2,'longitude':-86.52}

def row(**changes):
    return dict({'hex':'abc123','lat':36.21,'lon':-86.52,'alt_baro':5000,'seen_pos':1,'r':'N123AB','flight':'N123AB','t':'C172'},**changes)

def feed(*rows):return {'now':NOW*1000,'ac':list(rows)}

class NearestTests(unittest.TestCase):
    def test_out_of_bounds_timestamp_uses_invalid_feed_path(self):
        with self.assertRaisesRegex(ValueError, "clock"):
            n.nearest(dict(feed(), now=10**400), HOME, NOW)

    def test_out_of_bounds_position_does_not_hide_valid_contact(self):
        candidate, counts = n.nearest(
            feed(row(lat=10**400), row(hex="def456")), HOME, NOW
        )
        self.assertEqual(candidate["hex"], "def456")
        self.assertEqual(counts["invalidRejected"], 1)

    def test_nearest_military_beats_more_distant_civil(self):
        result,_=n.nearest(feed(row(lat=36.22),row(hex='def456',lat=36.201,dbFlags=1,r='10-0215')),HOME,NOW)
        self.assertEqual(result['hex'],'def456');self.assertTrue(result['military'])
    def test_ground_aircraft_excluded(self):
        result,counts=n.nearest(feed(row(lat=36.20001,alt_baro='ground'),row(hex='def456')),HOME,NOW)
        self.assertEqual(result['hex'],'def456');self.assertEqual(counts['groundRejected'],1)
    def test_surface_vehicles_excluded(self):
        self.assertIsNone(n.nearest(feed(row(category='C2')),HOME,NOW)[0])
    def test_unknown_military_classification_eligible(self):
        self.assertIsNotNone(n.nearest(feed(row()),HOME,NOW)[0])
    def test_no_altitude_unknown_airborne_excluded(self):
        self.assertIsNone(n.nearest(feed(row(alt_baro=None)),HOME,NOW)[0])
    def test_explicit_airborne_unknown_altitude_kept_unknown(self):
        candidate,_=n.nearest(feed(row(alt_baro=None,on_ground=False)),HOME,NOW)
        self.assertIsNone(candidate['altitudeFt'])
    def test_stale_positions_excluded(self):
        self.assertIsNone(n.nearest(feed(row(seen_pos=21)),HOME,NOW)[0])
    def test_provider_age_added_to_position_age(self):
        data=feed(row(seen_pos=15));data['now']-=6000
        self.assertIsNone(n.nearest(data,HOME,NOW)[0])
    def test_future_clock_rejected(self):
        data=feed(row());data['now']+=6000
        with self.assertRaises(ValueError):n.nearest(data,HOME,NOW)
    def test_wrong_timestamp_units_rejected(self):
        data=feed(row());data['now']=NOW
        with self.assertRaises(ValueError):n.nearest(data,HOME,NOW)
    def test_non_numeric_position_rejected(self):
        for bad in (True,None,'36.2',float('nan'),float('inf'),91):
            with self.subTest(bad=bad):self.assertIsNone(n.nearest(feed(row(lat=bad)),HOME,NOW)[0])
    def test_missing_age_not_zero(self):
        a=row();a.pop('seen_pos');self.assertIsNone(n.nearest(feed(a),HOME,NOW)[0])
    def test_outside_radius_excluded(self):
        self.assertIsNone(n.nearest(feed(row(lat=40)),HOME,NOW)[0])
    def test_one_mile_includes_near_and_excludes_far(self):
        # Along a meridian: 1 degree is about 69.1 statute miles.
        near=row(lat=HOME['latitude']+0.9/69.1)
        far=row(hex='def456',lat=HOME['latitude']+1.1/69.1)
        candidate,counts=n.nearest(feed(near,far),HOME,NOW,1)
        self.assertEqual(candidate['hex'],near['hex']);self.assertEqual(counts['eligible'],1)
        self.assertIsNone(n.nearest(feed(far),HOME,NOW,1)[0])
        self.assertIsNotNone(n.nearest(feed(far),HOME,NOW,2)[0])
    def test_miles_are_not_nautical_miles(self):
        self.assertIsNone(n.nearest(feed(row(lat=HOME['latitude']+1.1/69.1)),HOME,NOW,1)[0])
    def test_invalid_ranges_rejected(self):
        for value in (0,101,1.5,True,'1',float('nan')):
            with self.subTest(value=value),self.assertRaises(ValueError):n.nearest(feed(row()),HOME,NOW,value)
    def test_small_query_still_covers_rounded_home_offset(self):
        home={'latitude':36.249,'longitude':-86.549}
        url=n.query_url(home,1)
        radius=int(url.rsplit('/',1)[1]);offset=n.distance_bearing(home['latitude'],home['longitude'],36.2,-86.5)[0]/1852
        self.assertGreaterEqual(radius,offset+1609.344/1852)
        self.assertLess(radius,int(n.query_url(home,70).rsplit('/',1)[1]))
    def test_numeric_airline_uses_iata_style(self):
        a,_=n.nearest(feed(row(flight='BAW232')),HOME,NOW)
        self.assertEqual(a['displayId'],'BA232');self.assertEqual(a['callsign'],'BAW232')
    def test_ga_uses_tail_even_if_callsign_differs(self):
        a,_=n.nearest(feed(row(flight='EJA123',r='N123AB')),HOME,NOW)
        self.assertEqual(a['displayId'],'N123AB')
    def test_military_tail_takes_priority_over_airline_mapping(self):
        a,_=n.nearest(feed(row(flight='BAW232',r='10-0215',dbFlags=1)),HOME,NOW)
        self.assertEqual(a['displayId'],'10-0215')
    def test_alphanumeric_airline_callsign_not_invented_flight(self):
        a,_=n.nearest(feed(row(flight='BAW23X')),HOME,NOW)
        self.assertEqual(a['displayId'],'BAW23X');self.assertEqual(a['idKind'],'callsign')
    def test_regional_callsign_not_invented_codeshare(self):
        a,_=n.nearest(feed(row(flight='ENY1234')),HOME,NOW)
        self.assertEqual(a['displayId'],'ENY1234')
    def test_missing_tail_falls_back(self):
        a,_=n.nearest(feed(row(flight='RCH123',r=None,dbFlags=1)),HOME,NOW)
        self.assertEqual(a['displayId'],'RCH123')
    def test_markup_in_identifiers_falls_back_safely(self):
        a,_=n.nearest(feed(row(flight='<img src=x>',r='&lt;img&gt;',t='<svg>')),HOME,NOW)
        self.assertEqual(a['displayId'],'ABC123');self.assertEqual(a['aircraftType'],'')
        self.assertNotIn('<',json.dumps(a))
    def test_non_icao_address_uses_base_adsbx_link(self):
        a,_=n.nearest(feed(row(hex='~abc123')),HOME,NOW)
        self.assertEqual(a['adsbxUrl'],'https://globe.adsbexchange.com/')
    def test_tracking_links_are_public_pages(self):
        a,_=n.nearest(feed(row()),HOME,NOW)
        self.assertEqual(a['fr24Url'],'https://www.flightradar24.com/data/aircraft/n123ab')
        self.assertEqual(a['adsbxUrl'],'https://globe.adsbexchange.com/?icao=abc123')
    def test_bearing_distance(self):
        metres,bearing,direction=n.distance_bearing(0,0,0,1)
        self.assertAlmostEqual(metres,111195,delta=1);self.assertEqual(direction,'E');self.assertAlmostEqual(bearing,90)
    def test_horizontal_distance_not_altitude_selects_nearest(self):
        a,_=n.nearest(feed(row(lat=36.201,alt_baro=35000),row(hex='def456',lat=36.21,alt_baro=1000)),HOME,NOW)
        self.assertEqual(a['hex'],'abc123')
    def test_query_does_not_include_precise_home(self):
        home={'latitude':36.234567,'longitude':-86.543219}
        url=n.query_url(home)
        self.assertIn('/lat/36.2/lon/-86.5/',url);self.assertNotIn('234567',url);self.assertNotIn('543219',url)
    def test_response_size_limit_passed_to_curl(self):
        response=b'HTTP/2 200\r\ncontent-type: application/json\r\n\r\n'+json.dumps(feed(row())).encode()
        with patch.object(n,'read_curl',return_value=response) as run:
            self.assertEqual(n.fetch(HOME)['now'],NOW*1000)
            arguments=run.call_args.args[0];self.assertIn('--max-filesize',arguments);self.assertIn('--max-time',arguments)
            self.assertEqual(arguments[:2], ['curl', '-q'])
    def test_stream_rejects_oversized_headers_and_body(self):
        for output in (b"H" * 80, b"HTTP/2 200\r\n\r\n" + b"B" * 17):
            with self.subTest(output=output), patch.object(n, "MAX_HEADERS", 64), patch.object(n, "MAX_BODY", 16):
                command = [sys.executable, "-c", f"import os; os.write(1, {output!r})"]
                with self.assertRaises(n.FeedError) as failure:
                    n.read_curl(command)
                self.assertEqual(failure.exception.code, -1)

    def test_stream_discards_stderr_without_blocking(self):
        response = b"HTTP/2 200\r\n\r\n{}"
        command = [
            sys.executable, "-c",
            f"import os; os.write(2, b'x' * 200000); os.write(1, {response!r})",
        ]
        self.assertEqual(n.read_curl(command), response)

    def test_429_preserves_retry_after(self):
        response=b'HTTP/2 429\r\nretry-after: 120\r\n\r\n{}'
        with patch.object(n,'read_curl',return_value=response):
            with self.assertRaises(n.FeedError) as context:n.fetch(HOME)
            self.assertEqual(context.exception.code,429);self.assertEqual(context.exception.retry_after,120)

class LocalStateTests(unittest.TestCase):
    def test_coordinates_private_and_not_returned(self):
        with tempfile.TemporaryDirectory() as d:
            directory=Path(d)/'state';result=n.control(directory,dict(action='home',**HOME))
            self.assertEqual(result,{'ok':True});saved=json.loads((directory/'home.json').read_text())
            self.assertEqual(saved['latitude'],HOME['latitude']);self.assertEqual(stat.S_IMODE((directory/'home.json').stat().st_mode),0o600)
            self.assertEqual(stat.S_IMODE(directory.stat().st_mode),0o700)
    def test_pause_resume_preserves_home_and_request_budget(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d);n.control(p,dict(action='home',**HOME));n.write_local(p/'circuit.json',{'nextAllowedAt':NOW+120,'blocked':True})
            n.control(p,{'action':'pause'});self.assertFalse(n.read_local(p/'home.json')['enabled'])
            n.control(p,{'action':'resume'});self.assertTrue(n.read_local(p/'home.json')['enabled'])
            self.assertEqual(n.read_local(p/'circuit.json')['nextAllowedAt'],NOW+120)
    def test_invalid_home_does_not_replace_previous(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d);n.control(p,dict(action='home',**HOME));before=(p/'home.json').read_bytes()
            with self.assertRaises(ValueError):n.control(p,{'action':'home','latitude':91,'longitude':0})
            self.assertEqual((p/'home.json').read_bytes(),before)
    def test_symlink_state_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d);(p/'real').mkdir();(p/'link').symlink_to(p/'real')
            with self.assertRaises(ValueError):n.control(p/'link',dict(action='home',**HOME))
    def test_unconfigured_worker_performs_no_network_call(self):
        with tempfile.TemporaryDirectory() as d:
            p=subprocess.Popen([sys.executable,'-B',str(ROOT/'nearest.py'),'worker','--state-dir',d],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
            try:
                ready,_,_=select.select([p.stdout],[],[],3);self.assertTrue(ready)
                status=json.loads(p.stdout.readline());self.assertEqual(status['state'],'configure');self.assertFalse(status['configured'])
                self.assertFalse((Path(d)/'circuit.json').exists());self.assertFalse((Path(d)/'home.json').exists())
            finally:p.terminate();p.communicate(timeout=3)

if __name__=='__main__':unittest.main(verbosity=2)
