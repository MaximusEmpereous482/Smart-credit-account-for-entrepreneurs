# Архитектура решения

Проект развертывается через Docker Compose и состоит из трех независимых микросервисов.

```mermaid
graph TD
    Client[Клиент] -->|HTTP| Nginx[Frontend Nginx :8080]
    Banker[Сотрудник банка] -->|HTTP| Nginx
    Nginx -->|REST API| Orch[Orchestrator FastAPI :8002]
    Orch -->|SQLAlchemy| DB[(SQLite DB)]
    Orch -->|HTTPX| MockEGRUL[Mock ЕГРЮЛ]
    Orch -->|HTTPX| MockFNS[Mock ФНС]
    Orch -->|HTTPX| MockBKI[Mock БКИ]
    Orch -->|HTTPX| MockZSK[Mock ЗСК]