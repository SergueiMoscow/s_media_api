APPS = s_media_proxy
CODE = django_app $(APPS)
TEST = pytest --verbosity=2 --strict-markers ${arg} -k "${k}"

.PHONY: lint
lint:
	flake8 --jobs 4 --statistics --show-source $(CODE)
	pylint --jobs 4 $(CODE)
	black --check $(CODE)
	unify --in-place --recursive --check $(CODE)

.PHONY: check_no_missing_migrations
check_no_missing_migrations:
	./manage.py makemigrations --settings django_app.settings_tests --check --dry-run

.PHONY: format
format:
	autoflake $(CODE)
	isort $(CODE)
	black $(CODE)
	unify --in-place --recursive $(CODE)

.PHONY: check
check: format check_no_missing_migrations lint test

.PHONY: check_ci_job
check_ci_job: lint check_no_missing_migrations test

.PHONY: test
test:
	${TEST} --cov=${APPS} --ignore=${APPS}/tests/test_integration.py

.PHONY: test-fast
test-fast:
	${TEST} --exitfirst --cov=${APPS} --ignore=${APPS}/tests/test_integration.py

.PHONY: test-failed
test-failed:
	${TEST} --last-failed --ignore=${APPS}/tests/test_integration.py

.PHONY: test-integration
test-integration:
	$(eval k := integration)
	${TEST}
