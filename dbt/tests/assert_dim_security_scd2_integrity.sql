-- Exactly one current row per security, and version intervals never overlap or leave gaps.
with v as (
    select security_id, valid_from, valid_to, is_current,
           lead(valid_from) over (partition by security_id order by valid_from) as next_from
    from {{ source('gold_tasks', 'dim_security') }}
)
select security_id, 'gap_or_overlap' as problem from v where next_from is not null and next_from <> valid_to
union all
select security_id, 'current_count_' || count_if(is_current) from v group by security_id having count_if(is_current) <> 1
