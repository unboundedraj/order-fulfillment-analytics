PY ?= python
DBT = cd dbt && DBT_PROFILES_DIR=. dbt

.PHONY: install lint fmt test test-fast run advance build docs dagster dashboard status clean

install:            ## install with orchestration, dashboard and dev extras
	$(PY) -m pip install -e ".[orchestration,dashboard,dev]"

lint:               ## python + SQL linting
	ruff check src tests dashboard
	ruff format --check src tests dashboard
	sqlfluff lint dbt/models

fmt:
	ruff format src tests dashboard
	ruff check --fix src tests dashboard
	sqlfluff fix dbt/models -f

test:               ## unit + end-to-end tests (runs dbt on a small simulated dataset)
	$(PY) -m pytest

test-fast:          ## skip the dbt end-to-end tests
	$(PY) -m pytest -m "not e2e"

run:                ## generate 2 years of data -> load -> dbt build
	$(PY) -m fulfillment run

advance:            ## release one more day of extracts and process incrementally
	$(PY) -m fulfillment advance --days 1

build:              ## dbt seed + build against the existing raw data
	$(PY) -m fulfillment transform

docs:               ## dbt docs site with lineage graph -> http://localhost:8081
	$(DBT) docs generate && $(DBT) docs serve --port 8081

dagster:            ## Dagster UI -> http://localhost:3000
	dagster dev -m fulfillment.orchestration.definitions

dashboard:          ## Streamlit dashboard -> http://localhost:8501
	streamlit run dashboard/app.py

status:
	$(PY) -m fulfillment status

clean:
	rm -rf data dbt/target dbt/logs .dagster_home
