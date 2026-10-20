{#
  RF-05 / RN-01: net inflows = inflows - redemptions in the period. Fails on every row whose
  `net` column is null or differs from `inflow - redemption` (a missing side counts as zero) by
  more than `tolerance` (default 0: the amounts are decimals, so the comparison is exact).
  Model-level test, reused at every grain where a net inflow column appears.
#}
{% test net_inflow(model, net, inflow, redemption, tolerance=0) %}

select
    {{ net }} as vl_liquido,
    {{ inflow }} as vl_captacao,
    {{ redemption }} as vl_resgate
from {{ model }}
where {{ net }} is null
   or abs({{ net }} - (coalesce({{ inflow }}, 0) - coalesce({{ redemption }}, 0))) > {{ tolerance }}

{% endtest %}
