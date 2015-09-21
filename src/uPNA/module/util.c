#define _GNU_SOURCE
#include <sched.h>
#include <sys/types.h>
#include <time.h>
#include <pcap.h>
#include <netinet/in.h>
#include <netinet/if_ether.h>

#include "util.h"

/**************************************
 * The time difference in millisecond *
 **************************************/
double delta_time (struct timeval *now, struct timeval *before)
{
    time_t delta_seconds;
    time_t delta_microseconds;

    /* compute delta in second, 1/10's and 1/1000's second units */
    delta_seconds      = now->tv_sec  - before->tv_sec;
    delta_microseconds = now->tv_usec - before->tv_usec;

    if (delta_microseconds < 0) {
        /* manually carry a one from the seconds field */
        delta_microseconds += 1000000;    /* 1e6 */
        --delta_seconds;
    }
    return ((double)(delta_seconds * 1000) + (double)delta_microseconds/1000);
}

void print_stats(int type, void *pd, struct timeval *start, unsigned long long pkts, unsigned long long bytes)
{
    struct pcap_stat pcapStat;
    //pfring_stat pfringStat;

    struct timeval endTime;
    double deltaMillisec;
    static u_int64_t lastPkts = 0, lastBytes = 0;
    static struct timeval lastTime;
    unsigned long long diffPkts, diffBytes;
    unsigned long long recv = 0, drop = 0;


    if (start->tv_sec == 0) {
        gettimeofday(start, NULL);
    }

    gettimeofday(&endTime, NULL);
    deltaMillisec = delta_time(&endTime, start);

    if (type == PCAP && pcap_stats(pd, &pcapStat) >= 0) {
        recv = pcapStat.ps_recv;
        drop = pcapStat.ps_drop;
    }
//    else if (type == PFRING && pfring_stats(pd, &pfringStat) >= 0) {
//        recv = pfringStat.recv;
//        drop = pfringStat.drop;
//    }

    if (recv != 0 || drop != 0) {
        printf("=========================\n");
        printf("Absolute Stats: %llu pkts rcvd, %llu pkts dropped\n", recv, drop);
        printf("%llu pkts [%.1f pkt/sec] - %llu bytes [%.2f Mbit/sec]\n",
                pkts, (pkts*1000.0)/deltaMillisec,
                bytes, (bytes*8.0)/(deltaMillisec*1000));

        if (lastTime.tv_sec > 0) {
            deltaMillisec = delta_time(&endTime, &lastTime);
            diffPkts = pkts - lastPkts;
            diffBytes = bytes - lastBytes;
            printf("=========================\n");
            printf("Interval Stats: %.1f s\n", deltaMillisec/1000);
            printf("%llu pkts [%.2f pkt/sec] - %llu bytes [%.2f Mbit/sec]\n",
                   diffPkts, (diffPkts*1000.0)/deltaMillisec,
                   diffBytes, (diffBytes*8.0)/(deltaMillisec*1000));
        }
    }
    else {
        printf("=========================\n");
        printf("No packets seen in this interval\n");
    }

    lastTime.tv_sec = endTime.tv_sec;
    lastTime.tv_usec = endTime.tv_usec;
    lastPkts = pkts;
    lastBytes = bytes;

    printf("=========================\n");
}
