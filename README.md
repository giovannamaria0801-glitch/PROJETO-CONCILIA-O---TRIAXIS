# TRIAXIS — Tax Reconciliation & Control (MVP)

Conciliação e diagnóstico fiscal entre **SAP**, **TaxOne** e **apuração assistida** (CBS/IBS), por importação de arquivos.
Somente leitura sobre os dados de origem: nada é gravado no SAP, no TaxOne ou em sistemas governamentais. **Não há integrações simuladas.**
Todos os dados em `demo/` são **fictícios** e não representam resultados reais da LANXESS.

## Instalação no Windows
1. Instale Python 3.11+ (python.org), marcando "Add python.exe to PATH".
2. No PowerShell, dentro da pasta do projeto:
   ```
   python -m venv .venv
   .venv\Scripts\activate
   pip install -r requirements.txt
   streamlit run app.py
   ```
3. O navegador abrirá em http://localhost:8501. O banco local é criado em `dados/triaxis.db`.

## Primeiro uso (demonstração)
Importação de arquivos → **Carregar dados de demonstração** → *Validar e normalizar* em cada aba → *Processar conciliação* →
Dashboard / Divergências → abrir uma divergência (ex.: NF-12345, CBS_RECUPERAR, diferença de R$ 500,00) → registrar causa, status e exportar em Relatórios.
Os arquivos de exemplo (`demo/*.xlsx`) também podem ser enviados manualmente; regenere-os com `python -m triaxis.demo_data`.

## Testes
```
python -m unittest discover -s tests -v
```
22 testes cobrindo: normalização (valores, datas, sinais, zeros à esquerda), preservação de originais, de-para (ambíguo, vigência, pendente ≠ aprovado),
ausência ≠ zero, duas fontes, tolerância, duplicidade, período, sinal, registro sem chave, causa só confirmada com evidência,
status/encerramento, reabertura de recorrentes, versões de regra com aprovação por outra pessoa, reprodutibilidade e exportação.

## Arquitetura (`triaxis/`)
`importacao` (leitura, mapeamento, validação, log) · `normalizacao` · `depara` · `conciliacao` (motor) · `diagnostico` · `regras` (versionadas) ·
`gestao` (fluxo de status) · `exportacao` (Excel/CSV) · `db` (SQLite) · `servico` (orquestração) · `app.py` (interface).

## Como a conciliação funciona
- **Documento**: registros de fontes distintas são ligados por chaves compartilhadas, em ordem de prioridade: chave de acesso → empresa+nº do documento → empresa+doc. contábil+item.
  Valor monetário nunca identifica documento. Sem identificador comum, o registro fica "não comparável" (nunca "conciliado").
- **Saldo**: soma por empresa/período/conta, usando apenas contas com de-para **aprovado e vigente** e sem ambiguidade.
- **Ausência ≠ zero**: fonte sem registro ou sem valor é "não comparável"; zero só quando o arquivo traz 0,00.
- **Diagnóstico**: categorias + hipóteses com a evidência que as sustenta. Causa só vira "confirmada" por ação do analista, com justificativa e registros de origem.
- **Rastreabilidade**: ID estável (DIV-AAAA-NNNNNN) por divergência; linha do arquivo de origem; log de normalização; cada processamento guarda os registros, o de-para e as regras usados e um hash do resultado — *Relatórios* reexecuta e confirma que o resultado é idêntico.

## Limitações conhecidas e pontos de configuração (não inventados)
- **Autenticação, perfis e segregação por empresa/estabelecimento: não implementados.** O campo "Usuário" só identifica o autor. Para multiusuário: autenticação corporativa + banco corporativo (trocar `db.py`).
- Política de retenção/exclusão e armazenamento seguro dos arquivos originais: a definir com TI/Segurança (o MVP guarda os registros normalizados + `dados_originais` por linha e o SHA-256 do arquivo).
- Regras específicas de IRPJ/CSLL (provisões, adições/exclusões, memória de cálculo), CBS/IBS (vigências, classificações) e elegibilidade de crédito dependem de **exemplos anonimizados dos relatórios reais** e de validação do Fiscal; o MVP oferece regras de tolerância por tributo e campos de configuração.
- Chaves compostas adicionais "aprovadas" (item 7.2.4), anexos de evidência, transferência por permissão e relatórios por conta/documento além dos incluídos no Excel ficam para a próxima iteração.
- "1.234" sem vírgula é lido como milhar (padrão BR); use o seletor de separador decimal quando o arquivo vier em formato americano.
