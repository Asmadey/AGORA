"""AGORA agent-core — бэкенд синтетических фокус-групп.

Состав по задачам графа (evals/state/tasks.json):
  #13 orchestrator  — LangGraph-пайплайн внутри Celery-задачи
  #14 media         — ffmpeg: extract_audio, сегментация длинного видео
  #15 transcribe    — faster-whisper large-v3 int8 + pyannote 3.1 по полному треку
  #16 frames        — PySceneDetect + панели×4 + кэш + Qwen VLM
  #17 stitch        — reduce: video_understanding по таймлайну
  #18 respondent    — изолированная оценка персонами × replication_count
  #19 qa            — LLM-as-judge: consistency / grounding / diversity
  #20 analytics     — агрегат + групповой синтез + доверительные границы

На задаче #1 здесь только контракт сборки: пакет импортируется, pytest и ruff проходят.
"""

__version__ = "0.1.0"
