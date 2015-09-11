# Copyright 2011 Washington University in St Louis
# 
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
# 
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

# userspace module files

MAIN_PROG := pna
COMMON_OBJS := pna_main.o pna_flowmon.o pna_domain_trie.o
COMMON_OBJS += pna_rtmon.o util.o dump_table.o

LDFLAGS := $(LDFLAGS) -lpthread
CC := $(CROSS_COMPILE)gcc

# we want to build libpcap into the image
ifneq ($(CROSS_LIBS),)
	COMMON_OBJS += $(CROSS_LIBS)/libpcap.a
else
	LDFLAGS += -lpcap
endif

all: ${MAIN_PROG}

${MAIN_PROG}: ${MAIN_PROG}.o ${COMMON_OBJS}
	$(CC) $(CFLAGS) $< ${COMMON_OBJS} $(LDFLAGS) -o $@

%.o: %.c
	$(CC) $(CFLAGS) -c $< -o $@

clean:
	rm -f *.o ${MAIN_PROG}
