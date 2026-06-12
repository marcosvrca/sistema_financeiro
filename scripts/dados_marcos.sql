--
-- PostgreSQL database dump
--

\restrict DkxKzNwgDYANIReEUxfJ2xMrGYJsFI8H6BKmYCf66gDyhFJIbp0ffFex72jmD2e

-- Dumped from database version 16.14
-- Dumped by pg_dump version 16.14

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

--
-- Data for Name: configuracao; Type: TABLE DATA; Schema: public; Owner: -
--

SET SESSION AUTHORIZATION DEFAULT;

ALTER TABLE public.configuracao DISABLE TRIGGER ALL;

INSERT INTO public.configuracao (chave, valor) VALUES ('salario_mensal', '3455.40');
INSERT INTO public.configuracao (chave, valor) VALUES ('reserva_multiplicador_meses', '12');


ALTER TABLE public.configuracao ENABLE TRIGGER ALL;

--
-- Data for Name: contas_fixas; Type: TABLE DATA; Schema: public; Owner: -
--

ALTER TABLE public.contas_fixas DISABLE TRIGGER ALL;

INSERT INTO public.contas_fixas (id, nome, valor, dia_vencimento, categoria, historico_contem, ativo, observacao) VALUES (1, 'Aluguel', 350.00, 5, 'Contas fixas (utilidades)', 'Aluguel', 1, NULL);
INSERT INTO public.contas_fixas (id, nome, valor, dia_vencimento, categoria, historico_contem, ativo, observacao) VALUES (2, 'Internet', 75.00, 25, 'Contas fixas (utilidades)', 'Internet ', 1, NULL);
INSERT INTO public.contas_fixas (id, nome, valor, dia_vencimento, categoria, historico_contem, ativo, observacao) VALUES (3, 'Internet movel', 50.00, 20, 'Contas fixas (utilidades)', 'Internet  movel', 1, NULL);
INSERT INTO public.contas_fixas (id, nome, valor, dia_vencimento, categoria, historico_contem, ativo, observacao) VALUES (4, 'Agua', 90.00, 5, 'Contas fixas (utilidades)', 'Agua', 1, NULL);
INSERT INTO public.contas_fixas (id, nome, valor, dia_vencimento, categoria, historico_contem, ativo, observacao) VALUES (5, 'Energia', 150.00, 5, 'Contas fixas (utilidades)', 'Energia', 1, NULL);
INSERT INTO public.contas_fixas (id, nome, valor, dia_vencimento, categoria, historico_contem, ativo, observacao) VALUES (6, 'Netflix', 19.96, 5, 'Contas fixas (utilidades)', 'Netflix', 1, NULL);
INSERT INTO public.contas_fixas (id, nome, valor, dia_vencimento, categoria, historico_contem, ativo, observacao) VALUES (7, 'HBO Max', 14.96, 5, 'Contas fixas (utilidades)', 'HBO Max', 1, NULL);
INSERT INTO public.contas_fixas (id, nome, valor, dia_vencimento, categoria, historico_contem, ativo, observacao) VALUES (8, 'Revisão e manutenção do carro', 350.00, 5, 'Contas fixas (utilidades)', 'Revisão e manutenção do carro', 1, NULL);


ALTER TABLE public.contas_fixas ENABLE TRIGGER ALL;

--
-- Data for Name: contas_fixas_mes; Type: TABLE DATA; Schema: public; Owner: -
--

ALTER TABLE public.contas_fixas_mes DISABLE TRIGGER ALL;

