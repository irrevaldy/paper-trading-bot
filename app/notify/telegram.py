import requests


class TelegramNotifier:
    def __init__(self, enabled: bool, bot_token: str, chat_id: str, logger):
        self.enabled = enabled
        self.bot_token = bot_token
        self.chat_id = chat_id
        self.logger = logger

    def send(self, message: str):
        if not self.enabled:
            return

        if not self.bot_token or not self.chat_id:
            self.logger.warning("Telegram enabled but token/chat_id missing")
            return

        url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
        payload = {
            "chat_id": self.chat_id,
            "text": message,
        }

        try:
            requests.post(url, json=payload, timeout=10)
        except Exception as e:
            self.logger.warning(f"Telegram send failed: {e}")
