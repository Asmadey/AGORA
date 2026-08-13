/**
 * Выбор темы: единственное место, которому разрешено хранилище браузера.
 *
 * ─── Почему это не нарушение правила ───────────────────────────────────────
 * `evals/tests/test_ui_real_storage.py` запрещает localStorage под `app/`,
 * `components/` и `lib/`, и запрет не формальный: экраны проектов, анкет и
 * аудиторий держали там данные продукта, из-за чего у второго человека список
 * был пуст, а изоляции арендаторов не было вовсе.
 *
 * Тема — не данные продукта. Она не принадлежит арендатору, её незачем видеть
 * коллеге, и её потеря ничего не стоит: следующий заход просто спросит систему.
 * Ровно поэтому исключение здесь одно, названо поимённо в тесте и ограничено
 * одним ключом. Исключение, которое нельзя перечислить, перестаёт быть
 * исключением и становится дырой.
 *
 * ─── Почему не кука ────────────────────────────────────────────────────────
 * Кука уехала бы на сервер с каждым запросом, включая загрузку видео, и
 * потребовала бы решения про SameSite и срок жизни ради значения, которое
 * серверу не нужно: тему применяет браузер до первой отрисовки.
 */

export const THEME_KEY = "agora-theme";

export type Theme = "light" | "dark";

/** Значение из хранилища, если оно осмысленно. Иначе — `null`. */
export function storedTheme(): Theme | null {
  try {
    const raw = window.localStorage.getItem(THEME_KEY);
    return raw === "light" || raw === "dark" ? raw : null;
  } catch {
    // Приватный режим и запрет хранилища в настройках браузера бросают здесь
    // исключение. Тема — не то, ради чего экран имеет право не открыться.
    return null;
  }
}

export function storeTheme(theme: Theme): void {
  try {
    window.localStorage.setItem(THEME_KEY, theme);
  } catch {
    /* см. выше: молча остаёмся на теме до конца сессии */
  }
}

/** Тема системы. Спрашивается только когда пользователь не выбирал сам. */
export function systemTheme(): Theme {
  return window.matchMedia?.("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

/** Применяет тему к документу. Класс на <html> — то, что читает globals.css. */
export function applyTheme(theme: Theme): void {
  document.documentElement.classList.toggle("dark", theme === "dark");
  document.documentElement.style.colorScheme = theme;
}

/**
 * Скрипт, выполняемый до первой отрисовки.
 *
 * Без него страница успевает мигнуть светлой темой у того, кто выбрал тёмную:
 * React применит класс только после гидратации, а это уже после первого кадра.
 * Мигание однокадровое и оттого выглядит дефектом рендера, а не задержкой.
 *
 * Строкой, а не импортом: содержимое уходит в inline-скрипт в <head>, до
 * загрузки любого бандла.
 */
export const NO_FLASH_SCRIPT = `(function(){try{
var t=localStorage.getItem(${JSON.stringify(THEME_KEY)});
if(t!=="light"&&t!=="dark"){t=matchMedia("(prefers-color-scheme: dark)").matches?"dark":"light";}
document.documentElement.classList.toggle("dark",t==="dark");
document.documentElement.style.colorScheme=t;
}catch(e){}})();`;