INSERT INTO public.contas_fixas_mes (id, conta_fixa_id, mes, valor_real, pago, data_pagamento, observacao) VALUES (1, 4, '2026-05', 90.00, 1, '2026-05-27', NULL);
INSERT INTO public.contas_fixas_mes (id, conta_fixa_id, mes, valor_real, pago, data_pagamento, observacao) VALUES (2, 1, '2026-05', 350.00, 1, '2026-05-27', NULL);
INSERT INTO public.contas_fixas_mes (id, conta_fixa_id, mes, valor_real, pago, data_pagamento, observacao) VALUES (3, 5, '2026-05', 150.00, 1, '2026-05-27', NULL);
INSERT INTO public.contas_fixas_mes (id, conta_fixa_id, mes, valor_real, pago, data_pagamento, observacao) VALUES (5, 7, '2026-05', 14.96, 1, '2026-05-27', NULL);
INSERT INTO public.contas_fixas_mes (id, conta_fixa_id, mes, valor_real, pago, data_pagamento, observacao) VALUES (4, 6, '2026-05', 19.96, 1, '2026-05-27', NULL);
INSERT INTO public.contas_fixas_mes (id, conta_fixa_id, mes, valor_real, pago, data_pagamento, observacao) VALUES (6, 8, '2026-05', 350.00, 1, '2026-05-27', NULL);
INSERT INTO public.contas_fixas_mes (id, conta_fixa_id, mes, valor_real, pago, data_pagamento, observacao) VALUES (7, 2, '2026-05', 75.00, 1, '2026-05-27', NULL);
INSERT INTO public.contas_fixas_mes (id, conta_fixa_id, mes, valor_real, pago, data_pagamento, observacao) VALUES (15, 4, '2026-06', 89.64, 1, '2026-05-27', NULL);
INSERT INTO public.contas_fixas_mes (id, conta_fixa_id, mes, valor_real, pago, data_pagamento, observacao) VALUES (17, 5, '2026-06', 167.14, 1, '2026-05-27', NULL);


ALTER TABLE public.contas_fixas_mes ENABLE TRIGGER ALL;

--
-- Data for Name: lancamentos_manuais; Type: TABLE DATA; Schema: public; Owner: -
--

ALTER TABLE public.lancamentos_manuais DISABLE TRIGGER ALL;

