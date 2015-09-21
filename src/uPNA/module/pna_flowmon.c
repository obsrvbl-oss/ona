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

/* handle insertion into flow table */
/* functions: flowmon_init, flowmon_cleanup, flowmon_hook */

#include <stdlib.h>
#include <string.h>
#include <errno.h>
#include <pthread.h>
#include <sys/time.h>
#include <netinet/ip.h>

#include "pna.h"

#define LOG_FILE_FORMAT  "%s/pna-%%Y%%m%%d%%H%%M%%S-%s.t%d.log"
#define MAX_STR          1024

/* functions for flow monitoring */
static struct flowtab_info *flowtab_get(struct timeval tv);
static int flowkey_match(struct pna_flowkey *key_a,
			 struct pna_flowkey *key_b);
int flowmon_init(void);
void flowmon_cleanup(void);
static void flowtab_clean(struct flowtab_info *info);
void dump_table(void *table_base, char *out_file, unsigned int size);


unsigned int hash_32(unsigned int, unsigned int);

/* pointer to information about the flow tables */
static struct flowtab_info *flowtab_info;
extern char *log_dir;
extern char *pcap_source_name;

/* simple null key */
static struct pna_flowkey null_key = {
	.l3_protocol	= 0,
	.l4_protocol	= 0,
	.local_ip	= 0,
	.remote_ip	= 0,
	.local_port	= 0,
	.remote_port	= 0,
};

static unsigned int flowtab_idx = 0;

static void flowtab_dump(struct flowtab_info *info)
{
	struct timeval start;
    struct tm *start_tm;
    char out_base[MAX_STR], out_file[MAX_STR];

    /* determine where to dump the file
     * - for backward compat we use current time to decide filename
     */
	gettimeofday(&start, NULL);
	start.tv_sec -= 1;  // drop 1 second since we stop at the rollover
    start_tm = gmtime((time_t*)&start);
	snprintf(out_base, MAX_STR, LOG_FILE_FORMAT, log_dir,
             pcap_source_name, info->table_id);
    strftime(out_file, MAX_STR, out_base, start_tm);

    printf("dumping to: '%s'\n", out_file);

    /* actually dump the table */
    dump_table(info->table_base, out_file, PNA_SZ_FLOW_ENTRIES(pna_bits));

    /* dump a table to the file system and unlock it once complete */
    flowtab_clean(info);
    pthread_mutex_unlock(&info->read_mutex);
}

/* clear out all the mflowtable data from a flowtab entry */
static void flowtab_clean(struct flowtab_info *info)
{
    memset(info->table_base, 0, PNA_SZ_FLOW_ENTRIES(pna_bits));
    info->table_dirty = 0;
    info->first_sec = 0;
    info->smp_id = 0;
    info->nflows = 0;
    info->nflows_missed = 0;
}

/* determine which flow table to use */
static struct flowtab_info *flowtab_get(struct timeval tv)
{
    static unsigned int lock_misses = 0;
	int i;
	char ten_bound, too_old;
	struct flowtab_info *info;

	/* figure out which flow table to use */
    /* assume we're pointing to the right one for now */
	info = &flowtab_info[flowtab_idx];

	/* if the table is dirty and has some data, try to dump it on 10
	 * seconds boundaries. If we somehow missed a 10 seconds boundary, dump
	 * it if it's too old. */
	ten_bound = (tv.tv_sec % 10 == 0 && tv.tv_sec != info->first_sec);
	too_old = (tv.tv_sec - info->first_sec >= 10);
    if (info->table_dirty != 0 && (ten_bound || too_old)) {
        /* spin off thread to handle this */
        flowtab_dump(info);
        /* move to next table */
		flowtab_idx = (flowtab_idx + 1) % pna_tables;
    	info = &flowtab_info[flowtab_idx];
    }
    else if (info->table_dirty) {
        /* table is dirty but still active, everything is awesome */
        return info;
    }

	/* check if table is locked */
	i = 0;
	while (pthread_mutex_trylock(&info->read_mutex) && i < pna_tables) {
		/* if it is locked try the next table ... */
		flowtab_idx = (flowtab_idx + 1) % pna_tables;
		info = &flowtab_info[flowtab_idx];
		/* don't try a table more than once */
		i++;
	}
	if (i == pna_tables) {
        	lock_misses += 1;
		if (lock_misses >= 1000) {
			pna_warning("pna: all tables are locked, missed %d packets\n", lock_misses);
			lock_misses = 0;
		}
		return NULL;
	}

	/* make sure this table is marked as dirty */
	// XXX: table_dirty should probably be atomic_t
	if (info->table_dirty == 0) {
		info->first_sec = tv.tv_sec;
		info->table_dirty = 1;
		info->smp_id = 0;
	}

	return info;
}

