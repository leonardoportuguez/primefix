CREATE TABLE IF NOT EXISTS password_reset_tokens (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token VARCHAR(100) UNIQUE NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    expira_em TIMESTAMP NOT NULL,
    usado BOOLEAN NOT NULL DEFAULT FALSE
);

ALTER TABLE service_orders
ADD COLUMN atribuida_em TIMESTAMP;

ALTER TABLE categories ADD COLUMN ordem INTEGER;

-- Preenche a ordem inicial com base na ordem de criação atual
-- (a categoria mais antiga fica em primeiro, por enquanto)
UPDATE categories SET ordem = id;


ALTER TABLE service_orders ADD COLUMN motivo_cancelamento TEXT; 








--- saber oq ha no projeto 

SELECT
    column_name AS coluna,
    data_type AS tipo,
    is_nullable AS aceita_nulo,
    column_default AS valor_padrao
FROM information_schema.columns
WHERE table_schema = 'public'
  AND table_name = 'technicians'
ORDER BY ordinal_position;




SELECT
    t.typname AS nome_tipo,
    e.enumlabel AS valor
FROM pg_type t
JOIN pg_enum e ON t.oid = e.enumtypid
WHERE t.typname = 'technician_status'
ORDER BY e.enumsortorder;


-- ============================================================
-- 001 - CONTROLE DE APROVAÇÃO DE PARCEIROS TÉCNICOS
-- ============================================================
-- O que este algoritmo faz:
-- Cria os campos necessários para controlar a solicitação
-- de parceria do técnico.
--
-- status_aprovacao:
--   pendente  = aguardando análise do administrador
--   aprovado  = técnico aceito como parceiro
--   recusado   = solicitação recusada
--
-- data_analise:
--   registra quando o administrador tomou a decisão.
--
-- prazo_analise:
--   registra a data limite de 48 horas para análise.
--
-- motivo_recusa:
--   permite registrar o motivo caso a solicitação seja recusada.
-- ============================================================

ALTER TABLE technicians
ADD COLUMN IF NOT EXISTS status_aprovacao VARCHAR(20) NOT NULL DEFAULT 'pendente';

ALTER TABLE technicians
ADD COLUMN IF NOT EXISTS data_analise TIMESTAMP NULL;

ALTER TABLE technicians
ADD COLUMN IF NOT EXISTS prazo_analise TIMESTAMP NULL;

ALTER TABLE technicians
ADD COLUMN IF NOT EXISTS motivo_recusa TEXT NULL; 




-- ============================================================
-- VERIFICAÇÃO
-- ============================================================
-- Mostra as novas colunas criadas na tabela technicians.
-- Serve para confirmar que a alteração foi aplicada corretamente.
-- ============================================================

SELECT
    column_name AS coluna,
    data_type AS tipo,
    is_nullable AS aceita_nulo,
    column_default AS valor_padrao
FROM information_schema.columns
WHERE table_schema = 'public'
  AND table_name = 'technicians'
ORDER BY ordinal_position; 





--- testes 
SELECT
    id,
    nome,
    status,
    status_aprovacao,
    data_analise,
    prazo_analise,
    motivo_recusa
FROM technicians
ORDER BY id DESC
LIMIT 1;

---teste 2 
SELECT
    id,
    user_id,
    nome,
    status,
    status_aprovacao,
    data_analise,
    prazo_analise,
    created_at
FROM technicians
ORDER BY id DESC
LIMIT 1;

