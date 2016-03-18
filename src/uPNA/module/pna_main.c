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

/* main PNA initialization (where the kernel module starts) */
/* functions: pna_init, pna_cleanup, pna_hook */

#include <stdio.h>
#include <string.h>
#include <sys/socket.h>
#include <sys/time.h>

#define __FAVOR_BSD
#include <netinet/in.h>
#include <netinet/if_ether.h>
#include <netinet/ip.h>
#include <netinet/tcp.h>
#include <netinet/udp.h>
#include <netinet/ip_icmp.h>

#include "pna.h"

static void pna_perflog(char *pkt, int dir);
static int pna_localize(struct pna_flowkey *key, int *direction);
static int pna_done(const unsigned char *pkt);
int pna_init(void);
void pna_cleanup(void);

typedef unsigned long pna_stat_uword;

// not all systems define all IP protocols
#ifndef IPPROTO_OSPFIGP
# define IPPROTO_OSPFIGP 89
#endif

#ifndef IPPROTO_IGRP
# define IPPROTO_IGRP 88
#endif

// not all hosts have sctp structs, make a simple one for our needs
struct pna_sctpcommonhdr {
	unsigned short src_port;
	unsigned short dst_port;
	unsigned long verification_tag;
	unsigned long checksum;
};

// pna wants a basic understanding of GRE tunnels to decapsulate them
struct pna_grehdr {
	unsigned char checksum_present : 1;
	unsigned char routing_present : 1;
	unsigned char key_present : 1;
	unsigned char sequence_present : 1;
	unsigned char strict_route : 1;
	unsigned char recur : 3;
	unsigned char flags : 5;
	unsigned char version : 3;
	unsigned short protocol;
};

#define eth_hdr(pkt) (struct ether_header *)(pkt)
#define ip_hdr(pkt) (struct ip *)(pkt)
#define gre_hdr(pkt) (struct pna_grehdr *)(pkt)
#define tcp_hdr(pkt) (struct tcphdr *)(pkt)
#define udp_hdr(pkt) (struct udphdr *)(pkt)
#define sctp_hdr(pkt) (struct pna_sctpcommonhdr *)(pkt)
#define icmp_hdr(pkt) (struct icmp *)(pkt)

// maximum number of protocol encapsulations (e.g., VLAN, GRE)
#define PNA_MAX_CHECKS 8

/* define a fragment table for reconstruction */
#define PNA_MAXFRAGS 512
struct pna_frag {
	unsigned long fingerprint;
	unsigned short src_port;
	unsigned short dst_port;
};
static struct pna_frag pna_frag_table[PNA_MAXFRAGS];
static int pna_frag_next_idx = 0;
static int pna_frag_packets_missed = 0;
static int pna_frag_bytes_missed = 0;

#define GOLDEN_RATIO_PRIME_32  0x9e370001UL

unsigned int hash_32(unsigned int val, unsigned int bits)
{
	unsigned int hash = val * GOLDEN_RATIO_PRIME_32;
	return hash >> (32 - bits);
}

/* handle IP fragmented packets */
unsigned long pna_frag_hash(struct ip *iphdr)
{
	unsigned long hash = 0;

	/* note: don't care about byte ordering here since we're hashing */
	hash ^= hash_32(iphdr->ip_src.s_addr, 32);
	hash ^= hash_32(iphdr->ip_dst.s_addr, 32);
	hash ^= (hash_32(iphdr->ip_p, 16) << 16);
	hash ^= hash_32(iphdr->ip_id, 16);
	return hash;
}

struct pna_frag *pna_get_frag(struct ip *iphdr)
{
	int i;
	struct pna_frag *entry;
	unsigned long fingerprint = pna_frag_hash(iphdr);

	for (i = 0; i < PNA_MAXFRAGS; i++) {
		entry = &pna_frag_table[i];
		if (fingerprint == entry->fingerprint)
			return entry;
	}

	return NULL;
}

void pna_set_frag(struct ip *iphdr,
		  unsigned short src_port, unsigned short dst_port)
{
	/* this is in the handler, so it is serial (for now) */
	struct pna_frag *entry;

	/* verify fragment doesn't already exist */
	entry = pna_get_frag(iphdr);
	if (entry)
		return;

	/* grab the entry to update */
	entry = &pna_frag_table[pna_frag_next_idx];
	/* increment to next index to use */
	pna_frag_next_idx = (pna_frag_next_idx + 1) % PNA_MAXFRAGS;
	/* update the entry */
	entry->fingerprint = pna_frag_hash(iphdr);
	entry->src_port = src_port;
	entry->dst_port = dst_port;
}

/* general non-kernel hash function for double hashing */
unsigned int pna_hash(unsigned int key, int bits)
{
	unsigned int hash = key;

	/* lets take the highest bits */
	hash = key >> (sizeof(unsigned int) - bits);

	/* divide by 2 and make it odd */
	hash = (hash >> 1) | 0x01;

	return hash;
}

