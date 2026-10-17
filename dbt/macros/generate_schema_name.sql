{#
  RNF-05: models land in the schema named by their layer (`staging`, `marts`) instead of dbt's
  default `<target schema>_<custom schema>` (e.g. `main_staging`). Models without a custom
  schema stay in the target schema.
#}
{% macro generate_schema_name(custom_schema_name, node) -%}
  {%- if custom_schema_name is none -%}
    {{ target.schema }}
  {%- else -%}
    {{ custom_schema_name | trim }}
  {%- endif -%}
{%- endmacro %}
