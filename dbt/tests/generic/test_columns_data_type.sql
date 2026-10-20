{#
  RF-05 / RN-02: the listed columns of the model are stored with the expected type, a
  case-insensitive LIKE pattern against `information_schema.columns.data_type` (DuckDB), e.g.
  'DECIMAL(%,2)' for money in BRL (never FLOAT/DOUBLE) or 'DATE' for calendar dates. Returns one
  row per column that is missing or has another type.
#}
{% test columns_data_type(model, columns, data_type) %}

with expected as (

    {% for column in columns %}
    select '{{ column }}' as column_name{% if not loop.last %} union all{% endif %}
    {% endfor %}

),

actual as (

    select lower(column_name) as column_name, data_type
    from information_schema.columns
    where lower(table_schema) = lower('{{ model.schema }}')
      and lower(table_name) = lower('{{ model.identifier }}')

)

select e.column_name, a.data_type, '{{ data_type }}' as expected_data_type
from expected as e
left join actual as a
    on a.column_name = lower(e.column_name)
where a.data_type is null
   or not (a.data_type ilike '{{ data_type }}')

{% endtest %}
