-- SCD2 built declaratively from the full history of monthly fund snapshots (compare with the stateful,
-- hand-written MERGE in V003 for DIM_SECURITY). Rebuildable from Bronze at any time.
with h as (
    select *, md5(concat_ws('|', fund_name, strategy, expense_ratio::string, manager_name, manager_email)) as hash_diff
    from {{ ref('stg_funds') }}
),
changes as (
    select *, lag(hash_diff) over (partition by fund_id order by as_of_date) as prev_hash
    from h
),
versions as (select * from changes where prev_hash is null or prev_hash <> hash_diff)
select md5(fund_id || '|' || as_of_date) as fund_sk,
       fund_id, fund_ticker, fund_name, strategy, region, expense_ratio, inception_date, manager_name,
       iff(row_number() over (partition by fund_id order by as_of_date) = 1, '1900-01-01'::date, as_of_date) as valid_from,
       coalesce(lead(as_of_date) over (partition by fund_id order by as_of_date), '9999-12-31'::date) as valid_to,
       valid_to = '9999-12-31'::date as is_current
from versions