void pna_session_swap(struct pna_flowkey *key)
{
	unsigned int temp;

	temp = key->local_ip;
	key->local_ip = key->remote_ip;
	key->remote_ip = temp;

	temp = key->local_port;
	key->local_port = key->remote_port;
	key->remote_port = temp;

	temp = key->local_domain;
	key->local_domain = key->remote_domain;
	key->remote_domain = temp;
}

/**
 * Receive Packet Hook (and helpers)
 */
/* make sure the local and remote values are correct in the key */
static int pna_localize(struct pna_flowkey *key, int *direction)
{
	key->local_domain = pna_dtrie_lookup(key->local_ip);
	key->remote_domain = pna_dtrie_lookup(key->remote_ip);

	/* the lowest domain ID is treated as local */
	if (key->local_domain < key->remote_domain) {
		/* local ip is local */
		*direction = PNA_DIR_OUTBOUND;
		return 1;
	} else if (key->local_domain > key->remote_domain) {
		/* remote ip is smaller, swap! */
		*direction = PNA_DIR_INBOUND;
		pna_session_swap(key);
		return 1;
	} else {
		/* neither of these are local, weird and drop */
		if (key->local_domain == MAX_DOMAIN)
			return 0;
		/* local and remote are in same domain, tie break */
		/* (assume IPs are different) */
		if (key->local_ip < key->remote_ip) {
			/* local IP is smaller */
			*direction = PNA_DIR_OUTBOUND;
			return 1;
		} else {
			/* remote IP is smaller, swap */
			*direction = PNA_DIR_INBOUND;
			pna_session_swap(key);
			return 1;
		}
	}
	return 0;
}

/* free all te resources we've used */
static int pna_done(const unsigned char *pkt)
{
	return NET_RX_DROP;
}

/* handle the understanding of IP protocols */
int ip_hook(
	struct pna_flowkey *key, unsigned int pkt_len, const unsigned char *pkt,
	struct ip *iphdr, unsigned short *flags)
{
	struct tcphdr *tcphdr;
	struct udphdr *udphdr;
	struct pna_sctpcommonhdr *sctphdr;
	struct icmp *icmphdr;
	struct pna_frag *entry;

	unsigned short src_port, dst_port, frag_off, offset;

	// check if there are fragments
	frag_off = ntohs(iphdr->ip_off);
	offset = frag_off & IP_OFFMASK;

	switch (key->l4_protocol) {
	case IPPROTO_TCP:
		if (offset != 0) {
			printf("ipproto_tcp, offset: %d\n", offset);
			return pna_done(pkt);
		}
		tcphdr = tcp_hdr(pkt);
		src_port = ntohs(tcphdr->th_sport);
		dst_port = ntohs(tcphdr->th_dport);
		*flags = tcphdr->th_flags;
		break;
	case IPPROTO_UDP:
		/* this is an IP fragmented UDP packet */
		if (offset != 0) {
			/* offset is set, get the appropriate entry */
			entry = pna_get_frag(iphdr);
			/* no entry means we can't record - arrived out of order */
			if (!entry) {
				pna_frag_packets_missed += 1;
				pna_frag_bytes_missed += pkt_len + ETH_OVERHEAD;
				return pna_done(pkt);
			}
			src_port = entry->src_port;
			dst_port = entry->dst_port;
		} else {
			/* no offset */
			udphdr = udp_hdr(pkt);
			src_port = ntohs(udphdr->uh_sport);
			dst_port = ntohs(udphdr->uh_dport);
			/* there will be fragments, add to table */
			if (frag_off & IP_MF)
				pna_set_frag(iphdr, src_port, dst_port);
		}
		break;
	case IPPROTO_SCTP:
		/* this is an SCTP packet, extract ports */
		if (offset != 0) {
			printf("ipproto_sctp, offset: %d\n", offset);
			return pna_done(pkt);
		}
		sctphdr = sctp_hdr(pkt);
		src_port = ntohs(sctphdr->src_port);
		dst_port = ntohs(sctphdr->dst_port);
		break;
	case IPPROTO_ICMP:
		/* this is designed to mimic the NetFlow encoding for ICMP */
		// - src port is 0
		// - dst port is type and code (icmp_type*256 + icmp_code)
		icmphdr = icmp_hdr(pkt);
		src_port = 0;
		dst_port = (icmphdr->icmp_type << 8) + icmphdr->icmp_code;
		break;
	default:
		printf("unknown ipproto: %d\n", key->l4_protocol);
	case IPPROTO_OSPFIGP:  // don't care about OSPF
	case IPPROTO_IGRP:  // no routing protocols
	case IPPROTO_PIM:  // no PIM
	case 253: case 254:  // IANA reserved for experimentation and testing
		return pna_done(pkt);
	}

	// now put the ports in the key
	key->local_port = src_port;
	key->remote_port = dst_port;

	return 0;
}

