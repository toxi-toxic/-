import os
import time
import traceback
from collections import Counter

import tkinter as tk
from tkinter import scrolledtext, messagebox, filedialog
from tkinter import ttk

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from bs4 import BeautifulSoup

import matplotlib
matplotlib.use("Agg")
from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

#Настройк
AUTO_HEADLESS = False
CLICK_MORE_ATTEMPTS = 6
SCROLL_PAUSE = 1.0
WAIT_TIMEOUT = 12

#WebDriver
def build_driver(headless=AUTO_HEADLESS):
    opts = Options()
    if headless:
        opts.add_argument("--headless=new")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--disable-gpu")
    # Установим понятный User-Agent (иногда помогает)
    opts.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                      "(KHTML, like Gecko) Chrome/141.0.7390.108 Safari/537.36")
    # Устанавливаем сервис через webdriver-manager (скачает подходящий chromedriver)
    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=opts)
    driver.set_page_load_timeout(30)
    return driver

#Сбор и парсинг
def expand_page(driver):
    """
    наэимаем 'Показать ещё'варианты
    """
    try:
    
        last_height = driver.execute_script("return document.body.scrollHeight")
        for _ in range(6):
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(SCROLL_PAUSE)
            new_height = driver.execute_script("return document.body.scrollHeight")
            if new_height == last_height:
                break
            last_height = new_height
        xpath_buttons = [
            "//button[contains(translate(text(),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'показ')]",  # показать
            "//button[contains(translate(text(),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'еще')]",  # еще / ещё
            "//a[contains(translate(text(),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'еще')]",
            "//a[contains(translate(text(),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'показ')]",
            "//button[contains(@class,'more') or contains(@class,'load') or contains(@class,'show')]"  # класс-эфемер
        ]
        clicked_any = True
        attempts = 0
        while clicked_any and attempts < CLICK_MORE_ATTEMPTS:
            clicked_any = True
            attempts += 1
            for xp in xpath_buttons:
                try:
                    elems = driver.find_elements(By.XPATH, xp)
                    for e in elems:
                        try:
                            if e.is_displayed():
                                # Селениум иногда не может кликнуть — используем JS click
                                driver.execute_script("arguments[0].click();", e)
                                clicked_any = True
                                time.sleep(0.6)
                        except Exception:
                            continue
                except Exception:
                    continue
            if clicked_any:
                # если кликнули — немного прокрутим/подождём
                time.sleep(0.8)
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(SCROLL_PAUSE)
    except Exception:
        pass

def extract_reviews_from_html(html):
    """
    Попытка извлечь тексты отзывов множеством эвристик.
    Возвращает список строк (отзывов).
    """
    soup = BeautifulSoup(html, "html.parser")
    results = []

    # 1) Попытка по очевидным селекторам (data-test, itemprop, role, aria)
    selectors = [
        ("div", {"data-test-id": lambda v: v and "review" in v}),
        ("div", {"data-qa": lambda v: v and "review" in v}),
        ("div", {"class": lambda v: v and ("review" in v.lower() or "comment" in v.lower() or "response" in v.lower())}),
        ("article", {}),
        ("div", {"itemprop": "reviewBody"}),
        ("p", {}),
        ("div", {"role": "article"})
    ]

    # Собираем кандидатов: блоки, содержащие длинный текст
    for tag, attrs in selectors:
        try:
            tags = soup.find_all(tag, attrs=attrs)
        except Exception:
            # некоторые lambda в attrs могут выбрасывать — игнорируем
            try:
                tags = soup.find_all(tag)
            except Exception:
                tags = []
        for t in tags:
            text = t.get_text(separator="\n").strip()
            if text and len(text) >= 30:
                results.append(text)

    # 2) Поиск блоков, где много <p>, вероятно отзыв
    for div in soup.find_all("div"):
        ps = div.find_all("p")
        if len(ps) >= 1:
            combined = "\n".join(p.get_text().strip() for p in ps)
            if len(combined) >= 30 and len(combined.split()) >= 8:
                results.append(combined)

    # 3) Поиск по CSS-паттерну (кино сайты часто генерируют классы вида styles_review__XYZ)
    for d in soup.find_all(True, {"class": lambda v: v and ("styles_review" in v or "review__" in v or "comment" in v)}):
        text = d.get_text(separator="\n").strip()
        if len(text) >= 30:
            results.append(text)

    # 4) Очистка: убираем шумы, ссылки, дубли
    cleaned = []
    seen = set()
    for r in results:
        text = " ".join(r.split())
        # отбросить короткий текст или текст с слишком мало букв
        letters = sum(1 for ch in text if ch.isalpha())
        if len(text) < 30 or letters < 20:
            continue
        if text in seen:
            continue
        seen.add(text)
        cleaned.append(text)

    return cleaned

