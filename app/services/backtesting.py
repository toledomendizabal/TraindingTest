"""Backtesting and analysis service."""
import os
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from loguru import logger
from app.core.config import settings
from app.models.signal import BacktestResult
from app.services.excel_manager import excel_manager


class BacktestingService:
    """Service for running backtesting analysis on closed signals."""

    def __init__(self):
        self.reports_dir = settings.REPORTS_DIR
        os.makedirs(self.reports_dir, exist_ok=True)

    async def run_daily_backtest(self) -> BacktestResult:
        """Run daily backtesting analysis at 23:59."""
        today = datetime.now().strftime("%Y-%m-%d")
        logger.info(f"Running daily backtest for {today}")

        closed_signals = excel_manager.get_closed_signals(start_date=today)
        result = self._analyze_signals(closed_signals, today)

        # Save report
        self._save_report(result, "daily")

        # Send notifications
        from app.services.telegram_service import telegram_service
        await telegram_service.send_backtesting_report(result.model_dump())

        return result

    async def run_weekly_backtest(self) -> BacktestResult:
        """Run weekly backtesting analysis (Friday 11 PM)."""
        today = datetime.now()
        week_start = (today - timedelta(days=today.weekday())).strftime("%Y-%m-%d")
        date_str = today.strftime("%Y-%m-%d")

        logger.info(f"Running weekly backtest from {week_start}")

        closed_signals = excel_manager.get_closed_signals(start_date=week_start)
        result = self._analyze_signals(closed_signals, date_str)

        # Save report
        self._save_report(result, "weekly")

        # Send notifications
        from app.services.telegram_service import telegram_service
        await telegram_service.send_backtesting_report(result.model_dump())

        return result

    def _analyze_signals(self, signals: List[Dict], date: str) -> BacktestResult:
        """Analyze a list of closed signals."""
        total = len(signals)

        if total == 0:
            return BacktestResult(
                date=date,
                total_signals=0,
                recommendations=["No hay señales cerradas para analizar"],
                indicator_adjustments=[
                    "Considerar reducir el umbral mínimo de indicadores",
                    "Verificar la conectividad con la API de datos",
                    "Revisar si los activos están en horario de mercado"
                ]
            )

        # Calculate metrics
        profits = [s.get("profit_loss", 0) for s in signals]
        wins = [p for p in profits if p > 0]
        losses = [p for p in profits if p < 0]

        winning = len(wins)
        losing = len(losses)
        win_rate = (winning / total * 100) if total > 0 else 0

        total_profit = sum(wins) if wins else 0
        total_loss = abs(sum(losses)) if losses else 0
        profit_factor = (total_profit / total_loss) if total_loss > 0 else 0
        net_profit = total_profit - total_loss

        # Calculate drawdown
        cumulative = np.cumsum(profits)
        peak = np.maximum.accumulate(cumulative) if len(cumulative) > 0 else np.array([0])
        drawdown = (peak - cumulative)
        max_drawdown = (float(np.max(drawdown)) / settings.INITIAL_CAPITAL * 100) if len(drawdown) > 0 else 0

        # Calculate Sharpe Ratio
        if len(profits) > 1:
            returns = np.array(profits) / settings.INITIAL_CAPITAL
            sharpe = (np.mean(returns) / np.std(returns)) * np.sqrt(252) if np.std(returns) > 0 else 0
        else:
            sharpe = 0

        # Generate recommendations
        recommendations = self._generate_recommendations(win_rate, profit_factor, max_drawdown)
        indicator_adjustments = self._generate_indicator_adjustments(signals, win_rate)

        return BacktestResult(
            date=date,
            total_signals=total,
            winning_signals=winning,
            losing_signals=losing,
            win_rate=round(win_rate, 2),
            profit_factor=round(profit_factor, 2),
            max_drawdown=round(max_drawdown, 2),
            sharpe_ratio=round(sharpe, 2),
            total_profit=round(total_profit, 2),
            total_loss=round(total_loss, 2),
            net_profit=round(net_profit, 2),
            recommendations=recommendations,
            indicator_adjustments=indicator_adjustments
        )

    def _generate_recommendations(self, win_rate: float, profit_factor: float,
                                   max_drawdown: float) -> List[str]:
        """Generate improvement recommendations based on metrics."""
        recommendations = []

        if win_rate < 55:
            recommendations.append(
                f"Win Rate actual ({win_rate:.1f}%) por debajo del objetivo (75%). "
                "Considerar aumentar el número mínimo de indicadores para confirmar señales."
            )
        elif win_rate >= 75:
            recommendations.append(
                f"Win Rate excelente ({win_rate:.1f}%). Mantener configuración actual."
            )

        if profit_factor < 1.5:
            recommendations.append(
                f"Profit Factor ({profit_factor:.2f}) por debajo del objetivo (1.5). "
                "Revisar ratios de riesgo/recompensa."
            )

        if max_drawdown > 10:
            recommendations.append(
                f"Drawdown máximo ({max_drawdown:.1f}%) excede el límite (10%). "
                "Reducir el tamaño de posición o ajustar stop loss."
            )

        if not recommendations:
            recommendations.append("Todos los KPIs dentro de parámetros óptimos.")

        return recommendations

    def _generate_indicator_adjustments(self, signals: List[Dict],
                                         win_rate: float) -> List[str]:
        """Generate indicator adjustment suggestions."""
        adjustments = []

        if win_rate < 60:
            adjustments.append("Aumentar período RSI a 21 para reducir señales falsas")
            adjustments.append("Considerar usar EMA 100 como filtro adicional")
            adjustments.append("Ajustar ADX threshold a 30 para filtrar mercados laterales")

        if win_rate < 50:
            adjustments.append("Incrementar desviación estándar de Bollinger a 2.5")
            adjustments.append("Reducir multiplicador ATR para SL a 1.0")
            adjustments.append("Activar filtro de sesión institucional obligatorio")

        if not adjustments:
            adjustments.append("Indicadores operando dentro de parámetros óptimos")

        return adjustments

    def _save_report(self, result: BacktestResult, report_type: str):
        """Save backtesting report to file."""
        try:
            date_str = datetime.now().strftime("%Y%m%d")
            filename = f"[{date_str}]AnalisisBackTesting_{report_type}.txt"
            filepath = os.path.join(self.reports_dir, filename)

            content = self._format_report(result, report_type)

            with open(filepath, "w", encoding="utf-8") as f:
                f.write(content)

            logger.info(f"Backtest report saved: {filepath}")

        except Exception as e:
            logger.error(f"Error saving backtest report: {e}")

    def _format_report(self, result: BacktestResult, report_type: str) -> str:
        """Format backtesting report as text."""
        header = "DIARIO" if report_type == "daily" else "SEMANAL"

        content = f"""
{'='*60}
REPORTE DE BACKTESTING {header}
TradingSignal Pro
{'='*60}

Fecha: {result.date}
Generado: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

{'─'*60}
MÉTRICAS DE RENDIMIENTO
{'─'*60}

Total de Señales:     {result.total_signals}
Señales Ganadoras:    {result.winning_signals}
Señales Perdedoras:   {result.losing_signals}
Win Rate:             {result.win_rate}%
Profit Factor:        {result.profit_factor}
Max Drawdown:         {result.max_drawdown}%
Sharpe Ratio:         {result.sharpe_ratio}

{'─'*60}
RESULTADOS FINANCIEROS
{'─'*60}

Ganancia Total:       ${result.total_profit}
Pérdida Total:        ${result.total_loss}
Ganancia Neta:        ${result.net_profit}

{'─'*60}
RECOMENDACIONES DE MEJORA
{'─'*60}

"""
        for i, rec in enumerate(result.recommendations, 1):
            content += f"{i}. {rec}\n"

        content += f"""
{'─'*60}
AJUSTES DE INDICADORES SUGERIDOS
{'─'*60}

"""
        for i, adj in enumerate(result.indicator_adjustments, 1):
            content += f"{i}. {adj}\n"

        content += f"""
{'='*60}
FIN DEL REPORTE
{'='*60}
"""
        return content

    def get_latest_report(self, report_type: str = "daily") -> Optional[str]:
        """Get the latest backtesting report content."""
        try:
            files = os.listdir(self.reports_dir)
            report_files = [f for f in files if f.endswith(f"_{report_type}.txt")]

            if not report_files:
                return None

            report_files.sort(reverse=True)
            filepath = os.path.join(self.reports_dir, report_files[0])

            with open(filepath, "r", encoding="utf-8") as f:
                return f.read()

        except Exception:
            return None

    def get_all_reports(self) -> List[Dict]:
        """Get list of all available reports."""
        try:
            files = os.listdir(self.reports_dir)
            reports = []

            for f in sorted(files, reverse=True):
                if f.endswith(".txt"):
                    filepath = os.path.join(self.reports_dir, f)
                    reports.append({
                        "filename": f,
                        "path": filepath,
                        "date": f[1:9] if f.startswith("[") else "",
                        "type": "weekly" if "weekly" in f else "daily"
                    })

            return reports

        except Exception:
            return []


# Singleton instance
backtesting_service = BacktestingService()
