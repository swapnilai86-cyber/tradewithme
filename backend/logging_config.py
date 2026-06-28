import logging
import json
from datetime import datetime


class JSONFormatter(logging.Formatter):
    def format(self, record):
        log_obj = {
            "timestamp": datetime.now().isoformat(),
            "level": record.levelname,
            "name": record.name,
            "message": record.getMessage(),
        }
        if hasattr(record, "reason"):
            log_obj["reason"] = record.reason

        # Include extra kwargs passed via the 'extra' dict
        if hasattr(record, "reason_code"):
            log_obj["reason_code"] = record.reason_code

        # Include any other extra fields
        for key in ("symbol", "sector", "order_id", "daily_pnl_pct"):
            if hasattr(record, key):
                log_obj[key] = getattr(record, key)

        return json.dumps(log_obj)


class LiveBufferHandler(logging.Handler):
    """Pushes every log record into the in-memory SSE buffer."""
    def emit(self, record):
        try:
            # Lazy import to avoid circular dependency at module load time
            from backend.app.api.logs import push_log
            entry = {
                "timestamp": datetime.now().isoformat(),
                "level": record.levelname,
                "name": record.name,
                "message": self.format(record),
            }
            push_log(entry)
        except Exception:
            pass  # Never crash the app due to logging


_buffer_handler_added = False


def get_logger(name: str):
    global _buffer_handler_added
    logger = logging.getLogger(name)
    if not logger.handlers:
        # JSON stdout handler
        handler = logging.StreamHandler()
        formatter = JSONFormatter()
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        
        import os
        log_level_str = os.getenv("LOG_LEVEL", "INFO").upper()
        level = getattr(logging, log_level_str, logging.INFO)
        logger.setLevel(level)

    # Add the live-buffer handler once to the root logger
    root = logging.getLogger()
    if not _buffer_handler_added:
        buf_handler = LiveBufferHandler()
        # Use a plain formatter for the buffer message field
        buf_handler.setFormatter(logging.Formatter("%(message)s"))
        root.addHandler(buf_handler)
        _buffer_handler_added = True

    return logger
