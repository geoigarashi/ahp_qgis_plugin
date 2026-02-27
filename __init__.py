# -*- coding: utf-8 -*-
"""
AHP Weight Calculator Plugin for QGIS
Calcula pesos usando o método AHP (Analytic Hierarchy Process)
"""

def classFactory(iface):
    """Carrega o plugin AHP no QGIS."""
    from .ahp_plugin import AHPPlugin
    return AHPPlugin(iface)
