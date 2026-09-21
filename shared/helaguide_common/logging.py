import logging


def setup_logging(service_name: str, level: str = "INFO") -> logging.Logger:
    logging.basicConfig(
        level=level.upper(),
        format=f"%(asctime)s {service_name} %(levelname)s %(name)s: %(message)s",
    )
    return logging.getLogger(service_name)
