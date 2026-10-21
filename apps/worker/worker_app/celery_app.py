from celery import Celery
from server_core.config import settings
from server_core.observability import configure_observability

celery_app = Celery("knowledge_worker", broker=settings.redis_url, backend=settings.redis_url)
celery_app.conf.update(task_acks_late=True, worker_prefetch_multiplier=1, task_reject_on_worker_lost=True)
celery_app.autodiscover_tasks(["worker_app"])
configure_observability(celery_app=celery_app)
