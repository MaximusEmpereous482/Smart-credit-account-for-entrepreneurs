# Диаграмма состояний заявки

Полный жизненный цикл заявки от момента создания до финального решения.

```mermaid
stateDiagram-v2
    [*] --> DRAFT: Создание черновика
    DRAFT --> SUBMITTED: Отправка заявки
    SUBMITTED --> STOP_CHECKS: Проверка стоп-факторов (ЕГРЮЛ, ЗСК)

    STOP_CHECKS --> REJECTED_STOP_FACTOR: Найден стоп-фактор
    STOP_CHECKS --> RISK_CHECKS: Стоп-факторов нет

    RISK_CHECKS --> SCORING: Сбор данных (БКИ, ФНС) и скоринг
    RISK_CHECKS --> MANUAL_REVIEW: Техническая ошибка сервиса

    SCORING --> APPROVED: Скор >= 80
    SCORING --> COUNTER_OFFER: Скор 60-79
    SCORING --> REJECTED: Скор < 60

    COUNTER_OFFER --> DOCS_SIGNING: Клиент принял оффер
    COUNTER_OFFER --> [*]: Клиент отказался (таймаут)

    MANUAL_REVIEW --> APPROVED: Банкир одобрил вручную
    MANUAL_REVIEW --> REJECTED: Банкир отклонил вручную

    APPROVED --> DOCS_SIGNING: Подготовка документов