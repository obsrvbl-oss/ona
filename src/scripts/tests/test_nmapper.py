#  Copyright 2015 Observable Networks
#
#  Licensed under the Apache License, Version 2.0 (the "License");
#  you may not use this file except in compliance with the License.
#  You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
from datetime import datetime
from json import dumps
from unittest import TestCase

from mock import patch, MagicMock

from ona_service.nmapper import (
    NmapperService,
    _run_scan,
)
from ona_service.utils import utc

MOCK_SCAN_RESULT = '''<nmaprun scanner="nmap" args="nmap -oX - 192.168.1.1 192.168.1.42" start="1446682101" startstr="Wed Nov  4 18:08:21 2015" version="5.21" xmloutputversion="1.03">
<scaninfo type="syn"  protocol="tcp" numservices="1000" services="1,3-4,6-7,9,13,17,19-26,30,32-33,37,42-43,49,53,70,79-85,88-90,99-100,106,109-111,113,119,125,135,139,143-144,146,161,163,179,199,211-212,222,254-256,259,264,280,301,306,311,340,366,389,406-407,416-417,425,427,443-445,458,464-465,481,497,500,512-515,524,541,543-545,548,554-555,563,587,593,616-617,625,631,636,646,648,666-668,683,687,691,700,705,711,714,720,722,726,749,765,777,783,787,800-801,808,843,873,880,888,898,900-903,911-912,981,987,990,992-993,995,999-1002,1007,1009-1011,1021-1100,1102,1104-1108,1110-1114,1117,1119,1121-1124,1126,1130-1132,1137-1138,1141,1145,1147-1149,1151-1152,1154,1163-1166,1169,1174-1175,1183,1185-1187,1192,1198-1199,1201,1213,1216-1218,1233-1234,1236,1244,1247-1248,1259,1271-1272,1277,1287,1296,1300-1301,1309-1311,1322,1328,1334,1352,1417,1433-1434,1443,1455,1461,1494,1500-1501,1503,1521,1524,1533,1556,1580,1583,1594,1600,1641,1658,1666,1687-1688,1700,1717-1721,1723,1755,1761,1782-1783,1801,1805,1812,1839-1840,1862-1864,1875,1900,1914,1935,1947,1971-1972,1974,1984,1998-2010,2013,2020-2022,2030,2033-2035,2038,2040-2043,2045-2049,2065,2068,2099-2100,2103,2105-2107,2111,2119,2121,2126,2135,2144,2160-2161,2170,2179,2190-2191,2196,2200,2222,2251,2260,2288,2301,2323,2366,2381-2383,2393-2394,2399,2401,2492,2500,2522,2525,2557,2601-2602,2604-2605,2607-2608,2638,2701-2702,2710,2717-2718,2725,2800,2809,2811,2869,2875,2909-2910,2920,2967-2968,2998,3000-3001,3003,3005-3007,3011,3013,3017,3030-3031,3050,3052,3071,3077,3128,3168,3211,3221,3260-3261,3268-3269,3283,3300-3301,3306,3322-3325,3333,3351,3367,3369-3372,3389-3390,3404,3476,3493,3517,3527,3546,3551,3580,3659,3689-3690,3703,3737,3766,3784,3800-3801,3809,3814,3826-3828,3851,3869,3871,3878,3880,3889,3905,3914,3918,3920,3945,3971,3986,3995,3998,4000-4006,4045,4111,4125-4126,4129,4224,4242,4279,4321,4343,4443-4446,4449,4550,4567,4662,4848,4899-4900,4998,5000-5004,5009,5030,5033,5050-5051,5054,5060-5061,5080,5087,5100-5102,5120,5190,5200,5214,5221-5222,5225-5226,5269,5280,5298,5357,5405,5414,5431-5432,5440,5500,5510,5544,5550,5555,5560,5566,5631,5633,5666,5678-5679,5718,5730,5800-5802,5810-5811,5815,5822,5825,5850,5859,5862,5877,5900-5904,5906-5907,5910-5911,5915,5922,5925,5950,5952,5959-5963,5987-5989,5998-6007,6009,6025,6059,6100-6101,6106,6112,6123,6129,6156,6346,6389,6502,6510,6543,6547,6565-6567,6580,6646,6666-6669,6689,6692,6699,6779,6788-6789,6792,6839,6881,6901,6969,7000-7002,7004,7007,7019,7025,7070,7100,7103,7106,7200-7201,7402,7435,7443,7496,7512,7625,7627,7676,7741,7777-7778,7800,7911,7920-7921,7937-7938,7999-8002,8007-8011,8021-8022,8031,8042,8045,8080-8090,8093,8099-8100,8180-8181,8192-8194,8200,8222,8254,8290-8292,8300,8333,8383,8400,8402,8443,8500,8600,8649,8651-8652,8654,8701,8800,8873,8888,8899,8994,9000-9003,9009-9011,9040,9050,9071,9080-9081,9090-9091,9099-9103,9110-9111,9200,9207,9220,9290,9415,9418,9485,9500,9502-9503,9535,9575,9593-9595,9618,9666,9876-9878,9898,9900,9917,9943-9944,9968,9998-10004,10009-10010,10012,10024-10025,10082,10180,10215,10243,10566,10616-10617,10621,10626,10628-10629,10778,11110-11111,11967,12000,12174,12265,12345,13456,13722,13782-13783,14000,14238,14441-14442,15000,15002-15004,15660,15742,16000-16001,16012,16016,16018,16080,16113,16992-16993,17877,17988,18040,18101,18988,19101,19283,19315,19350,19780,19801,19842,20000,20005,20031,20221-20222,20828,21571,22939,23502,24444,24800,25734-25735,26214,27000,27352-27353,27355-27356,27715,28201,30000,30718,30951,31038,31337,32768-32785,33354,33899,34571-34573,35500,38292,40193,40911,41511,42510,44176,44442-44443,44501,45100,48080,49152-49161,49163,49165,49167,49175-49176,49400,49999-50003,50006,50300,50389,50500,50636,50800,51103,51493,52673,52822,52848,52869,54045,54328,55055-55056,55555,55600,56737-56738,57294,57797,58080,60020,60443,61532,61900,62078,63331,64623,64680,65000,65129,65389" />
<verbose level="0" />
<debugging level="0" />
<host><status state="down" reason="no-response"/>
<address addr="192.168.1.42" addrtype="ipv4" />
</host>
<host starttime="1446682101" endtime="1446682106"><status state="up" reason="arp-response"/>
<address addr="192.168.1.1" addrtype="ipv4" />
<address addr="67:89:01:23:45:67" addrtype="mac" />
<hostnames>
</hostnames>
<ports><extraports state="filtered" count="992">
<extrareasons reason="no-responses" count="992"/>
</extraports>
<port protocol="tcp" portid="22"><state state="closed" reason="reset" reason_ttl="64"/><service name="ssh" method="table" conf="3" /></port>
<port protocol="tcp" portid="80"><state state="open" reason="syn-ack" reason_ttl="64"/><service name="http" method="table" conf="3" /></port>
<port protocol="tcp" portid="443"><state state="open" reason="syn-ack" reason_ttl="64"/><service name="https" method="table" conf="3" /></port>
</ports>
<times srtt="4579" rttvar="2620" to="100000" />
</host>
<runstats><finished time="1446682106" timestr="Wed Nov  4 18:08:26 2015" elapsed="5.15"/><hosts up="1" down="1" total="2" />
<!-- Nmap done at Wed Nov  4 18:08:26 2015; 2 IP addresses (1 host up) scanned in 5.15 seconds -->
</runstats></nmaprun>
'''  # noqa


