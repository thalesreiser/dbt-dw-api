{#
  RF-01 verification: logs the row count of every declared source and fails if any is below
  `min_rows`. Usage: dbt run-operation source_row_counts --args '{min_rows: 1}'
#}
{% macro source_row_counts(min_rows=1) %}
  {% set empty = [] %}
  {% for node in graph.sources.values() %}
    {% set relation = source(node.source_name, node.name) %}
    {% set result = run_query("select count(*) from " ~ relation) %}
    {% set rows = result.columns[0].values()[0] %}
    {{ log("row_count " ~ node.source_name ~ "." ~ node.name ~ " " ~ rows, info=true) }}
    {% if rows < min_rows %}
      {% do empty.append(node.source_name ~ "." ~ node.name) %}
    {% endif %}
  {% endfor %}
  {% if empty %}
    {{ exceptions.raise_compiler_error("sources below " ~ min_rows ~ " rows: " ~ empty | join(", ")) }}
  {% endif %}
{% endmacro %}
