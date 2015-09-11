/**
 * Copyright 2011 Washington University in St Louis
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *     http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */
#ifndef __PNA_H
#define __PNA_H

#include <stdio.h>
#include <pthread.h>
#include <sys/time.h>

#define true  1
#define false 0

#define pna_err     printf
#define pna_warning printf
#define pna_info    printf

#define NET_RX_DROP (-1)

/* /proc directory PNA tables will be stored in */
#define PNA_PROCDIR  "pna"

/* name format of PNA table files */
#define PNA_PROCFILE "table%d"
#define PNA_MAX_STR  16

/* a table must have at least PNA_LAG_TIME seconds before dumping */
#define PNA_LAG_TIME 2

/* time interval to call real-time monitor "clean" function (milliseconds) */
#define RTMON_CLEAN_INTERVAL (10 * MSEC_PER_SEC)

/* various constants */
#define PNA_DIRECTIONS 2        /* out and in */
#define PNA_DIR_OUTBOUND 0
#define PNA_DIR_INBOUND  1
#define PNA_PROTOCOLS 2         /* tcp and udp */
#define PNA_PROTO_TCP 0
#define PNA_PROTO_UDP 1

#define MAX_DOMAIN 0xFFFF

/* log file format structures */
#define PNA_LOG_MAGIC0   'P'
#define PNA_LOG_MAGIC1   'N'
#define PNA_LOG_MAGIC2   'A'
#define PNA_LOG_VERSION  2
struct pna_log_hdr {
	unsigned char magic[3];
	unsigned char version;
	unsigned int start_time;
	unsigned int end_time;
	unsigned int size;
};

struct pna_log_entry {
	unsigned int local_ip;                  /* 4 */
	unsigned int remote_ip;                 /* 4 */
	unsigned short local_port;              /* 2 */
	unsigned short remote_port;             /* 2 */
	unsigned short local_domain;            /* 2 */
	unsigned short remote_domain;           /* 2 */
	unsigned int packets[PNA_DIRECTIONS];   /* 8 */
	unsigned int bytes[PNA_DIRECTIONS];     /* 8 */
	unsigned short flags[PNA_DIRECTIONS];   /* 4 */
	unsigned int first_tstamp;              /* 4 */
	unsigned int last_tstamp;               /* 4 */
	unsigned char l4_protocol;              /* 1 */
	unsigned char first_dir;                /* 1 */
	char pad[2];                            /* 2 */
};                                              /* = 48 */

/* definition of a flow for PNA */
struct pna_flowkey {
	unsigned short l3_protocol;
	unsigned char l4_protocol;
	unsigned int local_ip;
	unsigned int remote_ip;
	unsigned short local_port;
	unsigned short remote_port;
	unsigned short local_domain;
	unsigned short remote_domain;
};

/* flow data we're interested in off-line */
struct pna_flow_data {
	unsigned int bytes[PNA_DIRECTIONS];
	unsigned int packets[PNA_DIRECTIONS];
	unsigned short flags[PNA_DIRECTIONS];
	unsigned int timestamp;
	unsigned int first_tstamp;
	unsigned int last_tstamp;
	unsigned int first_dir;
};

struct flow_entry {
	struct pna_flowkey key;
	struct pna_flow_data data;
};

/* settings/structures for storing <src,dst,port> entries */
#define PNA_FLOW_ENTRIES(bits) (1 << (bits))
#define PNA_SZ_FLOW_ENTRIES(bits) (PNA_FLOW_ENTRIES((bits)) * sizeof(struct flow_entry))

/* Account for Ethernet overheads (stripped by sk_buff) */
#define ETH_INTERFRAME_GAP 12   /* 9.6ms @ 1Gbps */
#define ETH_PREAMBLE       8    /* preamble + start-of-frame delimiter */
#define ETH_HLEN           14
#define ETH_FCS_LEN        4
#define ETH_OVERHEAD       (ETH_INTERFRAME_GAP + ETH_PREAMBLE + ETH_HLEN + ETH_FCS_LEN)

/* configuration settings */
extern unsigned int pna_tables;
extern unsigned int pna_bits;
extern char pna_debug;
extern char pna_perfmon;
extern char pna_flowmon;
extern char pna_rtmon;
extern int verbose;

/* number of attempts to insert before giving up */
#define PNA_TABLE_TRIES 32

struct flowtab_info {
	void *table_base;
	char table_name[PNA_MAX_STR];
	struct flow_entry *flowtab;

    pthread_mutex_t read_mutex;

	int table_dirty;
    int table_id;
	unsigned int first_sec;
	int smp_id;
	unsigned int nflows;
	unsigned int nflows_missed;
	unsigned int probes[PNA_TABLE_TRIES];
};

/* some prototypes */
unsigned int pna_hash(unsigned int key, int bits);

int pna_init(void);
void pna_cleanup(void);
int pna_hook(unsigned int pkt_len, const struct timeval tv,
                     const unsigned char *pkt);

int flowmon_hook(struct pna_flowkey *key, int direction, unsigned short flags,
                 const unsigned char *pkt, unsigned int pkt_len,
                 const struct timeval tv);
int flowmon_init(void);
void flowmon_cleanup(void);

unsigned int pna_dtrie_lookup(unsigned int ip);
int pna_dtrie_init(void);
int pna_dtrie_deinit(void);

int rtmon_init(void);
int rtmon_hook(struct pna_flowkey *key, int direction, const unsigned char *pkt,
               unsigned int pkt_len, const struct timeval tv,
               unsigned long data);
void rtmon_release(void);

#endif                          /* __PNA_H */
