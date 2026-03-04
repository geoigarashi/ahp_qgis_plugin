# -*- coding: utf-8 -*-
"""
Classe principal do Plugin AHP para QGIS
"""
import os
from qgis.PyQt.QtWidgets import QAction
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtCore import QCoreApplication


class AHPPlugin:
    """Plugin AHP para cálculo de pesos por Processo Analítico Hierárquico."""

    def __init__(self, iface):
        self.iface = iface
        self.plugin_dir = os.path.dirname(__file__)
        self.action = None
        self.dialog = None

    def tr(self, message):
        return QCoreApplication.translate('AHPPlugin', message)

    def initGui(self):
        """Cria a entrada no menu e ícone na barra de ferramentas."""
        icon_path = os.path.join(self.plugin_dir, 'icon.png')
        self.action = QAction(
            QIcon(icon_path),
            self.tr('Calculadora AHP'),
            self.iface.mainWindow()
        )
        self.action.setStatusTip(self.tr('Abre a Calculadora de Pesos AHP'))
        self.action.triggered.connect(self.run)

        self.iface.addPluginToMenu("Ferramentas Geo", self.action)
        self.iface.addToolBarIcon(self.action)

    def unload(self):
        """Remove o plugin do menu e barra de ferramentas."""
        self.iface.removePluginMenu("Ferramentas Geo", self.action)
        self.iface.removeToolBarIcon(self.action)
        del self.action

    def run(self):
        """Abre o diálogo principal do plugin."""
        from .ahp_dialog import AHPDialog
        self.dialog = AHPDialog(self.iface)
        self.dialog.show()