INSERT INTO public.lancamentos_manuais (id, data, descricao, valor, tipo, categoria, criado_em) VALUES (3, '2026-05-04', 'Alimentação', 25.00, 'saida', 'Alimentação', '2026-05-26 13:06:27.10073+00');
INSERT INTO public.lancamentos_manuais (id, data, descricao, valor, tipo, categoria, criado_em) VALUES (4, '2026-05-04', 'Assinatura', 59.90, 'saida', 'PIX', '2026-05-26 13:07:07.162729+00');
INSERT INTO public.lancamentos_manuais (id, data, descricao, valor, tipo, categoria, criado_em) VALUES (6, '2026-05-05', 'Golpe', 1200.00, 'saida', 'PIX', '2026-05-26 13:11:30.164453+00');
INSERT INTO public.lancamentos_manuais (id, data, descricao, valor, tipo, categoria, criado_em) VALUES (7, '2026-05-05', 'Golpe', 1100.00, 'entrada', 'PIX', '2026-05-26 13:11:43.931416+00');
INSERT INTO public.lancamentos_manuais (id, data, descricao, valor, tipo, categoria, criado_em) VALUES (8, '2026-05-05', 'Golpe', 1100.00, 'saida', 'PIX', '2026-05-26 13:12:40.237488+00');
INSERT INTO public.lancamentos_manuais (id, data, descricao, valor, tipo, categoria, criado_em) VALUES (9, '2026-05-05', 'Alimentação - Recebido', 25.00, 'entrada', 'PIX', '2026-05-26 13:13:19.395763+00');
INSERT INTO public.lancamentos_manuais (id, data, descricao, valor, tipo, categoria, criado_em) VALUES (10, '2026-05-05', 'Alimentação - Recebido', 20.00, 'entrada', 'PIX', '2026-05-26 13:13:30.870159+00');
INSERT INTO public.lancamentos_manuais (id, data, descricao, valor, tipo, categoria, criado_em) VALUES (11, '2026-05-05', 'Alimentação', 50.00, 'saida', 'PIX', '2026-05-26 13:14:07.089223+00');
INSERT INTO public.lancamentos_manuais (id, data, descricao, valor, tipo, categoria, criado_em) VALUES (12, '2026-05-06', 'Alimentação', 56.00, 'saida', 'PIX', '2026-05-26 13:14:27.763873+00');
INSERT INTO public.lancamentos_manuais (id, data, descricao, valor, tipo, categoria, criado_em) VALUES (14, '2026-05-06', 'Alimentação - Recebido', 50.00, 'entrada', 'PIX', '2026-05-26 13:15:43.857169+00');
INSERT INTO public.lancamentos_manuais (id, data, descricao, valor, tipo, categoria, criado_em) VALUES (15, '2026-05-06', 'Golpe', 1000.00, 'entrada', 'PIX', '2026-05-26 13:16:38.984049+00');
INSERT INTO public.lancamentos_manuais (id, data, descricao, valor, tipo, categoria, criado_em) VALUES (16, '2026-05-06', 'Golpe', 1100.00, 'saida', 'PIX', '2026-05-26 13:16:54.77413+00');
INSERT INTO public.lancamentos_manuais (id, data, descricao, valor, tipo, categoria, criado_em) VALUES (18, '2026-05-07', 'Gasolina', 60.00, 'saida', 'Gasolina', '2026-05-26 13:17:49.286514+00');
INSERT INTO public.lancamentos_manuais (id, data, descricao, valor, tipo, categoria, criado_em) VALUES (19, '2026-05-08', 'Alimentação', 25.00, 'saida', 'Alimentação', '2026-05-26 13:18:28.75084+00');
INSERT INTO public.lancamentos_manuais (id, data, descricao, valor, tipo, categoria, criado_em) VALUES (20, '2026-05-08', 'Gasolina', 50.00, 'saida', 'Gasolina', '2026-05-26 13:19:11.914063+00');
INSERT INTO public.lancamentos_manuais (id, data, descricao, valor, tipo, categoria, criado_em) VALUES (21, '2026-05-09', 'Gasolina', 50.00, 'saida', 'Gasolina', '2026-05-26 13:19:28.461159+00');
INSERT INTO public.lancamentos_manuais (id, data, descricao, valor, tipo, categoria, criado_em) VALUES (22, '2026-05-09', 'Alimentação', 18.00, 'saida', 'Alimentação', '2026-05-26 13:19:47.872099+00');
INSERT INTO public.lancamentos_manuais (id, data, descricao, valor, tipo, categoria, criado_em) VALUES (25, '2026-05-11', 'Gasolina', 100.00, 'saida', 'Gasolina', '2026-05-26 13:21:29.219784+00');
INSERT INTO public.lancamentos_manuais (id, data, descricao, valor, tipo, categoria, criado_em) VALUES (27, '2026-05-11', 'Uber', 180.32, 'entrada', 'Salário / renda', '2026-05-26 13:29:11.921987+00');
INSERT INTO public.lancamentos_manuais (id, data, descricao, valor, tipo, categoria, criado_em) VALUES (29, '2026-05-11', 'Transferencia para anny', 3.00, 'saida', 'PIX', '2026-05-26 13:29:51.373201+00');
INSERT INTO public.lancamentos_manuais (id, data, descricao, valor, tipo, categoria, criado_em) VALUES (30, '2026-05-12', 'Alimentação', 25.00, 'saida', 'Alimentação', '2026-05-26 13:30:28.507462+00');
INSERT INTO public.lancamentos_manuais (id, data, descricao, valor, tipo, categoria, criado_em) VALUES (31, '2026-05-13', 'Geladeira do Gustavo', 105.21, 'saida', 'Cartão / compras', '2026-05-26 13:31:06.116197+00');
INSERT INTO public.lancamentos_manuais (id, data, descricao, valor, tipo, categoria, criado_em) VALUES (32, '2026-05-13', 'Manutenção de computador', 350.00, 'entrada', 'Salário / renda', '2026-05-26 13:40:15.281266+00');
INSERT INTO public.lancamentos_manuais (id, data, descricao, valor, tipo, categoria, criado_em) VALUES (33, '2026-05-13', 'Gasolina', 50.00, 'saida', 'Gasolina', '2026-05-26 13:40:42.302277+00');
INSERT INTO public.lancamentos_manuais (id, data, descricao, valor, tipo, categoria, criado_em) VALUES (35, '2026-05-15', 'Gasolin', 50.00, 'saida', 'Gasolina', '2026-05-26 13:41:38.580069+00');
INSERT INTO public.lancamentos_manuais (id, data, descricao, valor, tipo, categoria, criado_em) VALUES (36, '2026-05-15', 'Alimentação', 10.90, 'saida', 'Alimentação', '2026-05-26 13:41:53.966398+00');
INSERT INTO public.lancamentos_manuais (id, data, descricao, valor, tipo, categoria, criado_em) VALUES (37, '2026-05-16', 'Estacionamento Shopping', 14.00, 'saida', 'Outros', '2026-05-26 13:42:26.177384+00');
INSERT INTO public.lancamentos_manuais (id, data, descricao, valor, tipo, categoria, criado_em) VALUES (38, '2026-05-16', 'Compra de Cabide', 20.97, 'saida', 'Cartão / compras', '2026-05-26 13:42:51.880482+00');
INSERT INTO public.lancamentos_manuais (id, data, descricao, valor, tipo, categoria, criado_em) VALUES (40, '2026-05-17', 'Gasolina', 50.00, 'saida', 'Gasolina', '2026-05-26 13:44:02.948532+00');
INSERT INTO public.lancamentos_manuais (id, data, descricao, valor, tipo, categoria, criado_em) VALUES (41, '2026-05-17', 'Alimentação', 65.00, 'saida', 'Alimentação', '2026-05-26 13:44:17.330661+00');
INSERT INTO public.lancamentos_manuais (id, data, descricao, valor, tipo, categoria, criado_em) VALUES (44, '2026-05-18', 'Gasolina - Recebido', 100.00, 'entrada', 'Gasolina', '2026-05-26 13:45:44.319793+00');
INSERT INTO public.lancamentos_manuais (id, data, descricao, valor, tipo, categoria, criado_em) VALUES (45, '2026-05-18', 'Uber', 84.53, 'entrada', 'Salário / renda', '2026-05-26 13:45:58.28647+00');
INSERT INTO public.lancamentos_manuais (id, data, descricao, valor, tipo, categoria, criado_em) VALUES (46, '2026-05-18', 'Gasolina', 70.00, 'saida', 'Gasolina', '2026-05-26 13:46:36.410943+00');
INSERT INTO public.lancamentos_manuais (id, data, descricao, valor, tipo, categoria, criado_em) VALUES (47, '2026-05-18', 'Alimentação', 57.86, 'saida', 'Alimentação', '2026-05-26 13:46:54.407061+00');
INSERT INTO public.lancamentos_manuais (id, data, descricao, valor, tipo, categoria, criado_em) VALUES (48, '2026-05-19', 'Alimentação', 10.00, 'saida', 'Alimentação', '2026-05-26 13:47:29.517249+00');
INSERT INTO public.lancamentos_manuais (id, data, descricao, valor, tipo, categoria, criado_em) VALUES (50, '2026-05-19', 'Mensalidade mvGrafix', 49.90, 'entrada', 'Salário / renda', '2026-05-26 13:48:07.738006+00');
INSERT INTO public.lancamentos_manuais (id, data, descricao, valor, tipo, categoria, criado_em) VALUES (51, '2026-05-20', 'Gasolina', 50.00, 'saida', 'Gasolina', '2026-05-26 13:48:32.646303+00');
INSERT INTO public.lancamentos_manuais (id, data, descricao, valor, tipo, categoria, criado_em) VALUES (52, '2026-05-20', 'Farmacia', 12.19, 'saida', 'Saúde', '2026-05-26 13:48:55.91841+00');
INSERT INTO public.lancamentos_manuais (id, data, descricao, valor, tipo, categoria, criado_em) VALUES (53, '2026-05-21', 'Compra na feira', 25.00, 'saida', 'Alimentação', '2026-05-26 13:50:46.83362+00');
INSERT INTO public.lancamentos_manuais (id, data, descricao, valor, tipo, categoria, criado_em) VALUES (54, '2026-05-21', 'Compra na feira', 24.00, 'saida', 'Alimentação', '2026-05-26 13:50:57.925627+00');
INSERT INTO public.lancamentos_manuais (id, data, descricao, valor, tipo, categoria, criado_em) VALUES (55, '2026-05-22', 'Gasolina', 50.00, 'saida', 'Gasolina', '2026-05-26 13:51:15.767766+00');
INSERT INTO public.lancamentos_manuais (id, data, descricao, valor, tipo, categoria, criado_em) VALUES (58, '2026-05-22', 'Compra gelo aniversario da Laura', 10.00, 'saida', 'Cartão / compras', '2026-05-26 13:52:28.376313+00');
INSERT INTO public.lancamentos_manuais (id, data, descricao, valor, tipo, categoria, criado_em) VALUES (59, '2026-05-24', 'Internet - Recebido', 74.00, 'entrada', 'Transferência PIX', '2026-05-26 13:53:00.260459+00');
INSERT INTO public.lancamentos_manuais (id, data, descricao, valor, tipo, categoria, criado_em) VALUES (60, '2026-05-25', 'Recebido FGTS', 389.45, 'entrada', 'Salário / renda', '2026-05-26 13:53:41.893396+00');
INSERT INTO public.lancamentos_manuais (id, data, descricao, valor, tipo, categoria, criado_em) VALUES (64, '2026-05-25', 'Compra no shopping', 27.99, 'saida', 'Cartão / compras', '2026-05-26 13:55:16.007001+00');
INSERT INTO public.lancamentos_manuais (id, data, descricao, valor, tipo, categoria, criado_em) VALUES (63, '2026-05-25', 'Colação de grau', 135.00, 'saida', 'Transferência PIX', '2026-05-26 13:54:45.771461+00');
INSERT INTO public.lancamentos_manuais (id, data, descricao, valor, tipo, categoria, criado_em) VALUES (62, '2026-05-25', 'Colação de grau', 38.57, 'saida', 'Transferência PIX', '2026-05-26 13:54:25.618841+00');
INSERT INTO public.lancamentos_manuais (id, data, descricao, valor, tipo, categoria, criado_em) VALUES (61, '2026-05-25', 'Internet', 149.90, 'saida', 'Contas fixas (utilidades)', '2026-05-26 13:53:56.766735+00');
INSERT INTO public.lancamentos_manuais (id, data, descricao, valor, tipo, categoria, criado_em) VALUES (69, '2026-05-27', 'Agua - Mês 06', 89.64, 'saida', 'Contas fixas (utilidades)', '2026-05-27 14:26:27.028458+00');
INSERT INTO public.lancamentos_manuais (id, data, descricao, valor, tipo, categoria, criado_em) VALUES (57, '2026-05-22', 'Assinatura - Railway', 29.00, 'saida', 'Assinaturas', '2026-05-26 13:51:58.682182+00');
INSERT INTO public.lancamentos_manuais (id, data, descricao, valor, tipo, categoria, criado_em) VALUES (56, '2026-05-22', 'Mercado', 52.61, 'saida', 'Mercado', '2026-05-26 13:51:32.630091+00');
INSERT INTO public.lancamentos_manuais (id, data, descricao, valor, tipo, categoria, criado_em) VALUES (43, '2026-05-18', 'Assinatura - Spotify', 23.90, 'saida', 'Assinaturas', '2026-05-26 13:45:19.234319+00');
INSERT INTO public.lancamentos_manuais (id, data, descricao, valor, tipo, categoria, criado_em) VALUES (42, '2026-05-18', 'Assinatura - Cursor', 103.73, 'saida', 'Assinaturas', '2026-05-26 13:44:42.631806+00');
INSERT INTO public.lancamentos_manuais (id, data, descricao, valor, tipo, categoria, criado_em) VALUES (39, '2026-05-17', 'Mercado', 25.76, 'saida', 'Mercado', '2026-05-26 13:43:47.367076+00');
INSERT INTO public.lancamentos_manuais (id, data, descricao, valor, tipo, categoria, criado_em) VALUES (70, '2026-05-27', 'Jantar de formatura', 120.00, 'saida', 'Alimentação', '2026-05-27 14:26:52.062849+00');
INSERT INTO public.lancamentos_manuais (id, data, descricao, valor, tipo, categoria, criado_em) VALUES (34, '2026-05-14', 'Colação de Grau', 135.00, 'saida', 'Transferência PIX', '2026-05-26 13:41:17.670863+00');
INSERT INTO public.lancamentos_manuais (id, data, descricao, valor, tipo, categoria, criado_em) VALUES (17, '2026-05-07', 'Implantação do Sistema', 500.00, 'entrada', 'Salário / renda', '2026-05-26 13:17:15.784695+00');
INSERT INTO public.lancamentos_manuais (id, data, descricao, valor, tipo, categoria, criado_em) VALUES (2, '2026-05-04', 'Implantação  do Sistema', 1500.00, 'entrada', 'Salário / renda', '2026-05-26 13:06:03.739896+00');
INSERT INTO public.lancamentos_manuais (id, data, descricao, valor, tipo, categoria, criado_em) VALUES (5, '2026-05-04', 'Transferencia entre contas', 90.00, 'entrada', 'Transferência PIX', '2026-05-26 13:11:06.162227+00');
INSERT INTO public.lancamentos_manuais (id, data, descricao, valor, tipo, categoria, criado_em) VALUES (23, '2026-05-11', 'Gasolina  - Recebido', 100.00, 'entrada', 'Gasolina', '2026-05-26 13:20:22.68625+00');
INSERT INTO public.lancamentos_manuais (id, data, descricao, valor, tipo, categoria, criado_em) VALUES (65, '2026-05-26', 'Salario - ATI', 3455.40, 'entrada', 'Salário / renda', '2026-05-26 14:21:06.339144+00');
INSERT INTO public.lancamentos_manuais (id, data, descricao, valor, tipo, categoria, criado_em) VALUES (66, '2026-05-27', 'Aluguel - Mês 06', 350.00, 'saida', 'Moradia', '2026-05-27 14:24:54.912456+00');
INSERT INTO public.lancamentos_manuais (id, data, descricao, valor, tipo, categoria, criado_em) VALUES (67, '2026-05-27', 'Manutenção do carro - 3/10', 379.15, 'saida', 'Transporte', '2026-05-27 14:25:38.65634+00');
INSERT INTO public.lancamentos_manuais (id, data, descricao, valor, tipo, categoria, criado_em) VALUES (68, '2026-05-27', 'Ernegia - Mês 06', 167.14, 'saida', 'Contas fixas (utilidades)', '2026-05-27 14:26:11.668255+00');
INSERT INTO public.lancamentos_manuais (id, data, descricao, valor, tipo, categoria, criado_em) VALUES (71, '2026-05-27', 'Compra de mouse', 100.44, 'saida', 'Cartão / compras', '2026-05-27 16:15:51.784188+00');


