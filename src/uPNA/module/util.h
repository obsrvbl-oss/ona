#ifndef _UTIL_H_
#define _UTIL_H_

#include <sys/types.h>
#include <time.h>
#include <pcap.h>
//#include "pfring.h"

#define PFRING 34
#define PCAP   67

/* prototypes */
double delta_time (struct timeval *now, struct timeval *before);
void print_stats(int type, void *pd, struct timeval *start, unsigned long long pkts, unsigned long long bytes);
char *etheraddr_string(const u_char *ep, char *buf);
char *_intoa(unsigned int addr, char* buf, u_short bufLen);
char *intoa(unsigned int addr);
int bind2core(u_int core_id);

#endif /* _UTIL_H_ */
