# -*- coding: utf-8 -*-
"""
Núcleo do cálculo AHP (Analytic Hierarchy Process)
"""
import numpy as np


# Índice de Consistência Randômica (RI) de Saaty
RI_TABLE = {
    1: 0.00, 2: 0.00, 3: 0.58, 4: 0.90, 5: 1.12,
    6: 1.24, 7: 1.32, 8: 1.41, 9: 1.45, 10: 1.49,
    11: 1.51, 12: 1.48, 13: 1.56, 14: 1.57, 15: 1.59
}

# Escala fundamental de Saaty (valor: (descrição, recíproco))
SAATY_SCALE = {
    1: "Igual importância",
    2: "Importância levemente superior",
    3: "Moderadamente mais importante",
    4: "Moderadamente mais importante (forte)",
    5: "Fortemente mais importante",
    6: "Fortemente mais importante (plus)",
    7: "Muito fortemente mais importante",
    8: "Muito fortemente mais importante (plus)",
    9: "Extremamente mais importante"
}


class AHPCalculator:
    """Classe para cálculos AHP."""

    def __init__(self, criteria):
        """
        Inicializa a calculadora AHP.
        
        :param criteria: Lista de strings com os nomes dos critérios.
        """
        self.criteria = criteria
        self.n = len(criteria)
        self.matrix = np.ones((self.n, self.n))

    def set_comparison(self, i, j, value):
        """
        Define a comparação entre critério i e critério j.
        
        :param i: índice do critério na linha
        :param j: índice do critério na coluna
        :param value: valor da comparação (1-9 ou 1/9 a 1/1)
        """
        self.matrix[i][j] = value
        self.matrix[j][i] = 1.0 / value

    def calculate_weights(self):
        """
        Calcula os pesos utilizando o método do vetor próprio (eigenvector).
        
        :return: dict com pesos, lambda_max, IC, RC e status de consistência
        """
        # Normalizar cada coluna
        col_sums = self.matrix.sum(axis=0)
        normalized = self.matrix / col_sums

        # Calcular vetor de prioridades (média das linhas)
        weights = normalized.mean(axis=1)

        # Calcular lambda_max
        weighted_sum = self.matrix.dot(weights)
        ratio = weighted_sum / weights
        lambda_max = ratio.mean()

        # Calcular Índice de Consistência (IC)
        ic = (lambda_max - self.n) / (self.n - 1) if self.n > 1 else 0

        # Obter RI para n critérios
        ri = RI_TABLE.get(self.n, 1.59)

        # Calcular Razão de Consistência (RC)
        rc = ic / ri if ri > 0 else 0

        # Verificar consistência (RC < 0.10 é aceitável)
        is_consistent = rc < 0.10

        return {
            'weights': weights,
            'criteria': self.criteria,
            'lambda_max': lambda_max,
            'ic': ic,
            'ri': ri,
            'rc': rc,
            'is_consistent': is_consistent,
            'n': self.n
        }

    def get_matrix(self):
        """Retorna a matriz de comparação atual."""
        return self.matrix

    def validate_matrix(self):
        """
        Valida se a matriz está devidamente preenchida.
        
        :return: (bool, str) - válida ou não, e mensagem de erro
        """
        # Verificar se diagonal é 1
        for i in range(self.n):
            if abs(self.matrix[i][i] - 1.0) > 1e-9:
                return False, f"A diagonal principal deve ser 1 (critério {i+1})"

        # Verificar reciprocidade
        for i in range(self.n):
            for j in range(i+1, self.n):
                if abs(self.matrix[i][j] * self.matrix[j][i] - 1.0) > 1e-6:
                    return False, (
                        f"Erro de reciprocidade entre critério {i+1} e {j+1}: "
                        f"{self.matrix[i][j]:.4f} x {self.matrix[j][i]:.4f} ≠ 1"
                    )

        # Verificar valores no intervalo aceitável
        for i in range(self.n):
            for j in range(self.n):
                if self.matrix[i][j] <= 0:
                    return False, f"Valor inválido na posição ({i+1},{j+1}): deve ser positivo"

        return True, "Matriz válida"

    def format_results_text(self, results):
        """
        Formata os resultados como texto.
        
        :param results: dict retornado por calculate_weights()
        :return: string formatada com os resultados
        """
        lines = []
        lines.append("=" * 50)
        lines.append("   RESULTADOS - MÉTODO AHP")
        lines.append("=" * 50)
        lines.append("")
        lines.append("PESOS CALCULADOS:")
        lines.append("-" * 30)

        for i, (crit, weight) in enumerate(zip(results['criteria'], results['weights'])):
            lines.append(f"  {crit:25s}: {weight:.4f}  ({weight*100:.2f}%)")

        lines.append("")
        lines.append("MÉTRICAS DE CONSISTÊNCIA:")
        lines.append("-" * 30)
        lines.append(f"  λ máx (lambda_max): {results['lambda_max']:.4f}")
        lines.append(f"  n (nº critérios)  : {results['n']}")
        lines.append(f"  IC (Índice Consist): {results['ic']:.4f}")
        lines.append(f"  IR (Índice Rand.)  : {results['ri']:.4f}")
        lines.append(f"  RC (Razão Consist.): {results['rc']:.4f}")
        lines.append("")

        if results['is_consistent']:
            lines.append("  ✔ CONSISTENTE (RC < 0.10)")
        else:
            lines.append("  ✘ INCONSISTENTE (RC ≥ 0.10)")
            lines.append("  → Revise as comparações par a par!")

        lines.append("")
        lines.append("Referência: Saaty, T.L. (1980)")
        lines.append("=" * 50)

        return "\n".join(lines)
