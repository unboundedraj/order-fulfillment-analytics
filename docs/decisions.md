# Design decisions

### 1. A simulator instead of a static CSV
The original dashboard used a small mock extract. A static file can't exercise what a data
engineer actually deals with, which is data arriving every day, late, duplicated and dirty. The
seeded simulator produces two years of daily CDC extracts with those problems built in, and
it can release days one at a time (`fulfillment advance`) to exercise incremental processing.
It's deterministic, so tests can make exact assertions.

### 2. CDC row versions, not snapshots
Each status change is a new row. That's what log-based CDC (Debezium, DMS) delivers, and it
makes it possible to rebuild status history (SCD2) and to resolve the current state
correctly when rows arrive out of order.

### 3. Raw is append-only, and dedup happens in dbt
The loader never transforms or deduplicates. Raw is the audit trail, and all business logic
is versioned, tested SQL in dbt. Idempotency comes from the load manifest (file path, size
and mtime), with each entity's load committed in one transaction.

### 4. The incremental fact is driven by load time, not event time
An event-time watermark misses a late row for an old order. Selecting orders whose newest
source row (order version **or payment**) was loaded after the previous run catches every
change. `delete+insert` on `order_id` keeps re-runs idempotent, and a pytest test asserts the
incremental result equals a full refresh.

### 5. SCD2 derived from the log instead of `dbt snapshot`
Snapshots only capture what they happen to observe at run time, and their state is lost if
the warehouse is rebuilt. Deriving validity intervals from the CDC log with window functions
is reproducible from raw at any time, and it includes changes that happened between runs.

### 6. Point-in-time joins for customer attributes
An order belongs to the state the customer lived in **when it was placed**. Joining to the
current address would quietly move historical orders between states whenever someone moves.

### 7. Settlement window for financial checks
Reconciling every order raises false alarms at the edge of the data, because refunds can
arrive before the late "returned" status that explains them. The window is derived from
business rules (12-day return window + 3 days of CDC lateness + 1-day refund lag), not tuned.

### 8. Model contract on the fact table
`fct_orders` is the interface for downstream consumers. Enforcing the contract means a
renamed column or changed type fails the build, not the dashboard.

### 9. DuckDB + dbt instead of a cloud warehouse
Everything runs on a laptop and in CI in under two minutes at full size. The SQL is standard
enough to move to Snowflake, BigQuery or Databricks: swap the dbt adapter and the
`epoch()`/`range()` helpers in `macros/`.

### 10. Dagster for orchestration
Its asset model matches the warehouse. Every dbt model is an asset, dbt tests become asset
checks, and lineage from landing files to KPI marts is visible in one graph.

### 11. Streamlit dashboard instead of Tableau
The original Tableau workbook is not reproducible from a repository. A code-defined dashboard
reads the same marts, is versioned with them, and is declared as a dbt exposure so lineage
reaches the consumer.
