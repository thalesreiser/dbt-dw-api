{#
  RF-02: a cnpj_ column holds exactly 14 characters without punctuation: 12 alphanumeric
  characters (digits only for every CNPJ issued before July 2026) followed by 2 check digits.
  Nulls are left to not_null.
#}
{% test valid_cnpj(model, column_name) %}

select {{ column_name }}
from {{ model }}
where {{ column_name }} is not null
  and not regexp_full_match({{ column_name }}, '[0-9A-Z]{12}[0-9]{2}')

{% endtest %}


{#
  RF-02: a cpf_cnpj_ column holds either a CPF (11 digits) or a CNPJ (see valid_cnpj).
#}
{% test valid_cpf_cnpj(model, column_name) %}

select {{ column_name }}
from {{ model }}
where {{ column_name }} is not null
  and not regexp_full_match({{ column_name }}, '[0-9]{11}|[0-9A-Z]{12}[0-9]{2}')

{% endtest %}
