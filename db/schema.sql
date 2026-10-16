-- ============================================
-- NOVO ENUM: dias da semana
-- ============================================

CREATE TYPE week_day AS ENUM (
    'segunda',
    'terca',
    'quarta',
    'quinta',
    'sexta',
    'sabado',
    'domingo'
);

-- ============================================
-- ALTER TABLE: technicians
-- ============================================

ALTER TABLE technicians
ADD COLUMN categoria_id INTEGER REFERENCES categories(id) ON DELETE SET NULL,
ADD COLUMN descricao TEXT,
ADD COLUMN cidade VARCHAR(100),
ADD COLUMN estado VARCHAR(2),
ADD COLUMN foto VARCHAR(255),
ADD COLUMN pix VARCHAR(255),
ADD COLUMN atendimento_remoto BOOLEAN NOT NULL DEFAULT TRUE,
ADD COLUMN atendimento_domicilio BOOLEAN NOT NULL DEFAULT TRUE,
ADD COLUMN raio_atendimento INTEGER NOT NULL DEFAULT 20,
ADD COLUMN aceita_novos_servicos BOOLEAN NOT NULL DEFAULT TRUE,
ADD COLUMN nota_media NUMERIC(3,2) NOT NULL DEFAULT 0.00,
ADD COLUMN total_servicos INTEGER NOT NULL DEFAULT 0;

-- ============================================
-- NOVA TABELA: technician_availability
-- ============================================

CREATE TABLE technician_availability (
    id SERIAL PRIMARY KEY,
    technician_id INTEGER NOT NULL
        REFERENCES technicians(id)
        ON DELETE CASCADE,

    dia_semana week_day NOT NULL,

    hora_inicio TIME NOT NULL,

    hora_fim TIME NOT NULL,

    ativo BOOLEAN NOT NULL DEFAULT TRUE,

    created_at TIMESTAMP NOT NULL DEFAULT NOW(),

    CONSTRAINT uq_technician_day UNIQUE (technician_id, dia_semana)
);

CREATE INDEX idx_availability_technician
ON technician_availability(technician_id);

-- ============================================
-- NOVO STATUS DA ORDEM DE SERVIÇO
-- ============================================

ALTER TYPE os_status
ADD VALUE IF NOT EXISTS 'recusada_pelo_tecnico';

-- ============================================
-- ATUALIZA CATEGORIAS PADRÃO
-- ============================================

TRUNCATE TABLE categories RESTART IDENTITY CASCADE;

INSERT INTO categories (nome, descricao) VALUES
('Informática & Tecnologia', 'Manutenção de computadores, notebooks, redes e suporte técnico'),
('Instalação de Câmeras', 'Instalação e manutenção de sistemas de monitoramento'),
('Ar-Condicionado', 'Limpeza e manutenção de ar-condicionado'),
('Assistência Residencial', 'Serviços elétricos e manutenção residencial');