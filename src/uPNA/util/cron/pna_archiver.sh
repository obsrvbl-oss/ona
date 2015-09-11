#!/bin/bash
# Given a collection of compressed 10 minute archives,
# transfer them to a archival host

ARCHIVE_DIR="/usr/local/pna/archive"
PERIODIC_DIR="$ARCHIVE_DIR/daily"

SSH_OPTIONS="-i /home/mjschultz/.ssh/pna_rsa"
REMOTE_LOCATION="mjschultz@10.0.16.4:/var/pna/archive"

# Remove one day old periodic files 
ARCHIVES=`find $PERIODIC_DIR/ -ctime +0`
for archive in $ARCHIVES ; do
    # If it isn't a file skip it
    if [ ! -f $archive ] ; then
        continue
    fi

    # Attempt to copy to REMOTE_LOCATION
    scp $SSH_OPTIONS $archive $REMOTE_LOCATION

    # If successful, remove the local copy
    if [ $? -eq 0 ] ; then
        rm -f $archive
    fi
done