def fetch_reviews_from_url(url, debug_save_dir=None, headless=AUTO_HEADLESS):
    """
    Возвращает список строк: найденные отзывы.
    Если ничего не найдено — сохраняет debug_page.html.
    """
    driver = build_driver(headless=headless)
    texts = []
    debug_path = None
    try:
        driver.get(url)
        time.sleep(1.2)
        # Попробуем закрыть cookie/banner, если есть
        try:
            # часто кнопки имеют тексты 'Принять', 'Согласен' и т.п.
            for xp in [
                "//button[contains(translate(text(),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'прин')]", 
                "//button[contains(translate(text(),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'соглас')]", 
                "//button[contains(translate(text(),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'принять')]",
                "//button[contains(translate(text(),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'close') or contains(@aria-label,'close')]"
            ]:
                els = driver.find_elements(By.XPATH, xp)
                for el in els:
                    try:
                        if el.is_displayed():
                            driver.execute_script("arguments[0].click();", el)
                            time.sleep(0.3)
                    except Exception:
                        continue
        except Exception:
            pass

        # Расширяем и кликаем "Показать ещё"
        expand_page(driver)

        # Некоторое ожидание появления текста
        try:
            WebDriverWait(driver, WAIT_TIMEOUT).until(lambda d: len(d.page_source) > 5000)
        except Exception:
            pass

        html = driver.page_source
        texts = extract_reviews_from_html(html)

        # Если ничего не найдено — пробуем дополнительные стратегии:
        if not texts:
            # попробуем искать по xpath для элементов, часто встречающимся в Kinopoisk
            xpaths = [
                "//div[contains(@class,'styles_review')]", 
                "//div[contains(@class,'responseItem')]", 
                "//div[contains(@class,'user-review')]", 
                "//article"
            ]
            for xp in xpaths:
                try:
                    elems = driver.find_elements(By.XPATH, xp)
                    tmp = [e.text for e in elems if e.text and len(e.text) > 30]
                    if tmp:
                        texts = tmp
                        break
                except Exception:
                    continue

        # Если снова пусто — сохраняем debug HTML
        if not texts:
            if debug_save_dir is None:
                debug_save_dir = os.getcwd()
            debug_path = os.path.join(debug_save_dir, "debug_page.html")
            with open(debug_path, "w", encoding="utf-8") as f:
                f.write(html)
    except Exception as e:
        # любая ошибка — вернём пустой список и путь к debug если есть
        if debug_save_dir is None:
            debug_save_dir = os.getcwd()
        debug_path = os.path.join(debug_save_dir, "debug_error.txt")
        with open(debug_path, "w", encoding="utf-8") as f:
            f.write("ERROR:\n")
            f.write(traceback.format_exc())
    finally:
        try:
            driver.quit()
        except Exception:
            pass

    return texts, debug_path

