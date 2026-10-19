-- RF-03 (3.2): fl_dia_util sanity. Fails on any row returned:
-- * a weekend or a holiday flagged as a business day;
-- * a known national holiday inside the range that is a business day;
-- * a known business day inside the range that is not;
-- * a gap in the calendar (the spine must be contiguous).

with d as (

    select * from {{ ref('dim_data') }}

),

esperados (dt, fl_esperado) as (

    values
        (date '2025-12-25', false),   -- Natal
        (date '2026-02-17', false),   -- Carnaval (Easter-based)
        (date '2026-04-03', false),   -- Paixao de Cristo (Easter-based)
        (date '2026-09-07', false),   -- Independencia do Brasil
        (date '2026-10-12', false),   -- Nossa Senhora Aparecida
        (date '2026-11-20', false),   -- Consciencia Negra (national from 2024)
        (date '2026-09-08', true),    -- an ordinary Tuesday
        (date '2026-09-30', true)     -- an ordinary Wednesday

)

select 'weekend or holiday flagged as business day' as falha, sk_data
from d
where fl_dia_util and (fl_fim_de_semana or fl_feriado)

union all

select 'unexpected fl_dia_util', e.dt
from esperados as e
inner join d on d.sk_data = e.dt
where d.fl_dia_util <> e.fl_esperado

union all

select 'calendar gap', max(sk_data)
from d
having count(*) <> max(sk_data) - min(sk_data) + 1
