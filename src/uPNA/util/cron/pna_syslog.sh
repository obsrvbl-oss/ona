#!/bin/sh
# This gets relevant pna performance data from /var/log/messages on the PNA
# host

LOG_DIR="/home/pna/pna/syslogs"

SSH_OPTIONS="-i $BASE/.ssh/pna_rsa"
REMOTE_LOCATION="mjschultz@mcore.arl.wustl.edu:~/syslogs"

mkdir -p $LOG_DIR

# Set output file date
DATE=$(date --date='yesterday' +'%F')

# Date log files will contain
LOG_DATE=$(date --date='yesterday' +'%b %e')

# Log files to search (two most recent covers a day)
LOGS="/var/log/messages.1 /var/log/messages"

# grep string to match
KEYWORDS="pna \(throughput\|table\|\([A-Za-z]\+[0-9]\+ \)\?rx_stats\)"
GREP_STRING="^$LOG_DATE.*$KEYWORDS"

LOG_FILE="$LOG_DIR/messages_$DATE"
sudo grep -h "$GREP_STRING" $LOGS > $LOG_FILE

# Attempt to copy this and any older files to remote host
for log in $LOG_DIR/* ; do
	# If it isn't a file, skip it
	if [ ! -f $log ] ; then
		continue
	fi

	# Attempt to copy to REMOTE_LOCATION
	scp $SSH_OPTIONS $log $REMOTE_LOCATION

    # If successful, remove the file
	if [ $? -eq 0 ] ; then
		rm -f $log
	fi
done
