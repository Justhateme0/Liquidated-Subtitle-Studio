# Liquidated Subtitle Studio

Локальное Windows-приложение для создания субтитров из трека: выделение вокала через `Demucs`, распознавание через `faster-whisper`, ручная правка текста и таймингов, экспорт в `alpha MOV` и `MP4`.

## Возможности

- загрузка аудиотрека
- отделение вокала
- распознавание текста
- ручная правка строк и таймингов
- экспорт видео с субтитрами
- desktop-версия без отдельных консольных окон

## Для кого

Подходит для:

- эдитов
- клипов
- субтитров в стиле `brat`
- роликов с кастомным фоном, шрифтом и ручной правкой строк

## Стек

- Frontend: `React 19 + TypeScript + Vite`
- Backend: `FastAPI`
- ASR: `faster-whisper`
- Vocal separation: `Demucs`
- Render: `ffmpeg`
- Desktop shell: `pywebview`
- Installer: `Inno Setup`

## Установка

Самый простой способ:

1. Открой вкладку `Releases` на GitHub.
2. Скачай `LiquidatedSubtitleStudioSetup.exe`.
3. Запусти установщик.
4. Дождись завершения установки и первой подготовки runtime.

Важно:

- на первом запуске приложению может понадобиться интернет для загрузки моделей `faster-whisper` и `Demucs`
- первый запуск может идти дольше обычного

## Запуск из исходников

Если нужен dev-режим, установи:

1. `Python 3.11+`
2. `Node.js LTS`

Дальше:

1. Скачай проект
2. Открой папку проекта
3. Запусти [`start-app.bat`](./start-app.bat)
4. Открой [http://localhost:5173/](http://localhost:5173/)

## Desktop сборка

Готовые артефакты после локальной сборки:

- `dist/LiquidatedSubtitleStudio/LiquidatedSubtitleStudio.exe`
- `dist/installer/LiquidatedSubtitleStudioSetup.exe`


[ИНСТРУКЦИЯ.md](./ИНСТРУКЦИЯ.md)
