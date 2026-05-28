"""Tabelas adicionais: investimentos, metas, dívidas, regras, tags, contas."""

SCHEMA_EXTRAS = """
CREATE TABLE IF NOT EXISTS regras_categoria (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    padrao TEXT NOT NULL,
    categoria TEXT NOT NULL,
    prioridade INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS contas_bancarias (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nome TEXT NOT NULL,
    tipo TEXT NOT NULL DEFAULT 'corrente',
    ativo INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS metas_financeiras (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tipo TEXT NOT NULL,
    nome TEXT NOT NULL,
    valor_alvo TEXT,
    valor_atual TEXT NOT NULL DEFAULT '0',
    multiplicador_meses INTEGER,
    prazo TEXT,
    criado_em TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS projetos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nome TEXT NOT NULL,
    valor_alvo TEXT NOT NULL,
    valor_acumulado TEXT NOT NULL DEFAULT '0',
    aporte_mensal TEXT,
    prazo TEXT,
    ativo INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS dividas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nome TEXT NOT NULL,
    valor_total TEXT NOT NULL,
    valor_pago TEXT NOT NULL DEFAULT '0',
    taxa_mensal TEXT,
    parcelas INTEGER,
    parcelas_pagas INTEGER NOT NULL DEFAULT 0,
    estrategia TEXT DEFAULT 'minimo',
    ativo INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS ativos_investimento (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nome TEXT NOT NULL,
    tipo TEXT NOT NULL,
    instituicao TEXT,
    valor_atual TEXT NOT NULL DEFAULT '0',
    ativo INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS movimentos_investimento (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ativo_id INTEGER NOT NULL REFERENCES ativos_investimento(id),
    data TEXT NOT NULL,
    tipo TEXT NOT NULL CHECK (tipo IN ('aporte', 'resgate', 'rendimento')),
    valor TEXT NOT NULL,
    observacao TEXT
);

CREATE TABLE IF NOT EXISTS metas_alocacao (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tipo_ativo TEXT NOT NULL UNIQUE,
    percentual TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS tags (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nome TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS lancamento_tags (
    lancamento_id INTEGER NOT NULL,
    tag_id INTEGER NOT NULL,
    PRIMARY KEY (lancamento_id, tag_id)
);

CREATE TABLE IF NOT EXISTS cartoes_credito (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nome TEXT NOT NULL,
    bandeira TEXT,
    dia_vencimento INTEGER NOT NULL,
    dia_fechamento INTEGER,
    limite TEXT,
    ativo INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS compras_cartao (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    cartao_id INTEGER NOT NULL REFERENCES cartoes_credito(id),
    descricao TEXT NOT NULL,
    valor_total TEXT NOT NULL,
    parcelas INTEGER NOT NULL DEFAULT 1,
    data_compra TEXT NOT NULL,
    primeira_fatura TEXT NOT NULL,
    observacao TEXT,
    criado_em TEXT DEFAULT (datetime('now'))
);
"""

SCHEMA_EXTRAS_POSTGRES = """
CREATE TABLE IF NOT EXISTS regras_categoria (
    id SERIAL PRIMARY KEY,
    padrao TEXT NOT NULL,
    categoria TEXT NOT NULL,
    prioridade INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS contas_bancarias (
    id SERIAL PRIMARY KEY,
    nome TEXT NOT NULL,
    tipo TEXT NOT NULL DEFAULT 'corrente',
    ativo SMALLINT NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS metas_financeiras (
    id SERIAL PRIMARY KEY,
    tipo TEXT NOT NULL,
    nome TEXT NOT NULL,
    valor_alvo NUMERIC(14,2),
    valor_atual NUMERIC(14,2) NOT NULL DEFAULT 0,
    multiplicador_meses INTEGER,
    prazo DATE,
    criado_em TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS projetos (
    id SERIAL PRIMARY KEY,
    nome TEXT NOT NULL,
    valor_alvo NUMERIC(14,2) NOT NULL,
    valor_acumulado NUMERIC(14,2) NOT NULL DEFAULT 0,
    aporte_mensal NUMERIC(14,2),
    prazo DATE,
    ativo SMALLINT NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS dividas (
    id SERIAL PRIMARY KEY,
    nome TEXT NOT NULL,
    valor_total NUMERIC(14,2) NOT NULL,
    valor_pago NUMERIC(14,2) NOT NULL DEFAULT 0,
    taxa_mensal NUMERIC(8,4),
    parcelas INTEGER,
    parcelas_pagas INTEGER NOT NULL DEFAULT 0,
    estrategia TEXT DEFAULT 'minimo',
    ativo SMALLINT NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS ativos_investimento (
    id SERIAL PRIMARY KEY,
    nome TEXT NOT NULL,
    tipo TEXT NOT NULL,
    instituicao TEXT,
    valor_atual NUMERIC(14,2) NOT NULL DEFAULT 0,
    ativo SMALLINT NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS movimentos_investimento (
    id SERIAL PRIMARY KEY,
    ativo_id INTEGER NOT NULL REFERENCES ativos_investimento(id),
    data DATE NOT NULL,
    tipo TEXT NOT NULL CHECK (tipo IN ('aporte', 'resgate', 'rendimento')),
    valor NUMERIC(14,2) NOT NULL,
    observacao TEXT
);

CREATE TABLE IF NOT EXISTS metas_alocacao (
    id SERIAL PRIMARY KEY,
    tipo_ativo TEXT NOT NULL UNIQUE,
    percentual NUMERIC(6,2) NOT NULL
);

CREATE TABLE IF NOT EXISTS tags (
    id SERIAL PRIMARY KEY,
    nome TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS lancamento_tags (
    lancamento_id INTEGER NOT NULL,
    tag_id INTEGER NOT NULL,
    PRIMARY KEY (lancamento_id, tag_id)
);

CREATE TABLE IF NOT EXISTS cartoes_credito (
    id SERIAL PRIMARY KEY,
    nome TEXT NOT NULL,
    bandeira TEXT,
    dia_vencimento SMALLINT NOT NULL,
    dia_fechamento SMALLINT,
    limite NUMERIC(14,2),
    ativo SMALLINT NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS compras_cartao (
    id SERIAL PRIMARY KEY,
    cartao_id INTEGER NOT NULL REFERENCES cartoes_credito(id),
    descricao TEXT NOT NULL,
    valor_total NUMERIC(14,2) NOT NULL,
    parcelas INTEGER NOT NULL DEFAULT 1,
    data_compra DATE NOT NULL,
    primeira_fatura TEXT NOT NULL,
    observacao TEXT,
    criado_em TIMESTAMPTZ DEFAULT NOW()
);
"""
