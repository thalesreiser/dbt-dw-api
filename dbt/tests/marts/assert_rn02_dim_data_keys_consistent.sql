-- RF-05 / RN-02: the calendar keys agree with the date. For every day of dim_data, `sk_mes` and
-- `dt_inicio_mes` are the first day of the month of `sk_data`, `dt_fim_mes` its last day, and
-- year, quarter, month and day are the parts of `sk_data`. Facts join on these keys
-- (`sk_data`, `sk_mes`), so a wrong key would move a value to another day or month.

select sk_data, sk_mes, dt_inicio_mes, dt_fim_mes, nr_ano, nr_trimestre, nr_mes, nr_dia
from {{ ref('dim_data') }}
where sk_mes is distinct from cast(date_trunc('month', sk_data) as date)
   or dt_inicio_mes is distinct from sk_mes
   or dt_fim_mes is distinct from last_day(sk_data)
   or nr_ano is distinct from year(sk_data)
   or nr_trimestre is distinct from quarter(sk_data)
   or nr_mes is distinct from month(sk_data)
   or nr_dia is distinct from day(sk_data)
