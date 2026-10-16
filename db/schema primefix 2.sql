ALTER TABLE service_orders
ADD COLUMN IF NOT EXISTS aprovacao_cliente VARCHAR(20) DEFAULT 'pendente';

UPDATE service_orders
SET aprovacao_cliente = 'pendente'
WHERE aprovacao_cliente IS NULL;

ALTER TABLE service_orders
ADD CONSTRAINT service_orders_aprovacao_cliente_check
CHECK (aprovacao_cliente IN ('pendente', 'aprovado', 'recusado'));

 ----- teste da atividade acima  

 SELECT id, status, valor_sugerido, valor_confirmado, aprovacao_cliente
FROM service_orders
ORDER BY id DESC; 


---- Criar aprovação do cliente

ALTER TABLE service_orders
ADD COLUMN IF NOT EXISTS aprovacao_cliente VARCHAR(20) DEFAULT 'pendente';

UPDATE service_orders
SET aprovacao_cliente = 'pendente'
WHERE aprovacao_cliente IS NULL;

ALTER TABLE service_orders
ADD CONSTRAINT service_orders_aprovacao_cliente_check
CHECK (aprovacao_cliente IN ('pendente', 'aprovado', 'recusado'));

-- teste de execução 
SELECT id, status, valor_sugerido, valor_confirmado, aprovacao_cliente
FROM service_orders
ORDER BY id DESC;

