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

/* real-time hook system */
/* @functions: rtmon_init, rtmon_hook, rtmon_clean, rtmon_release */

#include "pna.h"

/* in-file prototypes */
static void rtmon_clean(unsigned long data);

/*
 * @init: initialization routine for a hook
 * @hook: hook function called on every packet
 * @clean: clean function called periodically to reset tables/counters
 * @release: take-down function for table data and cleanup
 */
struct pna_rtmon {
	int (*init)(void);
	int (*hook)(struct pna_flowkey *, int, const unsigned char *,
                unsigned int, const struct timeval, unsigned long *);
	void (*clean)(void);
	void (*release)(void);
};

/* a NULL .hook signals the end-of-list */
struct pna_rtmon monitors[] = {
	/* NULL hook entry is end of list delimited */
	{ .init = NULL, .hook = NULL, .clean = NULL, .release = NULL }
};

/* reset each rtmon for next round of processing -- once per */
static void rtmon_clean(unsigned long data)
{
	struct pna_rtmon *monitor;

	for (monitor = &monitors[0]; monitor->hook != NULL; monitor++)
		monitor->clean();
}

/* hook from main on packet to start real-time monitoring */
int rtmon_hook(struct pna_flowkey *key, int direction, const unsigned char *pkt,
               unsigned int pkt_len, const struct timeval tv,
               unsigned long data)
{
	int ret = 0;

	struct pna_rtmon *monitor;

	for (monitor = &monitors[0]; monitor->hook != NULL; monitor++)
		ret = monitor->hook(key, direction, pkt, pkt_len, tv, &data);

	return ret;
}

/* initialize all the resources needed for each rtmon */
int rtmon_init(void)
{
	int ret = 0;

	struct pna_rtmon *monitor;

	for (monitor = &monitors[0]; monitor->hook != NULL; monitor++)
		ret += monitor->init();

	return ret;
}

/* release the resources each rtmon is using */
void rtmon_release(void)
{
	struct pna_rtmon *monitor;

	/* clean up each of the monitors */
	for (monitor = &monitors[0]; monitor->hook != NULL; monitor++)
		monitor->release();
    printf("release rtmon\n");
}
