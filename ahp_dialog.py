# -*- coding: utf-8 -*-
"""
Diálogo principal do Plugin AHP para QGIS
Interface gráfica completa para cálculo de pesos AHP
"""
import csv
import json
import os

from qgis.PyQt.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QGridLayout,
    QPushButton, QLabel, QLineEdit, QTableWidget, QTableWidgetItem,
    QTextEdit, QSpinBox, QTabWidget, QWidget, QGroupBox,
    QComboBox, QMessageBox, QFileDialog, QHeaderView,
    QSplitter, QFrame, QScrollArea, QApplication
)
from qgis.PyQt.QtCore import Qt, pyqtSignal, QSettings
from qgis.PyQt.QtGui import QColor, QFont, QBrush

try:
    from qgis.core import QgsProject, QgsVectorLayer, QgsTask
    HAS_QGIS = True
except ImportError:
    HAS_QGIS = False

from .ahp_core import AHPCalculator, RI_TABLE


class AHPExportTask(QgsTask):
    """
    QgsTask para adicionar os campos de peso AHP na camada vetorial
    em background, garantindo thread safety e sem congelar a UI.
    """
    def __init__(self, layer_id, fields_to_add, layer_name):
        super().__init__(f"Exportando Pesos AHP para {layer_name}", QgsTask.CanCancel)
        self.layer_id = layer_id
        self.fields_to_add = fields_to_add
        self.layer_name = layer_name
        self.exception = None
        self.added = 0

    def run(self):
        try:
            lyr = QgsProject.instance().mapLayer(self.layer_id)
            if not lyr:
                raise Exception("Camada não encontrada na pilha de processos.")

            from qgis.core import QgsField
            from qgis.PyQt.QtCore import QVariant

            lyr.startEditing()
            for field_data in self.fields_to_add:
                fname = field_data['name']
                fval = field_data['value']

                if lyr.fields().indexOf(fname) == -1:
                    lyr.addAttribute(QgsField(fname, QVariant.Double))
                    self.added += 1

                    # Preenche features
                    for feat in lyr.getFeatures():
                        if self.isCanceled():
                            lyr.rollBack()
                            return False
                        lyr.changeAttributeValue(feat.id(), lyr.fields().indexOf(fname), fval)

            lyr.commitChanges()
            return True

        except Exception as e:
            self.exception = e
            return False

    def finished(self, result):
        if result:
            msg = "Pesos adicionados com sucesso."
            self.export_completed.emit(True, self.added, self.layer_name, msg)
        else:
            if self.exception:
                msg = str(self.exception)
            else:
                msg = "A tarefa foi cancelada pelo usuário."
            
            # Se a task possuir rollback pendente e não commitou
            lyr = QgsProject.instance().mapLayer(self.layer_id)
            if lyr and lyr.isEditable():
                lyr.rollBack()

            self.export_completed.emit(False, 0, self.layer_name, msg)

    # Sinal de conclusão da exportação
    export_completed = pyqtSignal(bool, int, str, str)


