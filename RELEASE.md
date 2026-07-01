# Релиз

## Формат коммитов

| Префикс | Когда использовать |
|---|---|
| `feat:` | Новая функция |
| `fix:` | Исправление бага |
| `refactor:` | Рефакторинг без изменения поведения |
| `chore:` | Служебные изменения (зависимости, CI, конфиги) |
| `docs:` | Изменения документации |

---

## Выпуск

```bash
git tag v1.2.0
git push origin v1.2.0
```

GitHub Actions соберёт exe для Windows и macOS, сгенерирует changelog и опубликует релиз автоматически (~5–10 минут).

Результат: https://github.com/AtariVC/keithly_calibrator/releases

---

## Откат тега

```bash
git tag -d v1.2.0
git push origin :refs/tags/v1.2.0
```
