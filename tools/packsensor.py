#!/usr/bin/env python3

from datetime import datetime, timezone
from os import mkdir
from subprocess import check_output, CalledProcessError, TimeoutExpired, STDOUT
from sys import exc_info
from traceback import print_tb

COMMAND_TIMEOUT = 10


def call_to_file(filename, command):
    try:
        result = check_output(command, timeout=COMMAND_TIMEOUT, stderr=STDOUT, shell=True)
        exc = None
        return_code = 0
    except CalledProcessError as e:
        result = e.output
        exc = exc_info()
        return_code = e.returncode
    except TimeoutExpired as e:
        exc = exc_info()
        result = e.output
        return_code = 'timeout'
    except Exception as e:
        exc = exc_info()
        result = exc[0].encode('utf8')
        return_code = 'exception'

    with open(filename, 'w') as f:
        print(f'Command: `{command}`', file=f)
        print(f'Return Code: `{return_code}`', file=f)
        print('Output:', file=f)
        print('=================', file=f)
        print(result.decode('utf8'), file=f)
        print('=================', file=f)
        if exc is not None:
            print('Exception:', file=f)
            print('*****************', file=f)
            print(f'Type: exc[0]', file=f)
            print(f'Value: exc[1]', file=f)
            print_tb(exc[2], file=f)
            print('!!!!!!!!!!!!!!!!!', file=f)


def main():

    now = datetime.now(timezone.utc)
    packdir = now.strftime('sensorpack-%Y%m%d_%H%M%S')

    print(f'*** Creating sensorpack directory ({packdir})')
    mkdir(packdir)

    print('*** Gathering system information')
    call_to_file(f'{packdir}/00_ona_version.txt', 'cat /opt/obsrvbl-ona/version')
    call_to_file(f'{packdir}/01_uname.txt', 'uname -a')
    call_to_file(f'{packdir}/02_lsb_release.txt', 'lsb_release -a')
    call_to_file(f'{packdir}/03_ip_addr.txt', 'ip addr show')
    call_to_file(f'{packdir}/04_ps_faux.txt', 'ps faux')
    call_to_file(f'{packdir}/05_proc_cpuinfo.txt', 'cat /proc/cpuinfo')
    call_to_file(f'{packdir}/06_proc_meminfo.txt', 'cat /proc/meminfo')

    print('*** Gathering disk information')
    call_to_file(f'{packdir}/10_df.txt', 'df --si')

    print('*** Gathering ONA configuration')
    call_to_file(f'{packdir}/20_config.txt', 'cat /opt/obsrvbl-ona/config')
    call_to_file(f'{packdir}/21_config_auto.txt', 'cat /opt/obsrvbl-ona/config.auto')
    call_to_file(f'{packdir}/22_config_local.txt', 'cat /opt/obsrvbl-ona/config.local')

    print('*** Gathering ONA logs')
    call_to_file(f'{packdir}/30_ona_log_size.txt', 'ls --recursive -l --si /opt/obsrvbl-ona/logs')
    call_to_file(f'{packdir}/31_ona_log_content.txt', 'head -n-0 /opt/obsrvbl-ona/logs/ona_service/*.log')

    print('*** Testing Cloud Connectivity')
    call_to_file(f'{packdir}/40_ext_connectivity.txt', 'curl -o- -D- https://sensor.ext.obsrvbl.com/')
    call_to_file(f'{packdir}/41_obsrvbl_connectivity.txt', 'curl -o- -D- https://sensor.obsrvbl.obsrvbl.com/')
    call_to_file(f'{packdir}/42_eu_connectivity.txt', 'curl -o- -D- https://sensor.eu-prod.obsrvbl.com/')
    call_to_file(f'{packdir}/43_anz_connectivity.txt', 'curl -o- -D- https://sensor.anz-prod.obsrvbl.com/')

    print('*** Gathering iptables configuration')
    call_to_file(f'{packdir}/50_iptables.txt', 'sudo -S iptables -L')

    print(f'*** Running tcpdump for 1,000 packets or {COMMAND_TIMEOUT} seconds')
    call_to_file(f'{packdir}/60_tcpdump.txt', f'sudo -S tcpdump -w {packdir}/60_tcpdump.pcap -c 1000 udp')

    print('*** Creating archive for support')
    call_to_file(f'{packdir}.txt', f'tar cvzf {packdir}.tar.gz {packdir}/*')

    print()
    print()
    print(f'Archive: {packdir}.tar.gz has been created, please include this in support requests')
    print()
    print()


if __name__ == '__main__':
    main()