class AHPDialog(QDialog):
    """Diálogo principal da Calculadora AHP."""

    SAATY_VALUES = [
        ("1/9 – Extremamente menos importante", 1/9),
        ("1/8", 1/8),
        ("1/7 – Muito fortemente menos importante", 1/7),
        ("1/6", 1/6),
        ("1/5 – Fortemente menos importante", 1/5),
        ("1/4", 1/4),
        ("1/3 – Moderadamente menos importante", 1/3),
        ("1/2 – Levemente menos importante", 1/2),
        ("1 – Igual importância", 1),
        ("2 – Levemente mais importante", 2),
        ("3 – Moderadamente mais importante", 3),
        ("4", 4),
        ("5 – Fortemente mais importante", 5),
        ("6", 6),
        ("7 – Muito fortemente mais importante", 7),
        ("8", 8),
        ("9 – Extremamente mais importante", 9),
    ]

    def __init__(self, iface=None, parent=None):
        super().__init__(parent)
        self.iface = iface
        self.criteria = []
        self.calculator = None
        self.last_results = None
        self.matrix_combos = {}

        self.setWindowTitle("Calculadora AHP – Analytic Hierarchy Process")
        self.setMinimumSize(900, 680)
        self.setModal(False)

        self._build_ui()
        self._apply_styles()
        self._load_settings()

    # ──────────────────────────────────────────────
    # UI BUILDER
    # ──────────────────────────────────────────────

    def _build_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(8)
        main_layout.setContentsMargins(10, 10, 10, 10)

        # Header
        header = self._build_header()
        main_layout.addWidget(header)

        # Tabs
        self.tabs = QTabWidget()
        self.tabs.addTab(self._build_tab_criteria(), "1. Critérios")
        self.tabs.addTab(self._build_tab_matrix(), "2. Matriz de Comparação")
        self.tabs.addTab(self._build_tab_results(), "3. Resultados")
        self.tabs.addTab(self._build_tab_reference(), "📖 Escala Saaty")
        self.tabs.addTab(self._build_tab_guide(), "📋 Guia Prático")
        main_layout.addWidget(self.tabs)

        # Bottom buttons
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        self.btn_calculate = QPushButton("⚡ Calcular Pesos")
        self.btn_calculate.setObjectName("btn_primary")
        self.btn_calculate.clicked.connect(self._on_calculate)
        self.btn_calculate.setEnabled(False)

        self.btn_export = QPushButton("💾 Exportar CSV")
        self.btn_export.setObjectName("btn_secondary")
        self.btn_export.clicked.connect(self._on_export)
        self.btn_export.setEnabled(False)

        self.btn_reset = QPushButton("🔄 Reiniciar")
        self.btn_reset.clicked.connect(self._on_reset)

        self.btn_close = QPushButton("✕ Fechar")
        self.btn_close.clicked.connect(self.close)

        for btn in [self.btn_calculate, self.btn_export, self.btn_reset, self.btn_close]:
            btn.setMinimumHeight(36)
            btn.setMinimumWidth(130)
            btn_layout.addWidget(btn)

        main_layout.addLayout(btn_layout)

        # Ler versão do metadata.txt dinamicamente
        version = "1.0.0"  # fallback
        try:
            import configparser
            plugin_dir = os.path.dirname(__file__)
            metadata_path = os.path.join(plugin_dir, "metadata.txt")
            if os.path.exists(metadata_path):
                config = configparser.ConfigParser()
                config.read(metadata_path, encoding='utf-8')
                if config.has_option('general', 'version'):
                    version = config.get('general', 'version')
        except Exception:
            pass

        # Rodapé padronizado
        lbl_footer = QLabel(
            f"Calculadora AHP v{version}  |  Clayton Igarashi "
            "<geoigarashi@gmail.com>"
        )
        lbl_footer.setAlignment(Qt.AlignCenter)
        lbl_footer.setStyleSheet("color: gray; font-size: 10px;")
        main_layout.addWidget(lbl_footer)

    def _build_header(self):
        frame = QFrame()
        frame.setObjectName("header_frame")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(12, 8, 12, 8)

        title = QLabel("🔢 Calculadora AHP – Analytic Hierarchy Process")
        title.setObjectName("header_title")
        title.setAlignment(Qt.AlignCenter)

        subtitle = QLabel(
            "Método de Saaty para cálculo de pesos em análise multicritério (MCDA)"
        )
        subtitle.setObjectName("header_subtitle")
        subtitle.setAlignment(Qt.AlignCenter)

        layout.addWidget(title)
        layout.addWidget(subtitle)
        return frame

    def _build_tab_criteria(self):
        """Aba 1: Definição dos critérios."""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setSpacing(10)

        # Número de critérios
        num_group = QGroupBox("Número de Critérios")
        num_layout = QHBoxLayout(num_group)

        num_layout.addWidget(QLabel("Quantidade de critérios:"))
        self.spin_num = QSpinBox()
        self.spin_num.setRange(2, 15)
        self.spin_num.setValue(4)
        self.spin_num.setMinimumWidth(80)
        num_layout.addWidget(self.spin_num)

        btn_gen = QPushButton("Gerar Campos")
        btn_gen.setObjectName("btn_secondary")
        btn_gen.clicked.connect(self._on_generate_fields)
        num_layout.addWidget(btn_gen)
        num_layout.addStretch()
        layout.addWidget(num_group)

        # Campos dos critérios
        criteria_group = QGroupBox("Nomes dos Critérios")
        self.criteria_layout = QGridLayout(criteria_group)
        layout.addWidget(criteria_group)

        # Info
        info = QLabel(
            "ℹ️  Preencha os nomes dos critérios e clique em "
            "<b>Gerar Matriz de Comparação</b> para avançar."
        )
        info.setWordWrap(True)
        layout.addWidget(info)

        # Botão avançar
        btn_advance = QPushButton("▶  Gerar Matriz de Comparação")
        btn_advance.setObjectName("btn_primary")
        btn_advance.clicked.connect(self._on_advance_to_matrix)
        btn_advance.setMinimumHeight(38)
        layout.addWidget(btn_advance)

        layout.addStretch()

        # Gerar campos iniciais
        self._generate_criteria_fields(4)
        return widget

    def _build_tab_matrix(self):
        """Aba 2: Matriz de comparação par a par."""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        info = QLabel(
            "Preencha a metade superior da matriz comparando cada par de critérios. "
            "A metade inferior (recíprocos) é preenchida automaticamente. "
            "Use a <b>Escala Saaty</b> como referência."
        )
        info.setWordWrap(True)
        layout.addWidget(info)

        # Tabela
        self.matrix_table = QTableWidget()
        self.matrix_table.setAlternatingRowColors(True)
        layout.addWidget(self.matrix_table)

        # Legenda
        legend = QLabel(
            "🔵 Diagonal principal (= 1) | 🟡 Metade superior: insira os valores | "
            "⬜ Metade inferior: calculada automaticamente"
        )
        legend.setWordWrap(True)
        layout.addWidget(legend)

        return widget

    def _build_tab_results(self):
        """Aba 3: Resultados."""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        splitter = QSplitter(Qt.Vertical)

        # Tabela de pesos
        weights_group = QGroupBox("Pesos Calculados")
        weights_layout = QVBoxLayout(weights_group)
        self.weights_table = QTableWidget()
        self.weights_table.setColumnCount(4)
        self.weights_table.setHorizontalHeaderLabels(
            ["Critério", "Peso", "Peso (%)", "Barra Visual"]
        )
        self.weights_table.horizontalHeader().setStretchLastSection(True)
        self.weights_table.setEditTriggers(QTableWidget.NoEditTriggers)
        weights_layout.addWidget(self.weights_table)
        splitter.addWidget(weights_group)

        # Texto detalhado
        detail_group = QGroupBox("Relatório Detalhado")
        detail_layout = QVBoxLayout(detail_group)
        self.results_text = QTextEdit()
        self.results_text.setReadOnly(True)
        self.results_text.setFont(QFont("Courier New", 10))
        detail_layout.addWidget(self.results_text)
        splitter.addWidget(detail_group)

        splitter.setSizes([250, 350])
        layout.addWidget(splitter)

        # Fórmula para Calculadora Raster
        formula_group = QGroupBox("Fórmula para a Calculadora Raster do QGIS")
        formula_layout = QVBoxLayout(formula_group)

        formula_info = QLabel(
            "Copie a expressão abaixo e cole na Calculadora Raster "
            "(Raster → Calculadora Raster). Cada raster deve estar "
            "normalizado na mesma escala antes de aplicar os pesos."
        )
        formula_info.setWordWrap(True)
        formula_layout.addWidget(formula_info)

        self.formula_text = QTextEdit()
        self.formula_text.setReadOnly(True)
        self.formula_text.setFont(QFont("Courier New", 9))
        self.formula_text.setMaximumHeight(90)
        self.formula_text.setPlaceholderText(
            "A fórmula será gerada automaticamente após o cálculo dos pesos..."
        )
        formula_layout.addWidget(self.formula_text)

        btn_copy = QPushButton("📋 Copiar Fórmula")
        btn_copy.setObjectName("btn_secondary")
        btn_copy.setMaximumWidth(160)
        btn_copy.clicked.connect(self._on_copy_formula)
        formula_layout.addWidget(btn_copy)

        layout.addWidget(formula_group)

        # QGIS Layer integration
        if HAS_QGIS and self.iface:
            qgis_group = QGroupBox("Exportar para Camada QGIS")
            qgis_layout = QHBoxLayout(qgis_group)
            qgis_layout.addWidget(QLabel("Camada vetorial:"))
            self.combo_layer = QComboBox()
            self._refresh_layers()
            qgis_layout.addWidget(self.combo_layer)
            btn_add = QPushButton("Adicionar campos de peso")
            btn_add.clicked.connect(self._on_add_to_layer)
            qgis_layout.addWidget(btn_add)
            btn_refresh = QPushButton("🔄")
            btn_refresh.setMaximumWidth(36)
            btn_refresh.clicked.connect(self._refresh_layers)
            qgis_layout.addWidget(btn_refresh)
            layout.addWidget(qgis_group)

        return widget

    def _build_tab_reference(self):
        """Aba 4: Referência da escala Saaty."""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        title = QLabel("<b>Escala Fundamental de Saaty (1980)</b>")
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)

        table = QTableWidget(9, 3)
        table.setHorizontalHeaderLabels(["Intensidade", "Descrição", "Recíproco"])
        table.setEditTriggers(QTableWidget.NoEditTriggers)
        table.horizontalHeader().setStretchLastSection(True)
        table.verticalHeader().setVisible(False)

        saaty_data = [
            ("1", "Igual importância", "1"),
            ("2", "Importância levemente superior", "1/2"),
            ("3", "Moderadamente mais importante", "1/3"),
            ("4", "Entre 3 e 5", "1/4"),
            ("5", "Fortemente mais importante", "1/5"),
            ("6", "Entre 5 e 7", "1/6"),
            ("7", "Muito fortemente mais importante", "1/7"),
            ("8", "Entre 7 e 9", "1/8"),
            ("9", "Extremamente mais importante", "1/9"),
        ]

        for row, (intens, desc, recip) in enumerate(saaty_data):
            table.setItem(row, 0, QTableWidgetItem(intens))
            table.setItem(row, 1, QTableWidgetItem(desc))
            table.setItem(row, 2, QTableWidgetItem(recip))
            if row % 2 == 0:
                for col in range(3):
                    table.item(row, col).setBackground(QColor(240, 248, 255))

        layout.addWidget(table)

        # RI Table
        ri_title = QLabel("<b>Índices de Consistência Randômica (IR) – Saaty</b>")
        ri_title.setAlignment(Qt.AlignCenter)
        layout.addWidget(ri_title)

        ri_table = QTableWidget(1, 13)
        ri_table.setVerticalHeaderLabels(["IR"])
        headers = [str(n) for n in range(3, 16)]
        ri_table.setHorizontalHeaderLabels(headers)
        ri_table.setEditTriggers(QTableWidget.NoEditTriggers)
        ri_table.setMaximumHeight(80)

        for col, n in enumerate(range(3, 16)):
            item = QTableWidgetItem(str(RI_TABLE.get(n, "-")))
            item.setTextAlignment(Qt.AlignCenter)
            ri_table.setItem(0, col, item)

        layout.addWidget(ri_table)

        # Fórmulas
        formulas = QLabel(
            "<b>Fórmulas AHP:</b><br>"
            "• Peso (w<sub>i</sub>) = média das linhas da matriz normalizada<br>"
            "• λ<sub>max</sub> = média de (Aw / w)<br>"
            "• IC = (λ<sub>max</sub> - n) / (n - 1)<br>"
            "• RC = IC / IR   →   RC &lt; 0.10 = consistente"
        )
        formulas.setWordWrap(True)
        layout.addWidget(formulas)
        layout.addStretch()

        return widget

    # ──────────────────────────────────────────────
    # CRITERIA MANAGEMENT
    # ──────────────────────────────────────────────

    def _generate_criteria_fields(self, n):
        """Gera os campos de texto para os nomes dos critérios."""
        # Limpar layout existente
        while self.criteria_layout.count():
            item = self.criteria_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        self.criteria_inputs = []
        default_names = [
            "Declividade", "Uso do Solo", "Distância Rios",
            "Geologia", "Precipitação", "Temperatura",
            "Altitude", "Solo", "Vegetação", "Infraestrutura",
            "Densidade Pop.", "Erosão", "Permeabilidade", "Cobertura", "Aspecto"
        ]

        cols = 3
        for i in range(n):
            row = i // cols
            col = (i % cols) * 2
            lbl = QLabel(f"Critério {i+1}:")
            inp = QLineEdit()
            inp.setPlaceholderText(f"Ex: {default_names[i]}")
            if i < len(default_names):
                inp.setText(default_names[i])
            inp.setMinimumWidth(150)
            self.criteria_layout.addWidget(lbl, row, col)
            self.criteria_layout.addWidget(inp, row, col + 1)
            self.criteria_inputs.append(inp)

    def _on_generate_fields(self):
        n = self.spin_num.value()
        self._generate_criteria_fields(n)

    def _on_advance_to_matrix(self):
        """Coleta nomes e gera a tabela de matriz."""
        names = [inp.text().strip() for inp in self.criteria_inputs]
        if any(n == "" for n in names):
            QMessageBox.warning(
                self, "Atenção",
                "Preencha todos os nomes dos critérios antes de continuar."
            )
            return

        if len(set(names)) != len(names):
            QMessageBox.warning(
                self, "Atenção",
                "Os nomes dos critérios devem ser únicos."
            )
            return

        self.criteria = names
        self.calculator = AHPCalculator(self.criteria)
        self._build_matrix_table()
        self.btn_calculate.setEnabled(True)
        self.tabs.setCurrentIndex(1)

    # ──────────────────────────────────────────────
    # MATRIX TABLE
    # ──────────────────────────────────────────────

    def _build_matrix_table(self):
        """Constrói a tabela da matriz de comparação."""
        n = len(self.criteria)
        self.matrix_table.setRowCount(n)
        self.matrix_table.setColumnCount(n)
        self.matrix_table.setHorizontalHeaderLabels(self.criteria)
        self.matrix_table.setVerticalHeaderLabels(self.criteria)

        # Armazenar widgets de células superiores
        self.matrix_combos = {}

        for i in range(n):
            for j in range(n):
                if i == j:
                    # Diagonal: sempre 1
                    item = QTableWidgetItem("1")
                    item.setFlags(Qt.ItemIsEnabled)
                    item.setTextAlignment(Qt.AlignCenter)
                    item.setBackground(QColor(173, 216, 230))  # azul claro
                    self.matrix_table.setItem(i, j, item)

                elif i < j:
                    # Metade superior: ComboBox de valores Saaty
                    combo = QComboBox()
                    for label, _ in self.SAATY_VALUES:
                        combo.addItem(label)
                    # Valor padrão: 1 (igual)
                    combo.setCurrentIndex(8)  # índice do "1 – Igual importância"
                    combo.currentIndexChanged.connect(
                        lambda idx, r=i, c=j: self._on_combo_changed(r, c, idx)
                    )
                    self.matrix_table.setCellWidget(i, j, combo)
                    self.matrix_combos[(i, j)] = combo

                else:
                    # Metade inferior: recíproco automático
                    item = QTableWidgetItem("1.0000")
                    item.setFlags(Qt.ItemIsEnabled)
                    item.setTextAlignment(Qt.AlignCenter)
                    item.setBackground(QColor(245, 245, 245))
                    self.matrix_table.setItem(i, j, item)

        self.matrix_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.matrix_table.verticalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)

    def _on_combo_changed(self, row, col, idx):
        """Atualiza recíproco quando combo muda."""
        if self.calculator is None:
            return
        value = self.SAATY_VALUES[idx][1]
        self.calculator.set_comparison(row, col, value)

        # Atualizar célula recíproca
        recip_item = self.matrix_table.item(col, row)
        if recip_item:
            recip_item.setText(f"{1.0/value:.4f}")

    # ──────────────────────────────────────────────
    # CALCULATE
    # ──────────────────────────────────────────────

    def _on_calculate(self):
        """Executa o cálculo AHP e exibe resultados."""
        if self.calculator is None:
            QMessageBox.warning(self, "Erro", "Gere a matriz primeiro.")
            return

        # Sincronizar todos os combos com a calculadora
        for (i, j), combo in self.matrix_combos.items():
            idx = combo.currentIndex()
            value = self.SAATY_VALUES[idx][1]
            self.calculator.set_comparison(i, j, value)

        # Validar
        valid, msg = self.calculator.validate_matrix()
        if not valid:
            QMessageBox.critical(self, "Erro na Matriz", msg)
            return

        # Calcular
        self.last_results = self.calculator.calculate_weights()

        # Exibir resultados
        self._display_results(self.last_results)
        self.btn_export.setEnabled(True)
        self.tabs.setCurrentIndex(2)

        # Aviso de inconsistência
        if not self.last_results['is_consistent']:
            QMessageBox.warning(
                self, "⚠ Inconsistência Detectada",
                f"Razão de Consistência (RC) = {self.last_results['rc']:.4f}\n\n"
                "O valor RC deve ser menor que 0.10 para uma matriz consistente.\n\n"
                "Revise as comparações na aba 'Matriz de Comparação'."
            )

    def _display_results(self, results):
        """Preenche a aba de resultados com os dados calculados."""
        weights = results['weights']
        criteria = results['criteria']
        n = results['n']

        # Tabela de pesos
        self.weights_table.setRowCount(n)
        for i in range(n):
            w = weights[i]
            bar = "█" * int(w * 40) + "░" * (40 - int(w * 40))

            self.weights_table.setItem(i, 0, QTableWidgetItem(criteria[i]))
            self.weights_table.setItem(i, 1, QTableWidgetItem(f"{w:.4f}"))
            self.weights_table.setItem(i, 2, QTableWidgetItem(f"{w*100:.2f}%"))

            bar_item = QTableWidgetItem(bar)
            bar_item.setFont(QFont("Courier New", 8))
            if results['is_consistent']:
                bar_item.setForeground(QBrush(QColor(34, 139, 34)))
            else:
                bar_item.setForeground(QBrush(QColor(200, 100, 0)))
            self.weights_table.setItem(i, 3, bar_item)

        self.weights_table.resizeColumnsToContents()

        # Texto detalhado
        text = self.calculator.format_results_text(results)
        text += "\n\nMATRIZ DE COMPARAÇÃO:\n"
        text += "-" * 50 + "\n"
        mat = self.calculator.get_matrix()

        header = "          " + "".join(f"{c[:8]:>10}" for c in criteria)
        text += header + "\n"
        for i, crit in enumerate(criteria):
            row_str = f"{crit[:8]:<10}" + "".join(f"{mat[i][j]:>10.4f}" for j in range(n))
            text += row_str + "\n"

        self.results_text.setPlainText(text)

        # Gerar fórmula para Calculadora Raster
        formula_parts = []
        for crit, w in zip(criteria, weights):
            layer_name = crit.lower().replace(" ", "_").replace("-", "_")
            formula_parts.append(f'({w:.4f} * "{layer_name}@1")')
        self.formula_text.setPlainText(" +\n".join(formula_parts))

    # ──────────────────────────────────────────────
    # EXPORT
    # ──────────────────────────────────────────────

    def _on_export(self):
        """Exporta os resultados para CSV."""
        if self.last_results is None:
            return

        path, _ = QFileDialog.getSaveFileName(
            self, "Salvar resultados AHP", "ahp_pesos.csv",
            "Arquivos CSV (*.csv)"
        )
        if not path:
            return

        try:
            with open(path, 'w', newline='', encoding='utf-8-sig') as f:
                writer = csv.writer(f, delimiter=';')

                # Cabeçalho
                writer.writerow(["RESULTADOS AHP – Analytic Hierarchy Process"])
                writer.writerow([])

                # Pesos
                writer.writerow(["Critério", "Peso", "Peso (%)"])
                for crit, w in zip(self.last_results['criteria'], self.last_results['weights']):
                    writer.writerow([crit, f"{w:.6f}", f"{w*100:.4f}"])

                writer.writerow([])
                writer.writerow(["MÉTRICAS DE CONSISTÊNCIA"])
                writer.writerow(["lambda_max", f"{self.last_results['lambda_max']:.4f}"])
                writer.writerow(["IC", f"{self.last_results['ic']:.4f}"])
                writer.writerow(["IR", f"{self.last_results['ri']:.4f}"])
                writer.writerow(["RC", f"{self.last_results['rc']:.4f}"])
                writer.writerow(["Consistente?",
                                  "Sim (RC < 0.10)" if self.last_results['is_consistent']
                                  else "Não (RC ≥ 0.10)"])

                writer.writerow([])
                writer.writerow(["MATRIZ DE COMPARAÇÃO"])
                n = self.last_results['n']
                mat = self.calculator.get_matrix()
                header = [""] + self.last_results['criteria']
                writer.writerow(header)
                for i, crit in enumerate(self.last_results['criteria']):
                    row = [crit] + [f"{mat[i][j]:.4f}" for j in range(n)]
                    writer.writerow(row)

            QMessageBox.information(
                self, "Exportado",
                f"Resultados salvos com sucesso em:\n{path}"
            )
        except Exception as e:
            QMessageBox.critical(self, "Erro ao Exportar", str(e))

    # ──────────────────────────────────────────────
    # QGIS LAYER INTEGRATION
    # ──────────────────────────────────────────────

    def _refresh_layers(self):
        """Atualiza o combo de camadas QGIS."""
        if not HAS_QGIS:
            return
        self.combo_layer.clear()
        layers = QgsProject.instance().mapLayers().values()
        for lyr in layers:
            if isinstance(lyr, QgsVectorLayer):
                self.combo_layer.addItem(lyr.name(), lyr.id())

    def _on_add_to_layer(self):
        """Adiciona campos de peso à camada vetorial selecionada."""
        if self.last_results is None:
            self._show_message("Atenção", "Calcule os pesos primeiro.", level="warning")
            return
        if not HAS_QGIS:
            return

        layer_id = self.combo_layer.currentData()
        if not layer_id:
            self._show_message("Atenção", "Selecione uma camada vetorial.", level="warning")
            return

        lyr = QgsProject.instance().mapLayer(layer_id)
        if not lyr:
            self._show_message("Erro", "Camada não encontrada.", level="critical")
            return

        # Aviso se matriz inconsistente
        if not self.last_results['is_consistent']:
            reply = QMessageBox.warning(
                self, "⚠ Matriz Inconsistente",
                f"A Razão de Consistência (RC = {self.last_results['rc']:.4f}) "
                "é maior que 0.10.\n\n"
                "Recomenda-se revisar as comparações antes de exportar.\n\n"
                "Deseja exportar mesmo assim?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )
            if reply == QMessageBox.No:
                return

        # Confirmação antes de modificar a camada
        reply = QMessageBox.question(
            self, "Confirmar Exportação",
            f"Adicionar campos de peso AHP à camada '{lyr.name()}'?\n\n"
            "Esta ação modifica a tabela de atributos da camada.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.Yes
        )
        if reply == QMessageBox.No:
            return

        from qgis.core import QgsApplication

        # Prepara dados para a task
        fields_to_add = []
        for crit, w in zip(self.last_results['criteria'], self.last_results['weights']):
            fname = f"ahp_{crit[:10].replace(' ', '_').lower()}"
            fields_to_add.append({'name': fname, 'value': float(w)})

        # Inicia a Task para não travar a UI principal
        task = AHPExportTask(
            layer_id=layer_id,
            fields_to_add=fields_to_add,
            layer_name=lyr.name()
        )
        task.export_completed.connect(self._on_export_task_completed)
        task.taskTerminated.connect(self._on_export_task_terminated)
        
        QgsApplication.taskManager().addTask(task)
        self._log_message(f"Iniciada a gravação de pesos na camada: {lyr.name()}")

    def _on_export_task_completed(self, success, added_count, layer_name, msg):
        """Slot chamado quando a QgsTask finaliza."""
        if success:
            self._show_message(
                "Sucesso",
                f"{added_count} campo(s) de peso AHP adicionado(s) à camada '{layer_name}'.",
                level="success"
            )
            self._log_message(f"Pesos adicionados com sucesso na camada '{layer_name}'.")
        else:
            self._show_message("Erro", f"Erro na escrita: {msg}", level="critical")
            self._log_message(f"Falha ao escrever na camada '{layer_name}': {msg}", level="critical")

    def _on_export_task_terminated(self):
        """Slot chamado caso a QgsTask falhe inesperadamente."""
        self._show_message("Erro", "A tarefa de exportação falhou ou foi cancelada.", level="critical")
        self._log_message("Tarefa de exportação cancelada/falha.", level="critical")

    def _show_message(self, title, message, level="info"):
        """Mostra notificações usando a MessageBar do QGIS quando disponível."""
        if HAS_QGIS and self.iface:
            from qgis.core import Qgis
            qgis_level = Qgis.MessageLevel.Info
            if level == "warning":
                qgis_level = Qgis.MessageLevel.Warning
            elif level == "critical":
                qgis_level = Qgis.MessageLevel.Critical
            elif level == "success":
                qgis_level = Qgis.MessageLevel.Success
            
            self.iface.messageBar().pushMessage(title, message, level=qgis_level, duration=5)
        else:
            # Fallback seguro caso não esteja rodando dentro do QGIS
            if level == "warning":
                QMessageBox.warning(self, title, message)
            elif level == "critical":
                QMessageBox.critical(self, title, message)
            else:
                QMessageBox.information(self, title, message)

    def _log_message(self, message, level="info"):
        """Registra no painel Log de Mensagens do QGIS."""
        if HAS_QGIS:
            from qgis.core import QgsMessageLog, Qgis
            qgis_level = Qgis.MessageLevel.Info
            if level == "warning":
                qgis_level = Qgis.MessageLevel.Warning
            elif level == "critical":
                qgis_level = Qgis.MessageLevel.Critical
            
            QgsMessageLog.logMessage(message, "AHP Plugin", level=qgis_level)

    # ──────────────────────────────────────────────
    # RESET
    # ──────────────────────────────────────────────

    def _on_reset(self):
        reply = QMessageBox.question(
            self, "Confirmar Reset",
            "Deseja reiniciar todos os dados?",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            self.criteria = []
            self.calculator = None
            self.last_results = None
            self.matrix_combos = {}
            self.btn_calculate.setEnabled(False)
            self.btn_export.setEnabled(False)
            self._generate_criteria_fields(self.spin_num.value())
            self.matrix_table.clearContents()
            self.matrix_table.setRowCount(0)
            self.weights_table.setRowCount(0)
            self.results_text.clear()
            self.tabs.setCurrentIndex(0)

    # ──────────────────────────────────────────────
    # COPY FORMULA
    # ──────────────────────────────────────────────

    def _on_copy_formula(self):
        """Copia a fórmula da Calculadora Raster para a área de transferência."""
        formula = self.formula_text.toPlainText().strip()
        if not formula:
            QMessageBox.information(
                self, "Atenção", "Calcule os pesos primeiro para gerar a fórmula."
            )
            return
        QApplication.clipboard().setText(formula)
        QMessageBox.information(
            self, "Copiado",
            "Fórmula copiada! Cole-a na Calculadora Raster do QGIS\n"
            "(Raster → Calculadora Raster)."
        )

    # ──────────────────────────────────────────────
    # GUIDE TAB
    # ──────────────────────────────────────────────

    def _build_tab_guide(self):
        """Aba: Guia Prático de uso pós-cálculo."""
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)

        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setSpacing(12)
        layout.setContentsMargins(16, 16, 16, 16)

        def section(title, html_body):
            grp = QGroupBox(title)
            grp.setObjectName("guide_group")
            lbl = QLabel(html_body)
            lbl.setWordWrap(True)
            lbl.setTextFormat(Qt.RichText)
            lbl.setOpenExternalLinks(False)
            inner = QVBoxLayout(grp)
            inner.addWidget(lbl)
            return grp

        # ── 1. O que é o AHP? ─────────────────────────────────────────────
        layout.addWidget(section(
            "🔢  O que é o Método AHP?",
            "O <b>Analytic Hierarchy Process (AHP)</b>, proposto por Thomas L. Saaty (1980), "
            "é um método de tomada de decisão multicritério que transforma julgamentos "
            "subjetivos de importância relativa em <b>pesos numéricos</b> que somam 1,0 (100%).<br><br>"
            "No contexto do <b>Geoprocessamento</b>, esses pesos são aplicados a camadas "
            "raster representando diferentes variáveis espaciais — gerando mapas de "
            "aptidão, vulnerabilidade, risco ou qualquer índice composto."
        ))

        # ── 2. Fluxo de trabalho ──────────────────────────────────────────
        layout.addWidget(section(
            "🗺️  Fluxo de Trabalho AHP-GIS",
            "<ol>"
            "<li><b>Definir o objetivo</b>: Ex.: mapa de risco de deslizamento, aptidão agrícola.</li>"
            "<li><b>Listar critérios</b>: Variáveis espaciais que influenciam o fenômeno "
            "(declividade, uso do solo, geologia, distância a drenagens…).</li>"
            "<li><b>Preparar os rasters</b>: Normalizar cada camada para uma escala comum "
            "(ex.: 0–1 ou 1–5) antes de aplicar os pesos.</li>"
            "<li><b>Calcular pesos no AHP</b>: Preencher a matriz de comparação e verificar RC.</li>"
            "<li><b>Aplicar na Calculadora Raster</b>: Usar a fórmula gerada na aba Resultados.</li>"
            "<li><b>Interpretar e validar</b>: Comparar o mapa com dados de campo ou amostras.</li>"
            "</ol>"
        ))

        # ── 3. Como preencher a matriz ────────────────────────────────────
        layout.addWidget(section(
            "✏️  Como Preencher a Matriz de Comparação",
            "Para cada par de critérios (linha A vs coluna B), responda:<br>"
            "<i>\"Quanto A é mais importante que B para atingir o objetivo?\"</i><br><br>"
            "<b>Dicas práticas:</b>"
            "<ul>"
            "<li>Comece comparando os pares mais óbvios (os extremos de importância).</li>"
            "<li>Mantenha consistência transitiva: se <b>A &gt; B</b> e <b>B &gt; C</b>, "
            "então A deve ser claramente mais importante que C.</li>"
            "<li>Evite usar os valores extremos (9) em muitos pares — isso tende a gerar "
            "alta inconsistência.</li>"
            "<li>Se a RC ultrapassar 0,10, revise primeiro os julgamentos mais intensos "
            "(valores 7, 8 ou 9) e tente suavizá-los.</li>"
            "<li>Com mais de 7 critérios, a manutenção da consistência torna-se "
            "progressivamente mais difícil.</li>"
            "</ul>"
        ))

        # ── 4. Razão de Consistência ──────────────────────────────────────
        layout.addWidget(section(
            "📐  Interpretando a Razão de Consistência (RC)",
            "<table cellspacing='6'>"
            "<tr><th align='left'>RC</th><th align='left'>Interpretação</th>"
            "<th align='left'>Ação</th></tr>"
            "<tr><td><b>&lt; 0,05</b></td><td>Excelente consistência</td>"
            "<td>Prossiga com confiança.</td></tr>"
            "<tr><td><b>0,05 – 0,10</b></td><td>Consistência aceitável</td>"
            "<td>Resultados válidos; revisão opcional.</td></tr>"
            "<tr><td><b>0,10 – 0,20</b></td><td>Consistência limítrofe</td>"
            "<td>Recomenda-se revisar os julgamentos.</td></tr>"
            "<tr><td><b>&gt; 0,20</b></td><td>Inconsistência elevada</td>"
            "<td>Revisar antes de usar os pesos.</td></tr>"
            "</table>"
        ))

        # ── 5. Normalização dos rasters ───────────────────────────────────
        layout.addWidget(section(
            "🔲  Normalização dos Rasters (pré-requisito)",
            "Antes de aplicar os pesos AHP, todos os rasters devem estar na "
            "<b>mesma escala de valores</b>. Métodos comuns:<br><br>"
            "<b>1. Normalização linear (min-max), escala 0–1:</b><br>"
            "<code>&nbsp;&nbsp;(\"raster@1\" - mínimo) / (máximo - mínimo)</code><br><br>"
            "<b>2. Reclassificação por faixas (1–5 ou 1–9):</b><br>"
            "Atribua notas de 1 a 5 (ou 1 a 9) a faixas de valores usando "
            "<i>Raster → Reclassificação</i>. Valores maiores devem indicar "
            "maior intensidade do fator analisado.<br><br>"
            "<b>3. Fuzzy membership:</b><br>"
            "Transforma valores em graus de pertinência (0–1) usando funções "
            "lineares, sigmoidal ou gaussiana — mais indicado quando os limites "
            "entre classes são gradientes, não cortes abruptos."
        ))

        # ── 6. Usando a fórmula na Calculadora Raster ─────────────────────
        layout.addWidget(section(
            "🧮  Usando a Fórmula na Calculadora Raster do QGIS",
            "Após calcular os pesos, vá à aba <b>3. Resultados</b> e copie a "
            "fórmula gerada automaticamente.<br><br>"
            "<b>Passos no QGIS:</b>"
            "<ol>"
            "<li>Menu <b>Raster → Calculadora Raster…</b></li>"
            "<li>Cole a fórmula no campo de expressão.</li>"
            "<li>Certifique-se de que os nomes das camadas na fórmula correspondem "
            "exatamente aos nomes das camadas carregadas no QGIS.</li>"
            "<li>Defina o arquivo de saída e a extensão/resolução de referência.</li>"
            "<li>Clique em <b>OK</b> para gerar o mapa.</li>"
            "</ol>"
            "<b>Exemplo (3 critérios):</b><br>"
            "<code>"
            "(0.6479 * \"declividade@1\") +<br>"
            "(0.2299 * \"uso_solo@1\") +<br>"
            "(0.1222 * \"hidrologia@1\")"
            "</code><br><br>"
            "⚠️ <i>O sufixo <b>@1</b> indica a banda 1 do raster. "
            "Ajuste para <b>@2</b>, <b>@3</b>… se o dado estiver em outra banda.</i>"
        ))

        # ── 7. Interpretação do mapa resultante ───────────────────────────
        layout.addWidget(section(
            "🗺️  Interpretando o Mapa Resultante",
            "<b>O que o mapa representa?</b><br>"
            "Cada pixel recebe um valor igual à <i>soma ponderada</i> dos valores "
            "dos rasters de entrada. O resultado é um índice contínuo — quanto maior "
            "o valor, maior a intensidade do fenômeno modelado.<br><br>"
            "<b>Faixa de valores:</b><br>"
            "Depende da escala de normalização escolhida:<br>"
            "• Rasters 0–1 → resultado entre 0 e 1<br>"
            "• Rasters 1–5 → resultado entre 1 e 5<br><br>"
            "<b>Classificação do resultado:</b><br>"
            "Aplique <i>Raster → Reclassificação</i> ou use simbologia por intervalos "
            "para criar classes (ex.: muito baixo / baixo / médio / alto / muito alto).<br><br>"
            "<b>Validação:</b><br>"
            "Compare o mapa com pontos de ocorrência conhecidos "
            "(ex.: histórico de deslizamentos, amostras de campo) para avaliar a "
            "qualidade do modelo antes de usá-lo para tomada de decisão."
        ))

        # ── 8. Referência ─────────────────────────────────────────────────
        layout.addWidget(section(
            "📚  Referências",
            "• Saaty, T.L. (1980). <i>The Analytic Hierarchy Process.</i> McGraw-Hill.<br>"
            "• Saaty, T.L. (1990). How to make a decision: The Analytic Hierarchy Process. "
            "<i>European Journal of Operational Research</i>, 48(1), 9–26.<br>"
            "• Eastman, J.R. (2006). <i>IDRISI Andes Guide to GIS and Image Processing.</i> "
            "Clark Labs."
        ))

        layout.addStretch()
        scroll.setWidget(container)
        return scroll

    # ──────────────────────────────────────────────
    # SETTINGS PERSISTENCE
    # ──────────────────────────────────────────────

    def _save_settings(self):
        """Persiste critérios e valores da matriz no QSettings."""
        s = QSettings("AHPPlugin", "AHPDialog")
        s.setValue("criteria_count", self.spin_num.value())
        names = [inp.text() for inp in self.criteria_inputs]
        s.setValue("criteria_names", json.dumps(names))
        if self.matrix_combos:
            combo_vals = {
                f"{i},{j}": combo.currentIndex()
                for (i, j), combo in self.matrix_combos.items()
            }
            s.setValue("matrix_combos", json.dumps(combo_vals))
        else:
            s.remove("matrix_combos")

    def _load_settings(self):
        """Restaura critérios e matriz do QSettings."""
        s = QSettings("AHPPlugin", "AHPDialog")

        count = s.value("criteria_count", 4, type=int)
        self.spin_num.setValue(count)
        self._generate_criteria_fields(count)

        names_json = s.value("criteria_names", "[]")
        try:
            names = json.loads(names_json)
            for i, inp in enumerate(self.criteria_inputs):
                if i < len(names) and names[i]:
                    inp.setText(names[i])
        except Exception:
            pass

        # Restaura matriz se os critérios estiverem completos e únicos
        combo_json = s.value("matrix_combos", "{}")
        try:
            combo_vals = json.loads(combo_json)
            if combo_vals:
                names_filled = [inp.text().strip() for inp in self.criteria_inputs]
                if all(names_filled) and len(set(names_filled)) == len(names_filled):
                    self.criteria = names_filled
                    self.calculator = AHPCalculator(self.criteria)
                    self._build_matrix_table()
                    self.btn_calculate.setEnabled(True)
                    for key, idx in combo_vals.items():
                        parts = key.split(",")
                        i, j = int(parts[0]), int(parts[1])
                        if (i, j) in self.matrix_combos:
                            self.matrix_combos[(i, j)].setCurrentIndex(idx)
        except Exception:
            pass

    def closeEvent(self, event):
        """Salva configurações ao fechar o diálogo."""
        self._save_settings()
        super().closeEvent(event)

    # ──────────────────────────────────────────────
    # STYLES
    # ──────────────────────────────────────────────

    def _apply_styles(self):
        self.setStyleSheet("""
            QDialog {
                background-color: #f5f5f5;
                font-family: 'Segoe UI', Arial, sans-serif;
            }
            #header_frame {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #1a5276, stop:1 #2e86c1);
                border-radius: 6px;
                padding: 6px;
            }
            #header_title {
                color: white;
                font-size: 16px;
                font-weight: bold;
            }
            #header_subtitle {
                color: #aed6f1;
                font-size: 11px;
            }
            QTabWidget::pane {
                border: 1px solid #c0c0c0;
                border-radius: 4px;
                background: white;
            }
            QTabBar::tab {
                background: #e8e8e8;
                padding: 8px 16px;
                border-top-left-radius: 4px;
                border-top-right-radius: 4px;
                margin-right: 2px;
            }
            QTabBar::tab:selected {
                background: #2e86c1;
                color: white;
                font-weight: bold;
            }
            QGroupBox {
                font-weight: bold;
                border: 1px solid #c0c0c0;
                border-radius: 4px;
                margin-top: 10px;
                padding-top: 10px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 8px;
                padding: 0 4px;
                color: #1a5276;
            }
            QPushButton#btn_primary {
                background-color: #2e86c1;
                color: white;
                border: none;
                border-radius: 4px;
                font-weight: bold;
                padding: 6px 12px;
            }
            QPushButton#btn_primary:hover {
                background-color: #1a5276;
            }
            QPushButton#btn_primary:disabled {
                background-color: #aab7c4;
            }
            QPushButton#btn_secondary {
                background-color: #27ae60;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 6px 12px;
            }
            QPushButton#btn_secondary:hover {
                background-color: #1e8449;
            }
            QPushButton#btn_secondary:disabled {
                background-color: #aab7c4;
            }
            QPushButton {
                border: 1px solid #c0c0c0;
                border-radius: 4px;
                padding: 6px 12px;
                background: white;
            }
            QPushButton:hover {
                background: #e8e8e8;
            }
            QTableWidget {
                gridline-color: #d0d0d0;
                border: 1px solid #c0c0c0;
            }
            QHeaderView::section {
                background-color: #2e86c1;
                color: white;
                padding: 6px;
                border: none;
                font-weight: bold;
            }
            QTextEdit {
                border: 1px solid #c0c0c0;
                border-radius: 4px;
                background: #fafafa;
            }
        """)
