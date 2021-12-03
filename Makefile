#  Copyright 2015 Observable Networks
#
#  Licensed under the Apache License, Version 2.0 (the "License");
#  you may not use this file except in compliance with the License.
#  You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
ARCH ?= amd64
VERSION := 5.1.0

SCRIPTS_DIR := src/scripts
uPNA_DIR := src/uPNA
IPFIX_DIR := src/ipfix

OBSRVBL_ROOT := packaging/root/opt/obsrvbl-ona

.PHONY: all
all:
	@echo please specify a target

.PHONY: test
test: test-scripts

.PHONY: test-scripts
test-scripts:
	make -C ${SCRIPTS_DIR} test

.PHONY: coverage
coverage: coverage-scripts

.PHONY: coverage-scripts
coverage-scripts:
	make -C ${SCRIPTS_DIR} coverage

.PHONY: build
build:
	make -C ${uPNA_DIR}

.PHONY: copy
copy:
	make -C ${SCRIPTS_DIR} vendor clean
	mkdir -p ${OBSRVBL_ROOT}/
	echo ${VERSION} > ${OBSRVBL_ROOT}/version
	mkdir -p ${OBSRVBL_ROOT}/pna/user/
	cp ${uPNA_DIR}/module/pna ${OBSRVBL_ROOT}/pna/user/pna
	mkdir -p ${OBSRVBL_ROOT}/ipfix/
	cp -r ${IPFIX_DIR}/* ${OBSRVBL_ROOT}/ipfix/
	mkdir -p ${OBSRVBL_ROOT}/ona_service/
	cp -r ${SCRIPTS_DIR}/ona_service/* ${OBSRVBL_ROOT}/ona_service/

.PHONY: package
package:
	mkdir -p packaging/output/
	python package_builder.py ${ARCH} ${VERSION} ${system_type}

ona-service_RHEL_7_%.rpm:
	mkdir -p $(dir $@)
	python package_builder.py $(notdir $*) ${VERSION} RHEL_7

ona-service_RHEL_8_%.rpm:
	mkdir -p $(dir $@)
	python package_builder.py $(notdir $*) ${VERSION} RHEL_8

ona-service_RaspbianJessie_%.deb:
	mkdir -p $(dir $@)
	python package_builder.py $(notdir $*) ${VERSION} RaspbianJessie

ona-service_UbuntuXenial_%.deb:
	mkdir -p $(dir $@)
	python package_builder.py $(notdir $*) ${VERSION} UbuntuXenial

ona-service_UbuntuXenialContainer_%.deb:
	mkdir -p $(dir $@)
	python package_builder.py $(notdir $*) ${VERSION} UbuntuXenialContainer

.PHONY: clean
clean:
	make -C ${SCRIPTS_DIR} clean
	make -C ${uPNA_DIR} clean
	rm -rf ${OBSRVBL_ROOT}/netflow/
	rm -rf ${OBSRVBL_ROOT}/ipfix/
	rm -rf ${OBSRVBL_ROOT}/ona_service/
	rm -rf ${OBSRVBL_ROOT}/pna/
	rm -rf ${OBSRVBL_ROOT}/version

.PHONY: realclean
realclean: clean
	rm -rf packaging/output/