class NmapperTest(TestCase):
    def setUp(self):
        self.inst = NmapperService()
        self.inst.api = MagicMock()

    @patch('ona_service.nmapper.NmapProcess', autospec=True)
    def test__run_scan(self, mock_nmap_factory):
        mock_nmap = MagicMock()
        mock_nmap_factory.return_value = mock_nmap

        mock_nmap.run.return_value = 0
        mock_nmap.stdout = MOCK_SCAN_RESULT

        now = datetime(2015, 11, 4)
        res = _run_scan(['1.1.1.1', '2.2.2.2'], now)
        self.assertEqual(res, [
            {
                'time': now.isoformat(),
                'source': '192.168.1.42',
                'ports': '',
                'info_type': 'services',
                'result': '',
            },
            {
                'time': now.isoformat(),
                'source': '192.168.1.1',
                'ports': '22/closed, 80/open, 443/open',
                'info_type': 'services',
                'result': '',
            },
        ])

    @patch('ona_service.nmapper.NmapProcess', autospec=True)
    def test__run_scan__bad_return(self, mock_nmap_factory):
        mock_nmap = MagicMock()
        mock_nmap_factory.return_value = mock_nmap

        mock_nmap.run.return_value = 12
        mock_nmap.stdout = 'foo'
        now = datetime(2015, 11, 4)

        self.assertIsNone(_run_scan(['1.1.1.1', '2.2.2.2'], now))

    @patch('ona_service.nmapper.NmapProcess', autospec=True)
    def test__run_scan__bad_parse(self, mock_nmap_factory):
        mock_nmap = MagicMock()
        mock_nmap_factory.return_value = mock_nmap

        mock_nmap.run.return_value = 0
        mock_nmap.stdout = 'foo'
        now = datetime(2015, 11, 4)

        self.assertIsNone(_run_scan(['1.1.1.1', '2.2.2.2'], now))

    @patch('ona_service.nmapper.MAX_SIMULTANEOUS_TARGETS', 1)
    @patch('ona_service.nmapper._run_scan', autospec=True)
    def test_execute(self, mock_scan):
        mock_scan.return_value = [{'some': 'json'}, {'more': 'json'}]
        actual_results = []

        def _dummy_upload(self, filename, now, suffix=None):
            with open(filename) as f:
                actual_results.append(f.read())
        self.inst.api.send_file.side_effect = _dummy_upload

        # mocking out _get_target_ips
        mock_response = MagicMock()
        mock_response.json.return_value = {
            'meta': {'total_count': 1},
            'objects': [
                {
                    'id': 1,
                    'is_all': True,
                    'is_enabled': True,
                    'scan_targets': ['192.0.2.1', '192.0.2.2']
                }
            ]
        }
        self.inst.api.get_data.return_value = mock_response

        now = datetime(2015, 11, 4)
        self.inst.execute(now)

        utcnow = now.replace(tzinfo=utc)

        mock_scan.assert_any_call(['192.0.2.1'], utcnow)
        mock_scan.assert_any_call(['192.0.2.2'], utcnow)
        self.assertEqual(self.inst.api.send_file.call_count, 2)

        expected_contents = [
            dumps(s, sort_keys=True) + '\n' for s in mock_scan.return_value
        ]
        expected_contents = ''.join(expected_contents)
        self.assertEqual(len(actual_results), 2)
        self.assertEqual(actual_results[0], expected_contents)
        self.assertEqual(actual_results[1], expected_contents)

    @patch('ona_service.nmapper.MAX_SIMULTANEOUS_TARGETS', 1)
    @patch('ona_service.nmapper._run_scan', autospec=True)
    def test_execute__no_results(self, mock_scan):
        mock_scan.return_value = []

        # mocking out _get_target_ips
        mock_response = MagicMock()
        mock_response.json.return_value = {
            'meta': {'total_count': 1},
            'objects': [
                {
                    'id': 1,
                    'is_all': True,
                    'is_enabled': True,
                    'scan_targets': ['192.0.2.1', '192.0.2.2']
                }
            ]
        }
        self.inst.api.get_data.return_value = mock_response

        self.inst.execute()

        mock_scan.assert_any_call(['192.0.2.1'], None)
        mock_scan.assert_any_call(['192.0.2.2'], None)
        self.assertEqual(self.inst.api.call_count, 0)
