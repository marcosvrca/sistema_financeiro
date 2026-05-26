SCHEMA_SQLITE = """
CREATE TABLE IF NOT EXISTS importacoes_extrato (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    criado_em TEXT DEFAULT (datetime('now')),
    qtd_lidas INTEGER NOT NULL DEFAULT 0,
    qtd_inseridas INTEGER NOT NULL DEFAULT 0,
    qtd_duplicadas INTEGER NOT NULL DEFAULT 0,
    data_min TEXT,
    data_max TEXT
);

CREATE TABLE IF NOT EXISTS movimentos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    data TEXT NOT NULL,
    historico TEXT NOT NULL,
    docto TEXT NOT NULL,
    credito TEXT,
    debito TEXT,
    saldo TEXT,
    categoria TEXT NOT NULL,
    hash_linha TEXT NOT NULL UNIQUE,
    importacao_id INTEGER REFERENCES importacoes_extrato(id)
);
CREATE INDEX IF NOT EXISTS idx_movimentos_data ON movimentos(data);
CREATE INDEX IF NOT EXISTS idx_movimentos_categoria ON movimentos(categoria);

CREATE TABLE IF NOT EXISTS contas_fixas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nome TEXT NOT NULL,
    valor TEXT NOT NULL,
    dia_vencimento INTEGER,
    categoria TEXT NOT NULL DEFAULT 'Contas fixas',
    historico_contem TEXT,
    ativo INTEGER NOT NULL DEFAULT 1,
    observacao TEXT
);

CREATE TABLE IF NOT EXISTS lancamentos_manuais (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    data TEXT NOT NULL,
    descricao TEXT NOT NULL,
    valor TEXT NOT NULL,
    tipo TEXT NOT NULL CHECK (tipo IN ('entrada', 'saida')),
    categoria TEXT NOT NULL,
    criado_em TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_lanc_manuais_data ON lancamentos_manuais(data);

CREATE TABLE IF NOT EXISTS orcamento_mensal (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    mes TEXT NOT NULL,
    categoria TEXT NOT NULL,
    limite TEXT NOT NULL,
    UNIQUE (mes, categoria)
);

CREATE TABLE IF NOT EXISTS configuracao (
    chave TEXT PRIMARY KEY,
    valor TEXT NOT NULL
);
"""

SCHEMA_POSTGRES = """
CREATE TABLE IF NOT EXISTS importacoes_extrato (
    id SERIAL PRIMARY KEY,
    criado_em TIMESTAMPTZ DEFAULT NOW(),
    qtd_lidas INTEGER NOT NULL DEFAULT 0,
    qtd_inseridas INTEGER NOT NULL DEFAULT 0,
    qtd_duplicadas INTEGER NOT NULL DEFAULT 0,
    data_min DATE,
    data_max DATE
);

CREATE TABLE IF NOT EXISTS movimentos (
    id SERIAL PRIMARY KEY,
    data DATE NOT NULL,
    historico TEXT NOT NULL,
    docto TEXT NOT NULL DEFAULT '',
    credito NUMERIC(14,2),
    debito NUMERIC(14,2),
    saldo NUMERIC(14,2),
    categoria TEXT NOT NULL,
    hash_linha TEXT NOT NULL UNIQUE,
    importacao_id INTEGER REFERENCES importacoes_extrato(id)
);
CREATE INDEX IF NOT EXISTS idx_movimentos_data ON movimentos(data);
CREATE INDEX IF NOT EXISTS idx_movimentos_categoria ON movimentos(categoria);

CREATE TABLE IF NOT EXISTS contas_fixas (
    id SERIAL PRIMARY KEY,
    nome TEXT NOT NULL,
    valor NUMERIC(14,2) NOT NULL,
    dia_vencimento SMALLINT,
    categoria TEXT NOT NULL DEFAULT 'Contas fixas',
    historico_contem TEXT,
    ativo SMALLINT NOT NULL DEFAULT 1,
    observacao TEXT
);

CREATE TABLE IF NOT EXISTS lancamentos_manuais (
    id SERIAL PRIMARY KEY,
    data DATE NOT NULL,
    descricao TEXT NOT NULL,
    valor NUMERIC(14,2) NOT NULL,
    tipo TEXT NOT NULL CHECK (tipo IN ('entrada', 'saida')),
    categoria TEXT NOT NULL,
    criado_em TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_lanc_manuais_data ON lancamentos_manuais(data);

CREATE TABLE IF NOT EXISTS orcamento_mensal (
    id SERIAL PRIMARY KEY,
    mes TEXT NOT NULL,
    categoria TEXT NOT NULL,
    limite NUMERIC(14,2) NOT NULL,
    UNIQUE (mes, categoria)
);

CREATE TABLE IF NOT EXISTS configuracao (
    chave TEXT PRIMARY KEY,
    valor TEXT NOT NULL
);
"""
