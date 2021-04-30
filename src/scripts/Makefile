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
PYTHONPATH ?= ../../packaging/root/opt/obsrvbl-ona/system/python-packages

all: test

vendor:
	mkdir -p ${PYTHONPATH}
	pip install --target="${PYTHONPATH}" -U -r requirements.txt
	touch "${PYTHONPATH}/supervisor/__init__.py"

requirements: vendor
	python3 -m pip install -r requirements.txt
	python3 -m pip install flake8 coverage

flake8:
	flake8 --max-complexity 10 .

quicktest:
	PYTHONPATH="${PYTHONPATH}" python3 -m unittest -v ${tests}

test: requirements flake8 quicktest

coverage: requirements flake8
	PYTHONPATH="${PYTHONPATH}" coverage run -m unittest -v
	coverage report

clean:
	find . -name '*.py[co]' -delete
	find . -name '__pycache__' -delete
	find ${PYTHONPATH} -name '*.py[co]' -delete
	find ${PYTHONPATH} -name '__pycache__' -delete
	rm -f .coverage
