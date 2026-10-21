import httpx
import os
import logging

logger = logging.getLogger(__name__)

# Адрес, где запущены моки.
# Если запускаешь локально (без Docker) - http://localhost:8001
# Если в Docker - http://mock:8000
MOCK_BASE_URL = os.getenv("MOCK_SERVICE_URL", "http://localhost:8001")

# Таймаут на один запрос (в секундах). Если мок тупит дольше - идем в ручное рассмотрение.
TIMEOUT_SECONDS = 3.0


async def _call_mock(endpoint: str, headers: dict = None) -> dict:
    """
    Универсальная функция вызова мока с обработкой ошибок.
    Возвращает либо данные от мока, либо словарь с ошибкой.
    """
    url = f"{MOCK_BASE_URL}{endpoint}"
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(url, headers=headers, timeout=TIMEOUT_SECONDS)

            # Если мок ответил 403 (например, нет согласия БКИ) - это валидный ответ
            if response.status_code == 403:
                return {"__error__": "FORBIDDEN", "detail": response.json()}

            response.raise_for_status()
            return response.json()

    except httpx.TimeoutException:
        logger.error(f"Timeout при запросе к {url}")
        return {"__error__": "TIMEOUT"}
    except httpx.HTTPStatusError as e:
        logger.error(f"Ошибка {e.response.status_code} при запросе к {url}")
        return {"__error__": "HTTP_ERROR", "status_code": e.response.status_code}
    except Exception as e:
        logger.error(f"Неизвестная ошибка при запросе к {url}: {str(e)}")
        return {"__error__": "CONNECTION_ERROR"}


# ==========================================
# Обертки для каждого конкретного сервиса
# ==========================================

async def get_egrul(inn: str) -> dict:
    return await _call_mock(f"/mock/egrul/{inn}")


async def get_zsk(inn: str) -> dict:
    return await _call_mock(f"/mock/zsk/{inn}")


async def get_fns(inn: str) -> dict:
    return await _call_mock(f"/mock/fns/{inn}")


async def get_risk_flags(inn: str) -> dict:
    return await _call_mock(f"/mock/risk-flags/{inn}")


async def get_bki(inn: str, consent_id: str = None) -> dict:
    headers = {}
    if consent_id:
        headers["X-Consent-Id"] = consent_id
    return await _call_mock(f"/mock/bki/{inn}", headers=headers)