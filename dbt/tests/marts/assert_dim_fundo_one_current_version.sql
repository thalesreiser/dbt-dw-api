-- RF-04 (3.4): every CNPJ of dim_fundo has exactly one current version (fl_versao_atual).
-- Returns the CNPJs with zero or several current versions.

select
    cnpj_fundo_classe,
    count(*) filter (where fl_versao_atual) as nr_versoes_atuais
from {{ ref('dim_fundo') }}
group by cnpj_fundo_classe
having count(*) filter (where fl_versao_atual) <> 1
