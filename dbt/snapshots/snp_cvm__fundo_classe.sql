{#
  RF-04 (3.4): SCD type 2 history of the unified fund/class registry. Design:
  docs/dimensional-model.md; decisions: docs/adr/007-registry-snapshot-source-and-hard-deletes.md.

  * Source: int_fundo_classe__unificado (a view, so the snapshot can select from it), one row per
    reporting CNPJ.
  * strategy check on the explicit list of tracked attributes below; a change in any of them
    closes the current version and opens a new one.
  * invalidate_hard_deletes = false: a CNPJ that leaves the registry keeps its last version open,
    so facts that still report it keep resolving (exactly one current version per CNPJ).
  * History accumulates only where the DuckDB file persists; in CI it lives for one run.
#}
{% snapshot snp_cvm__fundo_classe %}

{{
    config(
        target_schema='snapshots',
        unique_key='cnpj_fundo_classe',
        strategy='check',
        check_cols=[
            'tp_registro',
            'id_registro_classe',
            'id_registro_fundo',
            'cnpj_fundo',
            'nm_denominacao_social',
            'nm_denominacao_social_fundo',
            'tp_fundo',
            'tp_classe',
            'sit_fundo_classe',
            'sit_fundo',
            'tp_classificacao',
            'tp_classificacao_anbima',
            'tp_condominio',
            'tp_publico_alvo',
            'fl_exclusivo',
            'cnpj_administrador',
            'nm_administrador',
            'cpf_cnpj_gestor',
            'nm_gestor',
            'dt_registro',
        ],
        invalidate_hard_deletes=false,
    )
}}

select * from {{ ref('int_fundo_classe__unificado') }}

{% endsnapshot %}
