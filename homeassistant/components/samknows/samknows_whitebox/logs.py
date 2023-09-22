import logging


class CustomFormatter(logging.Formatter):
    green = "\x1b[32;20m"
    grey = "\x1b[38;20m"
    yellow = "\x1b[33;20m"
    red = "\x1b[31;20m"
    bold_red = "\x1b[31;1m"
    reset = "\x1b[0m"
    _log_format = (
        "%(asctime)s [%(name)s|%(levelname)s] %(message)s (%(filename)s:%(lineno)d)"
    )

    FORMATS = {
        logging.DEBUG: grey + _log_format + reset,
        logging.INFO: green + _log_format + reset,
        logging.WARNING: yellow + _log_format + reset,
        logging.ERROR: red + _log_format + reset,
        logging.CRITICAL: bold_red + _log_format + reset,
    }

    def format(self, record):
        log_fmt = self.FORMATS.get(record.levelno)
        formatter = logging.Formatter(log_fmt)
        return formatter.format(record)
