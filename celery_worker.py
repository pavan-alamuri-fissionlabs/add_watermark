from celery import Celery

celery_app = Celery(
    "worker",
    broker="redis://localhost:6379/0",   # Redis broker
    backend="redis://localhost:6379/0",   # Store results
    include=["add_watermark", "app"]  # Include tasks from these modules
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="Asia/Kolkata",
    enable_utc=True,
)
