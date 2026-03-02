# Plugin AHP para QGIS
> **Calculadora de Pesos – Analytic Hierarchy Process (AHP)**
> Versão 1.1.0 · Clayton Igarashi

---

## O que é o AHP?

O **Processo Analítico Hierárquico (AHP)**, desenvolvido por Thomas L. Saaty (1980),
é um método de apoio à decisão multicritério que permite estruturar problemas complexos,
comparar alternativas e calcular pesos para critérios de forma sistemática e consistente.

No **Geoprocessamento**, os pesos AHP são aplicados a camadas raster normalizadas para
gerar mapas de aptidão, vulnerabilidade, risco ou qualquer índice espacial composto.

---

## Telas do Plugin

### 1. Critérios
Define a quantidade e os nomes dos critérios que serão avaliados.
![Aba 1 - Critérios](docs/screenshot_1.png)

### 2. Matriz de Comparação
Comparação par a par entre os critérios utilizando a escala fundamental de Saaty.
![Aba 2 - Matriz de Comparação](docs/screenshot_2.png)

### 3. Resultados
Visualização dos pesos calculados, verificação da Razão de Consistência (RC),
fórmula automática para a Calculadora Raster e exportação de dados.
![Aba 3 - Resultados](docs/screenshot_3.png)

### 4. Escala Saaty
Material de referência rápida com a escala de intensidade de importância e fórmulas.
![Aba 4 - Escala Saaty](docs/screenshot_4.png)

### 5. Guia Prático *(novo em v1.1.0)*
Documentação integrada com fluxo de trabalho AHP-GIS, normalização de rasters,
uso da Calculadora Raster, interpretação do mapa resultado e referências bibliográficas.

---

## Instalação

### Método 1 – Via QGIS (recomendado)
1. Abra o QGIS
2. Menu **Complementos → Gerenciar e Instalar Complementos**
3. Clique em **Instalar a partir de um ZIP**
4. Selecione o arquivo `ahp_qgis_plugin_v1.1.0.zip`
5. Clique em **Instalar**

### Método 2 – Manual
1. Extraia o conteúdo do ZIP
2. Copie a pasta `ahp_qgis_plugin` para o diretório de plugins do QGIS:
   - **Windows:** `C:\Users\<user>\AppData\Roaming\QGIS\QGIS3\profiles\default\python\plugins\`
   - **Linux:** `~/.local/share/QGIS/QGIS3/profiles/default/python/plugins/`
   - **macOS:** `~/Library/Application Support/QGIS/QGIS3/profiles/default/python/plugins/`
3. Reinicie o QGIS e ative o plugin em **Complementos → Gerenciar e Instalar Complementos**

### Dependência
O plugin requer **NumPy** (geralmente já incluído no QGIS):
```bash
# Se necessário, instale via OSGeo4W Shell (Windows):
pip install numpy
```

---

## Como Usar

### Passo 1 – Definir Critérios
- Informe a **quantidade de critérios** (2 a 15)
- Preencha os **nomes** de cada critério
- Clique em **Gerar Matriz de Comparação**
- Os critérios e configurações são **salvos automaticamente** entre sessões

### Passo 2 – Preencher a Matriz
- Para cada par de critérios, selecione o valor na **Escala Saaty** (1 a 9)
- Os valores recíprocos são preenchidos automaticamente
- Use a aba **Escala Saaty** como referência

| Valor | Significado |
|-------|-------------|
| 1     | Igual importância |
| 3     | Moderadamente mais importante |
| 5     | Fortemente mais importante |
| 7     | Muito fortemente mais importante |
| 9     | Extremamente mais importante |
| 2,4,6,8 | Valores intermediários |

### Passo 3 – Calcular e Verificar
- Clique em **⚡ Calcular Pesos**
- Verifique a **Razão de Consistência (RC)**:
  - RC < 0.05 → Excelente consistência ✔
  - RC 0.05–0.10 → Consistência aceitável ✔
  - RC ≥ 0.10 → Revisão recomendada ✘

### Passo 4 – Aplicar na Calculadora Raster *(novo em v1.1.0)*
Na aba **Resultados**, a fórmula ponderada é gerada automaticamente:
```
(0.6479 * "declividade@1") +
(0.2299 * "uso_solo@1") +
(0.1222 * "hidrologia@1")
```
- Clique em **📋 Copiar Fórmula** e cole diretamente na **Calculadora Raster do QGIS**
  (Menu: Raster → Calculadora Raster)
- Certifique-se de que os rasters estão normalizados na mesma escala antes de aplicar os pesos
- Consulte a aba **📋 Guia Prático** para orientações sobre normalização e interpretação

### Passo 5 – Exportar
- **💾 Exportar CSV**: salva pesos e matriz em arquivo `.csv`
- **Exportar para Camada QGIS**: adiciona campos de peso em uma camada vetorial
  (solicita confirmação e avisa se RC ≥ 0.10)

---

## Fórmulas Matemáticas

```
Peso (wᵢ) = média das linhas da matriz normalizada
           = (1/n) × Σⱼ [aᵢⱼ / Σₖ aₖⱼ]