# ---------- GUI ----------
class App:
    def _init_(self, root):
        self.root = root
        root.title("по отзывам сюда")
        root.geometry("1020x720")
        root.configure(bg="#f3f5f8")

        top = tk.Frame(root, bg="#f3f5f8", pady=8)
        top.pack(fill=tk.X)

        tk.Label(top, text="Вставь ссылку на страницу отзывов кинопоиска:", bg="#f3f5f8", font=("Arial", 11, "bold")).pack(side=tk.LEFT, padx=8)
        self.url_var = tk.StringVar()
        self.url_entry = ttk.Entry(top, textvariable=self.url_var, width=82)
        self.url_entry.pack(side=tk.LEFT, padx=6)
        self.url_entry.bind("<Control-v>", lambda e: None)  # ctrl+v работает по умолчанию
        # контекстное меню правой кнопкой:
        self.create_context_menu(self.url_entry)

        self.analyze_btn = ttk.Button(top, text="Анализировать", command=self.on_analyze)
        self.analyze_btn.pack(side=tk.LEFT, padx=6)

        # center: left reviews, right chart + recommendation
        center = tk.PanedWindow(root, orient=tk.HORIZONTAL)
        center.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        left = tk.Frame(center, bg="#ffffff")
        center.add(left)
        tk.Label(left, text="Анализированные отзывы:", bg="#ffffff", font=("Arial", 11, "bold")).pack(anchor=tk.W, padx=6, pady=(6,2))
        self.reviews_box = scrolledtext.ScrolledText(left, wrap=tk.WORD, font=("Arial", 10))
        self.reviews_box.pack(fill=tk.BOTH, expand=True, padx=6, pady=6)

        right = tk.Frame(center, bg="#ffffff", width=360)
        center.add(right)
        tk.Label(right, text="Сводная статистика:", bg="#ffffff", font=("Arial", 11, "bold")).pack(anchor=tk.W, padx=6, pady=(6,2))

        self.fig = Figure(figsize=(4,3), dpi=100)
        self.ax = self.fig.add_subplot(111)
        self.canvas = FigureCanvasTkAgg(self.fig, master=right)
        self.canvas.get_tk_widget().pack(padx=6, pady=6)

        self.rec_label = tk.Label(right, text="Итоговая рекомендация: —", bg="#ffffff", font=("Arial", 12, "bold"))
        self.rec_label.pack(anchor=tk.W, padx=6, pady=6)

        self.status_var = tk.StringVar(value="Готово")
        tk.Label(root, textvariable=self.status_var, bg="#e9eef5", anchor="w").pack(side=tk.BOTTOM, fill=tk.X)

    def create_context_menu(self, widget):
        menu = tk.Menu(widget, tearoff=0)
        menu.add_command(label="Вставить", command=lambda: widget.event_generate("<<Paste>>"))
        menu.add_command(label="Копировать", command=lambda: widget.event_generate("<<Copy>>"))
        menu.add_command(label="Вырезать", command=lambda: widget.event_generate("<<Cut>>"))
        widget.bind("<Button-3>", lambda e: menu.tk_popup(e.x_root, e.y_root))

    def on_analyze(self):
        url = self.url_var.get().strip()
        if not url:
            messagebox.showwarning("Ввод", "Введите URL страницы с отзывами (на кинопоиск).")
            return

        # блокируем кнопку
        self.analyze_btn.config(state="disabled")
        self.status_var.set("нахожу отзывы...")
        self.root.update_idletasks()

        # запускаем работу (синхронно — чтобы пользователь сразу увидел результат)
        try:
            texts, debug_path = fetch_reviews_from_url(url, debug_save_dir=os.getcwd(), headless=AUTO_HEADLESS)
            if not texts:
                self.reviews_box.delete("1.0", tk.END)
                self.reviews_box.insert(tk.END, "Отзывы не найдены.\n")
                self.reviews_box.insert(tk.END, "Сохранён debug-файл: {}\n".format(debug_path))
                self.reviews_box.insert(tk.END, "Возможные причины:\n - Страница не содержит отзывов\n - Отзывы загружаются из другого домена/API\n - Необходимо авторизоваться на сайте\n\nПришлите URL и я дам вам отзыв.\n")
                self.status_var.set("Готово — не найдено")
                return

            # Отобразим
            self.reviews_box.delete("1.0", tk.END)
            for i, t in enumerate(texts, 1):
                # ограничим длину для показа (если очень длинные)
                display = t if len(t) <= 2000 else (t[:2000] + " ...[truncated]")
                self.reviews_box.insert(tk.END, f"{i}. {display}\n\n")

            # простая классификация по ключевым словам (быстрая эвристика)
            labels = []
            for t in texts:
                tl = t.lower()
                if any(x in tl for x in ("отлично", "хорошоо", "понравилось", "рекомендую", "класс")):
                    labels.append("Положительный")
                elif any(x in tl for x in ("плохо", "ужас", "не понрав", "отврат", "скучн")):
                    labels.append("Отрицательный")
                else:
                    labels.append("Нейтральный")

            cnt = Counter(labels)
            total = len(labels)
            # обновим диаграмму
            self.ax.clear()
            pie_labels = []
            sizes = []
            pie_colors = []
            mapping_colors = {"Положительный":"#4CAF50","Нейтральный":"#9E9E9E","Отрицательный":"#F44336"}
            for lab in ("Положительный","Нейтральный","Отрицательный"):
                v = cnt.get(lab,0)
                if v>0:
                    pie_labels.append(f"{lab} ({v})")
                    sizes.append(v)
                    pie_colors.append(mapping_colors.get(lab))
            if sizes:
                self.ax.pie(sizes, labels=pie_labels, autopct='%1.0f%%', startangle=90, colors=pie_colors)
                self.ax.axis('equal')
            else:
                self.ax.text(0.5,0.5,"Нет данных", ha='center', va='center')
            self.canvas.draw()

            # Итоговая рекомендация по эвристике
            pos = cnt.get("Положительный",0)
            neg = cnt.get("Отрицательный",0)
            pct_pos = pos*100/total if total else 0
            pct_neg = neg*100/total if total else 0
            if pct_pos >= 60:
                verdict = "Рекомендуется к просмотру"
                color = "green"
            elif pct_neg >= 50 and neg > pos:
                verdict = "Лучше воздержаться"
                color = "red"
            else:
                verdict = "решайте сами"
                color = "orange"

            self.rec_label.config(text=f"Итоговая рекомендация: {verdict}", fg=color)
            self.status_var.set(f"Анализ завершён: {total} отзывов")
        finally:
            self.analyze_btn.config(state="normal")


def main():
    root = tk.Tk()
    app = App(root)
    root.mainloop()

if _name_ == "_main_":
    main()