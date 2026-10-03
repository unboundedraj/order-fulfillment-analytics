# Data model (core schema)

```mermaid
erDiagram
    fct_orders ||--o{ fct_order_items : contains
    fct_orders ||--o{ fct_order_status_history : "status changes"
    dim_customers ||--o{ fct_orders : "version valid at purchase (customer_sk)"
    dim_date ||--o{ fct_orders : order_date_key
    dim_geography ||--o{ fct_orders : customer_state
    dim_hubs ||--o{ fct_orders : hub_id
    dim_products ||--o{ fct_order_items : product_id

    fct_orders {
        varchar order_id PK
        varchar customer_sk FK
        integer order_date_key FK
        varchar customer_state FK
        varchar hub_id FK
        varchar courier
        varchar payment_method
        varchar current_status
        timestamp purchase_at
        timestamp approved_at
        timestamp shipped_at
        timestamp delivered_at
        date estimated_delivery_date
        double approval_hours
        double processing_hours
        double transit_days
        double delivery_days
        boolean is_late
        bigint days_late
        boolean has_timestamp_anomaly
        decimal gross_merchandise_value
        decimal net_revenue
        timestamp source_last_loaded_at
    }
    dim_customers {
        varchar customer_sk PK
        varchar customer_id
        varchar state
        varchar region
        timestamp valid_from
        timestamp valid_to
        boolean is_current
    }
    dim_date {
        integer date_key PK
        date date_day
        varchar fiscal_year
        boolean is_weekend
        varchar sale_event
    }
    dim_geography {
        varchar state PK
        varchar region
        integer remoteness_tier
    }
    fct_order_items {
        varchar order_item_id PK
        varchar order_id FK
        varchar product_id FK
        decimal line_amount
    }
    fct_order_status_history {
        varchar order_version_id PK
        varchar order_id FK
        varchar order_status
        timestamp valid_from
        timestamp valid_to
        double hours_in_status
    }
    dim_products {
        varchar product_id PK
        varchar category
        varchar seller_id
        varchar hub_id
    }
    dim_hubs {
        varchar hub_id PK
        varchar hub_region
    }
```

## Grain and keys

| Table | Grain | Key | Notes |
|---|---|---|---|
| `fct_orders` | order (current state) | `order_id` | incremental `delete+insert`; contract enforced |
| `fct_order_items` | order line | `order_item_id` | |
| `fct_order_status_history` | order × status interval | `order_version_id` | SCD2 built from the CDC log |
| `dim_customers` | customer × address version | `customer_sk` | SCD2; exactly one `is_current` row per customer (tested) |
| `dim_date` | day | `date_key` (yyyymmdd) | Indian FY (Apr–Mar) and sale flags |

## KPI definitions

| KPI | Definition |
|---|---|
| Approval time | `approved_at - purchase_at` in hours |
| Processing time | `shipped_at - approved_at` in hours (warehouse pick, pack and handover) |
| Transit time | `delivered_at - shipped_at` in days; null when timestamps are anomalous |
| Order-to-door | `delivered_at - purchase_at` in days |
| On-time rate | delivered orders whose delivery date ≤ the promised date shown at checkout |
| RTO rate | orders returned to origin (undeliverable) / all orders |
| Bottleneck stage | the stage with the largest excess hours over the national average, per state |
| Net revenue | charges − refunds (COD is charged on delivery) |
