{#
  RF-02 / RNF-05: column standardization helpers used by the staging models.
  The rules behind each helper are documented in docs/naming-conventions.md.
#}

{# Empty or blank strings become null; everything else is trimmed. #}
{% macro clean_text(column) -%}
  nullif(trim({{ column }}), '')
{%- endmacro %}

{# nm_ columns: free text, trimmed, inner runs of whitespace collapsed; case and accents kept. #}
{% macro clean_name(column) -%}
  nullif(regexp_replace(trim({{ column }}), '\s+', ' ', 'g'), '')
{%- endmacro %}

{# tp_ / sit_ columns: categorical codes in upper case, without accents, whitespace collapsed. #}
{% macro clean_code(column) -%}
  nullif(upper(strip_accents(regexp_replace(trim({{ column }}), '\s+', ' ', 'g'))), '')
{%- endmacro %}

{#
  cnpj_ columns: 14 characters, punctuation removed, left-padded with zeros (guards against a
  CNPJ that went through a numeric type upstream). Letters are kept in upper case so that the
  alphanumeric CNPJ (12 alphanumeric characters + 2 check digits) introduced by the Brazilian
  Federal Revenue in July 2026 is accepted as-is.
#}
{% macro clean_cnpj(column) -%}
  nullif(lpad(upper(regexp_replace({{ column }}, '[^0-9A-Za-z]', '', 'g')), 14, '0'), '00000000000000')
{%- endmacro %}

{# cpf_cnpj_ columns: either a CPF (11 digits, natural person) or a CNPJ; punctuation removed, no padding. #}
{% macro clean_cpf_cnpj(column) -%}
  nullif(upper(regexp_replace({{ column }}, '[^0-9A-Za-z]', '', 'g')), '')
{%- endmacro %}

{# dt_ columns: ISO dates (YYYY-MM-DD). A malformed value fails the build on purpose. #}
{% macro to_date(column) -%}
  cast({{ clean_text(column) }} as date)
{%- endmacro %}

{# vl_ columns: decimal values with a point as decimal separator (default: money, 2 places). #}
{% macro to_decimal(column, precision=18, scale=2) -%}
  cast({{ clean_text(column) }} as decimal({{ precision }}, {{ scale }}))
{%- endmacro %}

{# nr_ columns: counts. #}
{% macro to_integer(column) -%}
  cast({{ clean_text(column) }} as integer)
{%- endmacro %}

{# fl_ columns: CVM S/N flags to boolean; N/A, blanks and anything else become null. #}
{% macro to_flag(column) -%}
  case upper(trim({{ column }})) when 'S' then true when 'N' then false end
{%- endmacro %}
