import logging, sys
from .config import settings

def setup_logging():
    logging.basicConfig(level=getattr(logging, settings.log_level, logging.INFO), format='%(asctime)s | %(levelname)s | %(name)s | %(message)s', handlers=[logging.StreamHandler(sys.stdout)])
    return logging.getLogger('special')

log = setup_logging()
