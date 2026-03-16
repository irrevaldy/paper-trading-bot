import logging
import os


def setup_logger(level: str = "INFO") -> logging.Logger:
    os.makedirs("logs", exist_ok=True)
    logger = logging.getLogger("crypto_bot")
    logger.setLevel(level)

    if not logger.handlers:
        formatter = logging.Formatter(
            "%(asctime)s | %(levelname)s | %(message)s"
        )

        stream_handler = logging.StreamHandler()
        stream_handler.setFormatter(formatter)

        file_handler = logging.FileHandler("logs/bot.log")
        file_handler.setFormatter(formatter)

        logger.addHandler(stream_handler)
        logger.addHandler(file_handler)

    return logger
