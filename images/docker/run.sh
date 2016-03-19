#!/bin/bash
# This file will provide default values for the environment, unless explicitly
# overrode by the runtime environment. It also copies in all OBSRVBL_*
# environment variables.
local_config=/opt/obsrvbl-ona/config.local

if [ -z $OBSRVBL_SERVICE_KEY ] ; then
    echo "Missing required OBSRVBL_SERVICE_KEY in environment"
    exit 1
fi

echo "" > $local_config
echo "OBSRVBL_MANAGE_MODE='${OBSRVBL_MANAGE_MODE:-manual}'" >> $local_config
echo "OBSRVBL_NETWORKS='${OBSRVBL_NETWORKS:-10.0.0.0/8 172.16.0.0/12 192.168.0.0/16}'" >> $local_config
echo "OBSRVBL_LOG_WATCHER='${OBSRVBL_LOG_WATCHER:-false}'" >> $local_config
echo "OBSRVBL_SYSLOG_ENABLED='${OBSRVBL_SYSLOG_ENABLED:-true}'" >> $local_config
echo "OBSRVBL_SYSLOG_FACILITY='${OBSRVBL_SYSLOG_FACILITY:-user}'" >> $local_config
echo "OBSRVBL_SYSLOG_SERVER='${OBSRVBL_SYSLOG_SERVER:-127.0.0.1}'" >> $local_config
echo "OBSRVBL_SYSLOG_SERVER_PORT='${OBSRVBL_SYSLOG_SERVER_PORT:-514}'" >> $local_config

for var in ${!OBSRVBL_*} ; do
    # Check if we've already written var to the config
    ret=$(grep $var $local_config)
    if [ ! -z $ret ] ; then
        continue
    fi

    # write the var to the config
    echo "$var='${!var}'" >> $local_config
done

exec /opt/obsrvbl-ona/system/supervisord/ona-supervisord.sh