/* check if flow keys match */
static inline int flowkey_match(struct pna_flowkey *key_a,
				struct pna_flowkey *key_b)
{
	/* exploit the fact that keys are 16 bytes = 128 bits wide */
	unsigned long long a_hi, a_lo, b_hi, b_lo;

	a_hi = *(unsigned long long *)key_a;
	a_lo = *((unsigned long long *)key_a + 1);
	b_hi = *(unsigned long long *)key_b;
	b_lo = *((unsigned long long *)key_b + 1);
	return (a_hi == b_hi) && (a_lo == b_lo);
}

/* Insert/Update this flow */
int flowmon_hook(struct pna_flowkey *key, int direction, unsigned short flags,
                 const unsigned char *pkt, unsigned int pkt_len,
                 struct timeval tv)
{
	struct flow_entry *flow;
	struct flowtab_info *info;
	unsigned int i, hash_0, hash;

	if (NULL == (info = flowtab_get(tv)))
		return -1;

	/* hash */
	hash = key->local_ip ^ key->remote_ip;
	hash ^= ((key->remote_port << 16) | key->local_port);
	hash_0 = hash_32(hash, pna_bits);

	/* loop through table until we find right entry */
	for (i = 0; i < PNA_TABLE_TRIES; i++) {
		/* quadratic probe for next entry */
		hash = (hash_0 + ((i + i * i) >> 1)) & (PNA_FLOW_ENTRIES(pna_bits) - 1);

		/* increment the number of probe tries for the table */
		info->probes[i]++;

		/* strt testing the waters */
		flow = &(info->flowtab[hash]);

		/* check for match -- update flow entry */
		if (flowkey_match(&flow->key, key)) {
			flow->data.bytes[direction] += pkt_len + ETH_OVERHEAD;
			flow->data.packets[direction] += 1;
			flow->data.flags[direction] |= flags;
			flow->data.last_tstamp = tv.tv_sec;
			return 0;
		}

		/* check for free spot -- insert flow entry */
		if (flowkey_match(&flow->key, &null_key)) {
			/* copy over the flow key for this entry */
			memmove(&flow->key, key, sizeof(*key));

			/* port specific information */
			flow->data.bytes[direction] += pkt_len + ETH_OVERHEAD;
			flow->data.packets[direction]++;
			flow->data.flags[direction] |= flags;
			flow->data.first_tstamp = tv.tv_sec;
			flow->data.last_tstamp = tv.tv_sec;
			flow->data.first_dir = direction;

			info->nflows++;
			return 1;
		}
	}

	info->nflows_missed++;
	return -1;
}

/* initialization routine for flow monitoring */
int flowmon_init(void)
{
	int i;
	long unsigned int pna_table_size;
	long unsigned int total_mem;
	struct flowtab_info *info;
	char table_str[PNA_MAX_STR];

	total_mem = 0;

	/* make memory for table meta-information */
	flowtab_info = (struct flowtab_info*)
		       malloc(pna_tables * sizeof(struct flowtab_info));
	total_mem += pna_tables * sizeof(struct flowtab_info);
	if (!flowtab_info) {
		pna_err("insufficient memory for flowtab_info\n");
		flowmon_cleanup();
		return -ENOMEM;
	}
	memset(flowtab_info, 0, pna_tables * sizeof(struct flowtab_info));

	/* configure each table for use */
	pna_table_size = PNA_SZ_FLOW_ENTRIES(pna_bits);
	for (i = 0; i < pna_tables; i++) {
		info = &flowtab_info[i];
		info->table_base = malloc(pna_table_size);
		total_mem += pna_table_size;
		if (!info->table_base) {
			pna_err("insufficient memory for %d/%d tables (%lu bytes)\n",
				i, pna_tables, (pna_tables * pna_table_size));
			flowmon_cleanup();
			return -ENOMEM;
		}
		/* set up table pointers */
		info->flowtab = info->table_base;
        info->table_id = i;
		flowtab_clean(info);

		/* initialize the read_mutex */
		pthread_mutex_init(&info->read_mutex, NULL);
	}

	if (verbose) {
		printf("flowmon memory: %lu kibibytes (%d bits)\n",
		       total_mem / 1024, pna_bits);
	}

	return 0;
}

/* clean up routine for flow monitoring */
void flowmon_cleanup(void)
{
	int i;

	/* destroy each table file we created */
	for (i = pna_tables - 1; i >= 0; i--) {
		if (flowtab_info[i].table_dirty != 0) {
			flowtab_dump(&flowtab_info[i]);
		}
        pthread_mutex_destroy(&flowtab_info[i].read_mutex);
		if (flowtab_info[i].table_base != NULL)
			free(flowtab_info[i].table_base);
	}

	/* free up table meta-information struct */
	free(flowtab_info);
}
