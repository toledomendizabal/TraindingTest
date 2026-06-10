"""Email service using Gmail API with OAuth2."""
import os
import base64
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
from datetime import datetime
from typing import Optional
from loguru import logger
from app.core.config import settings


class EmailService:
    """Service for sending emails via Gmail API."""

    SCOPES = ["https://www.googleapis.com/auth/gmail.send"]

    def __init__(self):
        self.credentials = None
        self.service = None
        self._initialized = False

    async def initialize(self):
        """Initialize Gmail service with OAuth2 credentials."""
        try:
            from google.oauth2.credentials import Credentials
            from google_auth_oauthlib.flow import InstalledAppFlow
            from google.auth.transport.requests import Request
            from googleapiclient.discovery import build

            token_path = os.path.join(settings.CONFIG_DIR, "token.json")
            client_secret_path = os.path.join(settings.CONFIG_DIR, "client_secret.json")

            if os.path.exists(token_path):
                self.credentials = Credentials.from_authorized_user_file(token_path, self.SCOPES)

            # Use credentials if valid, or try to refresh them
            if self.credentials and self.credentials.expired and self.credentials.refresh_token:
                try:
                    self.credentials.refresh(Request())
                    with open(token_path, "w") as token:
                        token.write(self.credentials.to_json())
                    logger.info("Gmail token refreshed successfully")
                except Exception as e:
                    logger.error(f"Failed to refresh Gmail token: {e}")
                    self.credentials = None

            # Only run local server if no valid credentials exist
            if not self.credentials or not self.credentials.valid:
                if os.path.exists(client_secret_path):
                    logger.info("Starting Gmail OAuth flow...")
                    flow = InstalledAppFlow.from_client_secrets_file(
                        client_secret_path, self.SCOPES
                    )
                    self.credentials = flow.run_local_server(port=0)
                    # Save token
                    if self.credentials:
                        with open(token_path, "w") as token:
                            token.write(self.credentials.to_json())
                else:
                    logger.warning("client_secret.json not found. Gmail authentication skipped.")

            if self.credentials:
                self.service = build("gmail", "v1", credentials=self.credentials)
                self._initialized = True
                logger.info("Gmail service initialized successfully")

        except Exception as e:
            logger.error(f"Error initializing Gmail service: {e}")
            self._initialized = False

    async def send_backtest_report(self, result, report_type: str) -> bool:
        """Send backtesting report via email."""
        try:
            if not self._initialized:
                await self.initialize()

            if not self.service:
                logger.warning("Gmail service not available, skipping email")
                return False

            subject = f"TradingSignal Pro - Reporte Backtesting {'Diario' if report_type == 'daily' else 'Semanal'} - {result.date}"

            body = self._format_email_body(result, report_type)

            message = MIMEMultipart()
            message["to"] = settings.EMAIL_RECIPIENT
            message["from"] = settings.EMAIL_SENDER
            message["subject"] = subject

            message.attach(MIMEText(body, "html"))

            # Attach report file if exists
            from app.services.backtesting import backtesting_service
            report_content = backtesting_service.get_latest_report(report_type)
            if report_content:
                date_str = datetime.now().strftime("%Y%m%d")
                filename = f"[{date_str}]AnalisisBackTesting_{report_type}.txt"

                attachment = MIMEBase("application", "octet-stream")
                attachment.set_payload(report_content.encode("utf-8"))
                encoders.encode_base64(attachment)
                attachment.add_header(
                    "Content-Disposition", f"attachment; filename={filename}"
                )
                message.attach(attachment)

            # Send
            raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
            self.service.users().messages().send(
                userId="me", body={"raw": raw}
            ).execute()

            logger.info(f"Backtest email sent to {settings.EMAIL_RECIPIENT}")
            return True

        except Exception as e:
            logger.error(f"Error sending email: {e}")
            return False

    def _format_email_body(self, result, report_type: str) -> str:
        """Format email body as HTML."""
        header = "Diario" if report_type == "daily" else "Semanal"

        html = f"""
        <html>
        <body style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
            <div style="background: #1a1a2e; color: white; padding: 20px; text-align: center;">
                <h1 style="color: #00d4aa;">TradingSignal Pro</h1>
                <h2>Reporte de Backtesting {header}</h2>
                <p>Fecha: {result.date}</p>
            </div>

            <div style="padding: 20px;">
                <h3 style="color: #333;">Métricas de Rendimiento</h3>
                <table style="width: 100%; border-collapse: collapse;">
                    <tr style="background: #f5f5f5;">
                        <td style="padding: 10px; border: 1px solid #ddd;">Total Señales</td>
                        <td style="padding: 10px; border: 1px solid #ddd; text-align: right;">{result.total_signals}</td>
                    </tr>
                    <tr>
                        <td style="padding: 10px; border: 1px solid #ddd;">Win Rate</td>
                        <td style="padding: 10px; border: 1px solid #ddd; text-align: right; color: {'green' if result.win_rate >= 55 else 'red'};">{result.win_rate}%</td>
                    </tr>
                    <tr style="background: #f5f5f5;">
                        <td style="padding: 10px; border: 1px solid #ddd;">Profit Factor</td>
                        <td style="padding: 10px; border: 1px solid #ddd; text-align: right;">{result.profit_factor}</td>
                    </tr>
                    <tr>
                        <td style="padding: 10px; border: 1px solid #ddd;">Max Drawdown</td>
                        <td style="padding: 10px; border: 1px solid #ddd; text-align: right;">{result.max_drawdown}%</td>
                    </tr>
                    <tr style="background: #f5f5f5;">
                        <td style="padding: 10px; border: 1px solid #ddd;">Ganancia Neta</td>
                        <td style="padding: 10px; border: 1px solid #ddd; text-align: right; color: {'green' if result.net_profit >= 0 else 'red'};">${result.net_profit}</td>
                    </tr>
                </table>

                <h3 style="color: #333; margin-top: 20px;">Recomendaciones</h3>
                <ul>
                    {"".join(f'<li>{rec}</li>' for rec in result.recommendations)}
                </ul>

                <h3 style="color: #333;">Ajustes de Indicadores</h3>
                <ul>
                    {"".join(f'<li>{adj}</li>' for adj in result.indicator_adjustments)}
                </ul>
            </div>

            <div style="background: #333; color: white; padding: 10px; text-align: center; font-size: 12px;">
                <p>TradingSignal Pro - Sistema Automatizado de Trading</p>
            </div>
        </body>
        </html>
        """
        return html

    def is_authenticated(self) -> bool:
        """Check if Gmail service is authenticated."""
        return self._initialized and self.service is not None


# Singleton instance
email_service = EmailService()
