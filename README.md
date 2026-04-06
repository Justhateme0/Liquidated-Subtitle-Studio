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

1. скачай проект
2. открой папку проекта
3. запусти [start-app.bat](./start-app.bat)
4. открой [http://127.0.0.1:5173](http://127.0.0.1:5173)

## Desktop сборка

Готовые артефакты после локальной сборки:

- `dist/LiquidatedSubtitleStudio/LiquidatedSubtitleStudio.exe`
- `dist/installer/LiquidatedSubtitleStudioSetup.exe`

## Что загружать на GitHub

В репозиторий загружай исходники:

- `backend/`
- `frontend/`
- `scripts/`
- `icon/`
- `README.md`
- `ИНСТРУКЦИЯ.md`
- `.gitignore`
- `start-app.bat`
- `desktop_app.py`
- `desktop-requirements.txt`
- `LiquidatedSubtitleStudio.spec`
- `LiquidatedSubtitleStudio.iss`

## Что не загружать в репозиторий

Не нужно коммитить локальные и собранные файлы:

- `.venv/`
- `frontend/node_modules/`
- `frontend/dist/`
- `storage/`
- `tools/ffmpeg/`
- `.pytest_cache/`
- `.playwright-cli/`
- `build/`
- `dist/`
- временные файлы вроде `tmp-create.json`, `tmp-upload.json`, `*.log`

Готовый установщик не нужно хранить в репозитории. Его лучше выкладывать в `GitHub Releases` как asset.

## Как выложить на GitHub

1. Создай новый репозиторий на GitHub.
2. В корне проекта выполни:

```bash
git init
git add .
git commit -m "Initial commit"
git branch -M main
git remote add origin https://github.com/USERNAME/REPO.git
git push -u origin main
```

3. После этого открой раздел `Releases`.
4. Создай новый релиз.
5. Прикрепи файл `LiquidatedSubtitleStudioSetup.exe`.

## Что писать в Release

Пример структуры релиза:

- заголовок версии
- коротко что изменилось
- что скачивать
- важное примечание про первый запуск

Готовый текст для подробного гайда:

[ИНСТРУКЦИЯ.md](./ИНСТРУКЦИЯ.md)