λ_max = média de [(A × w)ᵢ / wᵢ]

IC (Índice de Consistência) = (λ_max - n) / (n - 1)

RC (Razão de Consistência) = IC / IR

Critério: RC < 0.10 → Consistente
```

**Índices de Consistência Randômica (IR) de Saaty:**

| n | 3    | 4    | 5    | 6    | 7    | 8    | 9    | 10   |
|---|------|------|------|------|------|------|------|------|
|IR | 0.58 | 0.90 | 1.12 | 1.24 | 1.32 | 1.41 | 1.45 | 1.49 |

---

## Estrutura de Arquivos

```
ahp_qgis_plugin/
├── __init__.py        # Ponto de entrada do plugin QGIS
├── ahp_plugin.py      # Classe principal do plugin
├── ahp_dialog.py      # Interface gráfica completa (PyQt5)
├── ahp_core.py        # Núcleo matemático do AHP
├── test_ahp.py        # Testes independentes da lógica AHP
├── metadata.txt       # Metadados do plugin QGIS
├── icon.png           # Ícone do plugin
├── docs/              # Capturas de tela e documentação
└── README.md          # Este arquivo
```

---

## Histórico de Versões

### v1.1.0 (2026-03-02)
**Novas funcionalidades:**
- Aba **📋 Guia Prático** com 8 seções: conceito AHP, fluxo de trabalho AHP-GIS,
  dicas de preenchimento da matriz, tabela de interpretação da RC, métodos de
  normalização de rasters, uso da Calculadora Raster, interpretação do mapa e referências
- **Fórmula automática para Calculadora Raster** na aba Resultados — gera a expressão
  ponderada com os nomes e pesos calculados, com botão **📋 Copiar Fórmula**
- **QSettings**: critérios, quantidade e valores da matriz são restaurados entre sessões
- Confirmação antes de adicionar campos em camada vetorial
- Aviso ao exportar matriz inconsistente (RC ≥ 0.10) com opção de cancelar

**Correções críticas:**
- Resolve merge conflict em `ahp_dialog.py` que impedia carregamento do plugin
- Adiciona `import os` ausente (necessário para leitura da versão no rodapé)
- Move `pyqtSignal` para nível de módulo; renomeia `taskCompleted` → `export_completed`
  para evitar conflito com o sinal nativo de `QgsTask`
- `test_ahp.py`: importa `AHPCalculator` de `ahp_core` em vez de duplicar a lógica
- `metadata.txt`: `category` corrigido de `Raster` para `Analysis`;
  `qgisMinimumVersion` atualizado de `3.0` para `3.16`
- `matrix_combos` agora é limpo corretamente ao reiniciar

### v1.0.1
- Release inicial pública

---

## Referências

> Saaty, T.L. (1980). *The Analytic Hierarchy Process*. McGraw-Hill, New York.
> Saaty, T.L. (1990). How to make a decision: The Analytic Hierarchy Process.
> *European Journal of Operational Research*, 48(1), 9–26.

---

## Versão e Compatibilidade

- **Versão do Plugin:** 1.1.0
- **QGIS mínimo:** 3.16
- **Python:** 3.6+
- **Dependências:** NumPy, PyQt5 (incluídos no QGIS)
