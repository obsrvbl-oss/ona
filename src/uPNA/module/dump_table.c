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

#define _GNU_SOURCE
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <string.h>
#include <fcntl.h>
#include <errno.h>
#include <sys/mman.h>
#include <sys/stat.h>
#include <time.h>
#include <sys/time.h>

#include "pna.h"

#define BUF_SIZE         (1 * 1024 * 1024)
#define USECS_PER_SEC    1000000

/* simple null key */
static struct pna_flowkey null_key = {
	.l3_protocol	= 0,
	.l4_protocol	= 0,
	.local_ip	= 0,
	.remote_ip	= 0,
	.local_port	= 0,
	.remote_port	= 0,
};


/* global variables */
char *prog_name;

int flowkey_match(struct pna_flowkey *key_a, struct pna_flowkey *key_b)
{
	return !memcmp(key_a, key_b, sizeof(*key_a));
}

/* flushes a buffer out to the file */
int buf_flush(int out_fd, char *buffer, int buf_idx)
{
	int count;

	while (buf_idx > 0) {
		count = write(out_fd, buffer, buf_idx);
		if (count < 0)
			perror("write");
		buf_idx -= count;
	}

	return buf_idx;
}

/* dumps the in-memory table to a file */
void dump_table(void *table_base, char *out_file, unsigned int file_size)
{
	int fd;
	unsigned int nflows, f_max_entries;
	unsigned int start_time;
	unsigned int offset;
	unsigned int flow_idx;
	struct flow_entry *flow;
	struct flow_entry *flow_table;
	struct pna_log_hdr *log_header;
	struct pna_log_entry *log;
	char buf[BUF_SIZE];
	int buf_idx;

	/* record the current time */
	start_time = time(NULL);

	/* convert into max number of entries */
	f_max_entries = file_size / sizeof(*flow);

	/* open up the output file */
	fd = open(out_file, O_CREAT | O_RDWR);
	if (fd < 0) {
		perror("open out_file");
		return;
	}
	fchmod(fd, S_IRUSR | S_IWUSR | S_IRGRP | S_IWGRP | S_IROTH);
	lseek(fd, sizeof(struct pna_log_hdr), SEEK_SET);

	buf_idx = 0;
	nflows = 0;

	flow_table = (struct flow_entry*)table_base;

	/* now we loop through the tables ... */
	for (flow_idx = 0; flow_idx < f_max_entries; flow_idx++) {
		/* get the first level entry */
		flow = &flow_table[flow_idx];

		/* make sure it is active */
		if (flowkey_match(&flow->key, &null_key))
			continue;

		/* set up monitor buffer */
		log = (struct pna_log_entry*)&buf[buf_idx];
		buf_idx += sizeof(struct pna_log_entry);

		/* copy the flow entry */
		log->local_ip = flow->key.local_ip;
		log->remote_ip = flow->key.remote_ip;
		log->local_port = flow->key.local_port;
		log->remote_port = flow->key.remote_port;
		log->local_domain = flow->key.local_domain;
		log->remote_domain = flow->key.remote_domain;
		log->packets[PNA_DIR_OUTBOUND] =
			flow->data.packets[PNA_DIR_OUTBOUND];
		log->packets[PNA_DIR_INBOUND] =
			flow->data.packets[PNA_DIR_INBOUND];
		log->bytes[PNA_DIR_OUTBOUND] = flow->data.bytes[PNA_DIR_OUTBOUND];
		log->bytes[PNA_DIR_INBOUND] = flow->data.bytes[PNA_DIR_INBOUND];
		log->flags[PNA_DIR_OUTBOUND] = flow->data.flags[PNA_DIR_OUTBOUND];
		log->flags[PNA_DIR_INBOUND] = flow->data.flags[PNA_DIR_INBOUND];
		log->first_tstamp = flow->data.first_tstamp;
		log->last_tstamp = flow->data.last_tstamp;
		log->l4_protocol = flow->key.l4_protocol;
		log->first_dir = flow->data.first_dir;
		log->pad[0] = 0x00;
		log->pad[1] = 0x00;
		nflows++;

		/* check if we can fit another entry */
		if (buf_idx + sizeof(struct pna_log_entry) >= BUF_SIZE)
			/* flush the buffer */
			buf_idx = buf_flush(fd, buf, buf_idx);
	}

	/* make sure we're flushed */
	buf_idx = buf_flush(fd, buf, buf_idx);

	/* display the number of entries we got */
	if (verbose)
		printf("%d flows to '%s'\n", nflows, out_file);

	/* write out header data */
	lseek(fd, 0, SEEK_SET);
	log_header = (struct pna_log_hdr*)&buf[buf_idx];
	log_header->magic[0] = PNA_LOG_MAGIC0;
	log_header->magic[1] = PNA_LOG_MAGIC1;
	log_header->magic[2] = PNA_LOG_MAGIC2;
	log_header->version = PNA_LOG_VERSION;
	log_header->start_time = start_time;
	log_header->end_time = time(NULL);
	log_header->size = nflows * sizeof(struct pna_log_entry);
	write(fd, log_header, sizeof(*log_header));

	close(fd);
}
