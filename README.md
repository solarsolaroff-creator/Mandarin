# Мандарин

Простой браузер на Python и Chrome. Оранжевый интерфейс, адресная строка, поиск (DuckDuckGo, Google, Яндекс), кнопки назад, вперёд, обновить и домой.

## Версии

- **Windows:** `windows/mandarin.py` (готовый `.exe` в разделе Releases)
- **Android:** `android/index.html` (готовый `.apk` в разделе Releases), собран через HTML to APK

## Как это работает

Это оболочка над готовым браузером, а не отдельный движок. Windows-версия запускает установленный Google Chrome и встраивает его окно в программу, а Android-версия показывает страницы через встроенный WebView.

## Запуск на Windows

1. Установи Python 3.8+ и Google Chrome.
2. `python -m pip install customtkinter pywin32 requests websocket-client`
3. `python windows/mandarin.py`

## Ограничения

- Нет вкладок, закладок и истории.
- Только Windows (для `.exe`/`.py`) и нужен установленный Chrome.
- На Windows 7 и 8 Chrome не обновляется выше версии 109, для серьёзного сёрфинга лучше современная система.
- APK собран в режиме debug, при установке Android предупредит о неизвестном источнике.

## Лицензия

MIT, см. `LICENSE.md`.