/* handle the understanding of ethernet */
int ether_hook(
	struct pna_flowkey *key, unsigned int pkt_remains,
	const unsigned char *pkt, unsigned short *flags)
{
	int ret;
	unsigned int pad;
	struct ip *iphdr;
	struct pna_grehdr *grehdr;

	switch (key->l3_protocol) {
	case ETHERTYPE_IP:
		// not enough to process
		if (pkt_remains < sizeof(struct ip)) {
			printf("insufficient data remains\n");
			return pna_done(pkt);
		}
		// this is a supported type, continue
		iphdr = ip_hdr(pkt);
		// assume for now that src is local
		key->l4_protocol = iphdr->ip_p;
		key->local_ip = ntohl(iphdr->ip_src.s_addr);
		key->remote_ip = ntohl(iphdr->ip_dst.s_addr);

		// bump the pkt pointer for ip
		pkt = pkt + sizeof(struct ip);
		pkt_remains -= sizeof(struct ip);

		// GRE: It's not who you are but what you do that defines you.
		// dis-encapsulate GRE
		if (key->l4_protocol == IPPROTO_GRE) {
			grehdr = gre_hdr(pkt);
			if (grehdr->routing_present) {
				// cannot handle routing information in packet
				return pna_done(pkt);
			}
			pad = 0;  // base header
			// we bailed on routing_present, but checksum is okay and
			// implies the offset field exists, account for it
			pad += (grehdr->checksum_present ? 4 : 0);
			pad += (grehdr->key_present ? 4 : 0);
			pad += (grehdr->sequence_present ? 4 : 0);
			// update to the encapsulated protocol
			key->l3_protocol = ntohs(grehdr->protocol);
			pkt = pkt + sizeof(struct pna_grehdr) + pad;
			pkt_remains -= (sizeof(struct pna_grehdr) + pad);
			return ether_hook(key, pkt_remains, pkt, flags);
		}

		// otherwise we hook onto IP layer
		ret = ip_hook(key, pkt_remains, pkt, iphdr, flags);
		if (ret != 0) {
			return pna_done(pkt);
		}
		break;
	default:
		return pna_done(pkt);
	}

	return 0;
}

/* per-packet hook that begins pna processing */
int pna_hook(
	unsigned int pkt_len, const struct timeval tv, const unsigned char *pkt)
{
	struct pna_flowkey key;
	struct ether_header *ethhdr;
	int ret, direction;
	int check_depth;
	unsigned short flags = 0;
	unsigned int pkt_remains = pkt_len;

	/* make sure the key is all zeros before we start */
	memset(&key, 0, sizeof(key));

	/* let's decode the pkt (assume it's ethernet!) */
	ethhdr = eth_hdr(pkt);
	key.l3_protocol = ntohs(ethhdr->ether_type);

	/* we don't care about VLAN tag(s)s - there may be multiple level */
	check_depth = 0;  // limit the number of VLAN encapsulations
	while (key.l3_protocol == ETHERTYPE_VLAN && check_depth < PNA_MAX_CHECKS) {
		check_depth += 1;
		// bump packet forward 4 bytes for 1 VLAN header
		pkt += 4;
		pkt_remains -= 4;
		// recast the ethhdr and extract the l3_protocol
		// XXX: this breaks the mac addresses, but we don't use them
		ethhdr = eth_hdr(pkt);
		key.l3_protocol = ntohs(ethhdr->ether_type);
	}
	if (check_depth == PNA_MAX_CHECKS) {
		// we never got to the actual packet data
		return pna_done(pkt);
	}

	// bump the pkt pointer for ethernet
	pkt = sizeof(struct ether_header) + pkt;
	pkt_remains -= sizeof(struct ether_header);
	ret = ether_hook(&key, pkt_remains, pkt, &flags);
	if (ret != 0) {
		return pna_done(pkt);
	}

	/* entire key should now be filled in and we have a flow, localize it */
	if (!pna_localize(&key, &direction))
		/* couldn't localize the IP (neither source nor dest in prefix) */
		return pna_done(pkt);

	/* hook actions here */

	/* insert into flow table */
	if (pna_flowmon == true) {
		ret = flowmon_hook(&key, direction, flags, pkt, pkt_len, tv);
		if (ret < 0)
			/* failed to insert -- cleanup */
			return pna_done(pkt);

		/* run real-time hooks */
		if (pna_rtmon == true)
			rtmon_hook(&key, direction, pkt, pkt_len, tv, ret);
	}

	/* free our pkt */
	return pna_done(pkt);
}


/*
 * Module oriented code
 */
/* Initialization hook */
int pna_init(void)
{
	int i;
	int ret = 0;

	/* set up the flow table(s) */
	if ((ret = flowmon_init()) < 0)
		return ret;
	//init the domain mappings must be called after flowmon_init because of initialization of PNA proc entry
	pna_dtrie_init();

	if (rtmon_init() < 0) {
		pna_cleanup();
		return -1;
	}

	/* everything is set up, register the packet hook */
	pna_info("pna: capturing is available\n");

	return ret;
}

/* Destruction hook */
void pna_cleanup(void)
{
	rtmon_release();
	flowmon_cleanup();
	pna_info("pna: module is inactive\n");
}
