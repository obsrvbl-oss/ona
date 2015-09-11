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
VERSION := 1.0
SHA := $(shell git rev-parse --short HEAD)

SCRIPTS_DIR := src/scripts
uPNA_DIR := src/uPNA
NETFLOW_DIR := src/netflow

OBSRVBL_ROOT := packaging/root/opt/obsrvbl-ona

all:
	@echo please specify a target

test: test-scripts

test-scripts:
	make -C ${SCRIPTS_DIR} test

coverage: coverage-scripts

coverage-scripts:
	make -C ${SCRIPTS_DIR} coverage

build:
	make -C ${uPNA_DIR}

copy:
	mkdir -p ${OBSRVBL_ROOT}/
	git rev-parse HEAD > ${OBSRVBL_ROOT}/version
	mkdir -p ${OBSRVBL_ROOT}/pna/user/
	cp ${uPNA_DIR}/module/pna ${OBSRVBL_ROOT}/pna/user/pna
	mkdir -p ${OBSRVBL_ROOT}/netflow/
	cp -r ${NETFLOW_DIR}/* ${OBSRVBL_ROOT}/netflow/
	mkdir -p ${OBSRVBL_ROOT}/ona_service/
	cp -r ${SCRIPTS_DIR}/ona_service/* ${OBSRVBL_ROOT}/ona_service/

package:
	mkdir -p packaging/output/
	python package_builder.py ${ARCH} ${VERSION} ${system_type}

clean:
	make -C ${SCRIPTS_DIR} clean
	make -C ${uPNA_DIR} clean
	rm -rf ${OBSRVBL_ROOT}/netflow/
	rm -rf ${OBSRVBL_ROOT}/ona_service/
	rm -rf ${OBSRVBL_ROOT}/pna/
	rm -rf ${OBSRVBL_ROOT}/version

realclean: clean
	rm -rf packaging/output/
