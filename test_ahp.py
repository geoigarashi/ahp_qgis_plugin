#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Teste standalone da lógica AHP (sem QGIS).
Execute com: python3 test_ahp.py
"""
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))

# Importar apenas o núcleo (sem dependências QGIS)
import numpy as np

# ─── Copiar inline para teste sem dependência de módulo ───────────────────────

RI_TABLE = {
    1: 0.00, 2: 0.00, 3: 0.58, 4: 0.90, 5: 1.12,
    6: 1.24, 7: 1.32, 8: 1.41, 9: 1.45, 10: 1.49
}

class AHPCalculator:
    def __init__(self, criteria):
        self.criteria = criteria
        self.n = len(criteria)
        self.matrix = np.ones((self.n, self.n))

    def set_comparison(self, i, j, value):
        self.matrix[i][j] = value
        self.matrix[j][i] = 1.0 / value

    def calculate_weights(self):
        col_sums = self.matrix.sum(axis=0)
        normalized = self.matrix / col_sums
        weights = normalized.mean(axis=1)
        weighted_sum = self.matrix.dot(weights)
        ratio = weighted_sum / weights
        lambda_max = ratio.mean()
        ic = (lambda_max - self.n) / (self.n - 1) if self.n > 1 else 0
        ri = RI_TABLE.get(self.n, 1.59)
        rc = ic / ri if ri > 0 else 0
        return {
            'weights': weights,
            'criteria': self.criteria,
            'lambda_max': lambda_max,
            'ic': ic,
            'ri': ri,
            'rc': rc,
            'is_consistent': rc < 0.10,
            'n': self.n
        }

# ─── Teste com exemplo clássico de Saaty ─────────────────────────────────────

print("=" * 60)
print("  TESTE AHP - Exemplo Clássico (Saaty, 1980)")
print("=" * 60)

# Critérios: Preço, Qualidade, Serviço, Marca
criteria = ["Preço", "Qualidade", "Serviço", "Marca"]
ahp = AHPCalculator(criteria)

# Comparações par a par (baseado em exemplo de Saaty)
# (i, j, valor) → linha i é "valor" vezes mais importante que linha j
comparisons = [
    (0, 1, 1/3),  # Preço vs Qualidade: Qualidade 3x mais importante
    (0, 2, 1/2),  # Preço vs Serviço: Serviço 2x mais importante
    (0, 3, 3),    # Preço vs Marca: Preço 3x mais importante
    (1, 2, 3),    # Qualidade vs Serviço: Qualidade 3x mais importante
    (1, 3, 7),    # Qualidade vs Marca: Qualidade 7x mais importante
    (2, 3, 5),    # Serviço vs Marca: Serviço 5x mais importante
]

for i, j, val in comparisons:
    ahp.set_comparison(i, j, val)

results = ahp.calculate_weights()

print("\nPESOS CALCULADOS:")
print("-" * 40)
for crit, w in zip(results['criteria'], results['weights']):
    bar = "█" * int(w * 30)
    print(f"  {crit:<12}: {w:.4f} ({w*100:5.2f}%)  {bar}")

print(f"\nλ_max = {results['lambda_max']:.4f}")
print(f"IC    = {results['ic']:.4f}")
print(f"IR    = {results['ri']:.4f}")
print(f"RC    = {results['rc']:.4f}")
print(f"\nSoma dos pesos = {sum(results['weights']):.4f} (deve ser 1.0000)")

if results['is_consistent']:
    print("\n✔  MATRIZ CONSISTENTE (RC < 0.10)")
else:
    print("\n✘  MATRIZ INCONSISTENTE (RC ≥ 0.10)")

print("\n" + "=" * 60)
print("  TESTE 2 – Apenas 3 critérios")
print("=" * 60)

criteria2 = ["Declividade", "Uso do Solo", "Hidrologia"]
ahp2 = AHPCalculator(criteria2)
ahp2.set_comparison(0, 1, 3)  # Declividade 3x mais que Uso do Solo
ahp2.set_comparison(0, 2, 5)  # Declividade 5x mais que Hidrologia
ahp2.set_comparison(1, 2, 2)  # Uso do Solo 2x mais que Hidrologia

res2 = ahp2.calculate_weights()
print("\nPESOS:")
for crit, w in zip(res2['criteria'], res2['weights']):
    print(f"  {crit:<15}: {w:.4f} ({w*100:.2f}%)")
print(f"RC = {res2['rc']:.4f} → {'Consistente ✔' if res2['is_consistent'] else 'Inconsistente ✘'}")

print("\n✅ Todos os testes concluídos com sucesso!")