ALTER TABLE public.lancamentos_manuais ENABLE TRIGGER ALL;

--
-- Data for Name: metas_financeiras; Type: TABLE DATA; Schema: public; Owner: -
--

ALTER TABLE public.metas_financeiras DISABLE TRIGGER ALL;

INSERT INTO public.metas_financeiras (id, tipo, nome, valor_alvo, valor_atual, multiplicador_meses, prazo, criado_em) VALUES (1, 'geral', 'Casamento', 20000.00, 100.00, NULL, NULL, '2026-05-27 12:03:18.80366+00');


ALTER TABLE public.metas_financeiras ENABLE TRIGGER ALL;

--
-- Data for Name: projetos; Type: TABLE DATA; Schema: public; Owner: -
--

ALTER TABLE public.projetos DISABLE TRIGGER ALL;

INSERT INTO public.projetos (id, nome, valor_alvo, valor_acumulado, aporte_mensal, prazo, ativo) VALUES (1, 'Viagem para o Rio de Janeiro', 5000.00, 200.00, NULL, NULL, 1);


ALTER TABLE public.projetos ENABLE TRIGGER ALL;

--
-- Name: contas_fixas_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.contas_fixas_id_seq', 8, true);


--
-- Name: contas_fixas_mes_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.contas_fixas_mes_id_seq', 18, true);


--
-- Name: lancamentos_manuais_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.lancamentos_manuais_id_seq', 71, true);


--
-- Name: metas_financeiras_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.metas_financeiras_id_seq', 1, true);


--
-- Name: projetos_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.projetos_id_seq', 1, true);


--
-- PostgreSQL database dump complete
--

\unrestrict DkxKzNwgDYANIReEUxfJ2xMrGYJsFI8H6BKmYCf66gDyhFJIbp0ffFex72jmD2e

