-- Temporary (task 7.1): proves that a failing dbt test on a model fails CI. Reverted next.
select * from {{ ref('dim_fundo') }}
