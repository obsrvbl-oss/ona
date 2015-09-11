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

MODULE := module/pna
SERVICE := ./pna-service

all: $(MODULE)

$(MODULE):
	$(MAKE) -C module/

start: $(MODULE)
	sudo $(SERVICE) start "$(PARMS)"

stop:
	sudo $(SERVICE) stop

status:
	sudo $(SERVICE) status

indent:
	find . -name '*.[ch]' | xargs uncrustify -c linux.cfg --no-backup --replace
	find . -name '*~' -delete

clean:
	$(MAKE) -C module clean

tag:
	git tag $(shell cat VERSION)

realclean: clean
	rm -f irq_count.start irq_count.stop
	rm -f verbose-*.log
