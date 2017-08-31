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
all: test

requirements:
	pip install flake8 coverage nose mock

flake8:
	flake8 --max-complexity 10 --exclude=ona_service/vendor/ .

quicktest:
	python -m nose --verbose --where=tests/ ${tests}

test: requirements flake8 quicktest

coverage: requirements flake8
	coverage run -m nose --verbose --where="tests/"
	coverage report

clean:
	find . -name '*.py[co]' -delete
	rm -f .coverage
