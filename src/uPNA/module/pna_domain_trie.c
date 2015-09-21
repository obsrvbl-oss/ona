/**
 * pna_domain_trie.c
 * Code to peform longest prefix match on an IP and return the domain to
 * which it belongs.  All inputs must be in network byte order
 */

#include <string.h>
#include <stdlib.h>
#include <arpa/inet.h>

#include "pna.h"

/* locally used structs */
struct pna_dtrie_entry {
	int isprefix;
	unsigned short domain_id;
	struct pna_dtrie_entry *children[2];
};

struct pna_dtrie_entry *pna_dtrie_head;


int pna_dtrie_add(unsigned int prefix, unsigned int max_bit_pos,
                  unsigned int domain_id);

int pna_dtrie_parse(char *line, int netid)
{
	int ret;
    char *ipstring;
    char *prefix_string;
    char *domain_string;
    unsigned int prefix, mask;

	/* get the IP and prefix */
	ipstring = strtok(line, "/\n");
	prefix_string = strtok(NULL, "/\n");
	if (!ipstring || !prefix_string) {
		printf("bad string: '%s'\n", line);
		return -1;
	}

	/* get the netid, if needed */
	if (netid == -1) {
		domain_string = strtok(NULL, "/\n");
		if (!domain_string) {
			printf("missing netid: '%s'\n", line);
			return -1;
		}
		netid = atoi(domain_string);
	}

	/* convert the mask */
	mask = atoi(prefix_string);
	if (!mask || !netid) {
		printf("bad string %s or %d\n", prefix_string, netid);
		return -1;
	}

	prefix = htonl(inet_addr(ipstring));
	ret = pna_dtrie_add(prefix, mask, netid);
	if (ret != 0) {
		return ret;
	}
	return 0;
}

int pna_dtrie_build(char *networks_file)
{
	int ret;
	char buffer[100];
	FILE *infile;

    infile = fopen(networks_file, "r");
	if (!infile) {
		printf("failed to open %s\n", networks_file);
		return -1;
	}

	while (fgets(buffer, 100, infile)) {
		if (buffer[0] == '#')
			continue;
		if (buffer[0] == '\n')
			continue;
		if (buffer[0] == ' ')
			continue;
		ret = pna_dtrie_parse(buffer, -1);
		if (ret != 0) {
			return ret;
		}
	}

    return 0;
}

struct pna_dtrie_entry *pna_dtrie_entry_alloc(void)
{
	struct pna_dtrie_entry *entry =
		(struct pna_dtrie_entry*)malloc(sizeof(struct pna_dtrie_entry));

	if (!entry)
		return NULL;
	entry->domain_id = MAX_DOMAIN;
	entry->isprefix = 0;
	memset(entry->children, 0, 2 * sizeof(struct pna_domain_entry *));
	return entry;
}

unsigned int pna_dtrie_lookup(unsigned int ip)
{
	unsigned int cur_bit, cur_bit_pos;
	struct pna_dtrie_entry *next_entry;
	struct pna_dtrie_entry *entry = pna_dtrie_head;
	unsigned int curdomain = MAX_DOMAIN;

	//assume network byte order
	cur_bit_pos = 0;
	cur_bit = (ip >> (31 - cur_bit_pos)) & 0x1;
	next_entry = entry->children[cur_bit];
	while (next_entry) {
		entry = next_entry;
		if (entry->isprefix)
			curdomain = entry->domain_id;
		cur_bit_pos++;
		cur_bit = (ip >> (31 - cur_bit_pos)) & 1;
		next_entry = entry->children[cur_bit];
	}
	return curdomain;
}

int pna_dtrie_add(unsigned int prefix, unsigned int max_bit_pos,
		  unsigned int domain_id)
{
	unsigned int mask;
	unsigned int cur_bit_pos;
	unsigned int cur_bit;
	struct pna_dtrie_entry *next;
	struct pna_dtrie_entry *cur = pna_dtrie_head;

	if ( !(0 < max_bit_pos && max_bit_pos <= 32) ) {
		printf("invalid mask: %i\n", max_bit_pos);
		return -1;
	}

	if (verbose) {
		printf("pna_dtrie_add %X/%i (%i)\n", prefix, max_bit_pos, domain_id);
	}

	mask = 0xffffffff - ((1 << (32 - max_bit_pos)) - 1);
	if ( (prefix & mask) != prefix ) {
		prefix = prefix & mask;
		printf("pna_dtrie_add: corrected prefix %X/%i (%i)\n",
		       prefix, max_bit_pos, domain_id);
	}

	cur_bit_pos = 0;
	while (cur_bit_pos < max_bit_pos) {
		cur_bit = (prefix >> (31 - cur_bit_pos)) & 0x1;
		next = cur->children[cur_bit];
		if (!next) {
			cur->children[cur_bit] = next = pna_dtrie_entry_alloc();
			if (!next) {
				printf("Failed to alloc dtrie entry\n");
				return -1;
			}
		}
		cur_bit_pos++;
		cur = next;
	}
	cur->isprefix = 1;
	cur->domain_id = domain_id;
	return 0;
}


int pna_dtrie_rm_node(struct pna_dtrie_entry *entry)
{
	if (!entry)
		return 0;
	pna_dtrie_rm_node(entry->children[0]);
	pna_dtrie_rm_node(entry->children[1]);
	free(entry);
	return 0;
}

int pna_dtrie_deinit(void)
{
	pna_dtrie_rm_node(pna_dtrie_head);
	printf("pna dtrie freed\n");
	return 0;
}

int pna_dtrie_init(void)
{
	pna_dtrie_head = pna_dtrie_entry_alloc();
	if (!pna_dtrie_head) {
		printf("failed to init dtrie head\n");
		return -1;
	}

	return 0;
}
