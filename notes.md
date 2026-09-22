# ============================================================
# FILE: notes.md
# ROLE: Торговая база знаний, системные заметки и архитектура портфелей
# PROJECT: TrendH_Papper & Hron3 (cron3Papper) Symbiosis
# LAST UPDATED: 2026-09-20
# ============================================================

<!-- ## 1. Эволюция торговой системы и уроки рынка

### 🔴 Урок 1: Крах «слепых» пробойных стратегий (Семейство U15 / ADR-015)
В процессе масштабных параллельных тестов на 70+ парах семейство классических пробойных стратегий (`u15`, `u15_scalp`, `u15_cons`, `u15_aggr`, `u15_ratchet`) показало стабильный медленный слив депозита:
* **Суммарный результат:** свыше -$370 убытка при более чем 5000 сделок при низком винрейте (42–47%).
* **Причина:** попытка торговать пробои локальных экстремумов на 5m вслепую — без подтверждения реальной ликвидности и аномального объема — наталкивается на ложные заколы (fakes) и уничтожается биржевыми комиссиями.
* **Решение:** Все стратегии семейства U15 официально деактивированы (`is_active: false`) и отправлены в архив архитектурных решений (`tech_debt.md` -> **ADR-015**).

### 🟢 Урок 2: Триумф симбиотических Жнецов и HVH Volume Shock
Переход к стратегиям, отслеживающим реальное состояние рынка и сетки, показал выдающиеся результаты:
1. **`U_SHADOW_HARVESTER_50` (Лидер рейтинга: +40.04$, WR: 62%, 144 сделки)**:
   * Открывает хедж в направлении тренда против застрявшей сетки **только тогда**, когда сеточник набрал $\ge 50\%$ от максимально допустимого объема.
   * На спокойном рынке Жнец спит и не тратит ни цента на комиссии или стопы. При срыве в безоткатный памп — собирает огромный трендовый профит по динамическому трейлингу.
2. **`U_DELTA_SNIPER_15M` (100% Win Rate, +2.63$)**:
   * Точечные входы на старшем 15m таймфрейме при подтверждении аномального всплеска объема (HVH Volume Shock).
3. **`U_HVH_DELTA_SYMBIOSIS` (+2.06$ Realized, +4.93$ Open)**:
   * Трехуровневая фильтрация: 1H тренд + 15m откат к EMA21 + динамический безубыток/трейлинг.

---

## 2. Анатомия метрик сеточника и трендового бота

В системе аналитики (`cron3Papper` и `TrendH_Papper`) заложены ключевые метрики для объективной оценки качества инструмента:

### 1. `N/R` (Net / Realized Ratio)
$$\text{N/R} = \frac{\text{Net Profit (USDT)}}{\text{Realized PnL (USDT)}}$$
* **Смысл:** Показывает, сколько из закрытой прибыли *реально осело в балансе*, а сколько съедено текущей висящей просадкой.
* **Идеальный диапазон:** $\ge 0.75$ (80%+ прибыли свободно и не заморожено в сетке).
* *Примеры:* `CROSSUSDT` ($\text{N/R} = 0.85$), `AIAUSDT` ($\text{N/R} = 0.85$) — эталонный чистый кэш.
* *Антипримеры:* `GUSDT` ($\text{N/R} = -0.12$), `ZAMAUSDT` ($\text{N/R} = -1.41$) — огромный валовый оборот, но вся прибыль заморожена в глубокой сетке.

### 2. `Risk / Reward Ratio` (R/R)
$$\text{R/R} = \frac{|\text{Max Drawdown (USDT)}|}{\text{Avg Daily Profit (USDT)}}$$
* **Смысл:** Сколько дней средней прибыли нужно, чтобы полностью покрыть историческую максимальную просадку.
* **Чем ниже — тем лучше.** Значения $< 1.0$ означают ультра-безопасные активы.
* *Примеры:* `MIRAUSDT` ($0.38$), `AEROUSDT` ($0.52$), `CROSSUSDT` ($0.81$).

### 3. `DRME` (Daily Return on Max Exposure)
$$\text{DRME} = \frac{\text{Avg Daily Profit}}{\text{Max Position Size}}$$
* **Смысл:** Скорость оборачиваемости капитала. Показывает, сколько прибыли генерирует каждый доллар максимальной загрузки позиции в сутки.
* **Лидеры по DRME:** `GUSDT` ($0.154$), `PIEVERSEUSDT` ($0.052$), `ZAMAUSDT` ($0.046$), `CROSSUSDT` ($0.042$).

### 4. `MDME` (Max Drawdown on Max Exposure)
$$\text{MDME} = \frac{|\text{Max Drawdown}|}{\text{Max Position Size}}$$
* **Смысл:** Относительная глубина максимальной просадки к максимальному размеру позиции. Показывает структурную устойчивость монеты к сквизам.

---

## 3. Четыре режима отбора портфеля (`Portfolio Selector`)

Для формирования боевого пула монет реализованы четыре специализированных режима:

| Режим (Flag) | Основной драйвер прибыли | Роль TrendH | Критерии отбора монет |
| :--- | :--- | :--- | :--- |
| **`FOR_GRID_ONLY`** | **Сеточник** (`cron3Papper`) | Не используется (автономно) | Исключительно метрики сетки: **50% вес чистого Net PnL**, 20% N/R ($\ge 0.70$), 15% R/R ($< 1.0$), 15% MDME ($< 0.05$). |
| **`FOR_GRIDE_FIRSTABLE`** | **Сеточник** (`cron3Papper`) | Хеджер-страховщик (`SHADOW_50`) | $\text{N/R} \ge 0.70$, $\text{R/R} < 1.0$, $\text{MDME} < 0.05$. Фильтр ловушек пилы ($\text{TrendH Net} \ge -10\$). |
| **`FOR_TRENDH_ONLY`** | **TrendH** (Пробои / Откаты / Импульсы) | Автономный трейдер | Максимальная волатильность, объемный импульс HVH, WinRate $\ge 50\%$, TrendH Net $> 0$. |
| **`FOR_TRENDH_FIRSTABLE`** | **TrendH** (Жнецы / Ракетоловы) | Главный источник дохода | **Обязательно $\text{Comb Net} \ge 0$**, $\text{TrendH Net} > 0$, $\text{DRME} \ge 0.035$. |

### Подробное описание режимов:

1. **`FOR_GRID_ONLY` (Pure Grid Standalone)**:
   * Задача: Идеальный набор для автономной работы сеточника без хеджирования.
   * Распределение весов скоринга (100%):
     - **50% — Чистый Net Profit** ($\text{Grid Net} > 0$).
     - **20% — Эффективность N/R** ($\text{Net} / \text{Realized}$).
     - **15% — Риск/Доходность R/R** (чем ниже просадка к прибыли, тем лучше).
     - **15% — Глубина просадки MDME** (устойчивость к сквизам).
   * Данные TrendH полностью игнорируются. Отбираются монеты-тяжеловесы по реальной чистой прибыли.

2. **`FOR_GRIDE_FIRSTABLE` (Grid-First Symbiosis)**:
   * Задача: Максимизировать прибыль сеточника при нулевом шуме со стороны хеджера.
   * Поведение Жнеца: На отобранных монетах («Денежные коровы») сетка закрывается на уровнях 0–2. Порог $50\%$ объема не достигается, поэтому `SHADOW_HARVESTER_50` **полностью спит** и не платит стоп-лоссы. Хеджер просыпается исключительно при редких черных лебедях.

3. **`FOR_TRENDH_ONLY` (Trend-First Standalone)**:
   * Задача: Идеальный набор для самостоятельной работы трендового бота без привязки к сеточнику.
   * Отбираются монеты с выраженной направленной динамикой, высоким винрейтом на импульсах и откатах, отсекаются тухлые неликвиды.

4. **`FOR_TRENDH_FIRSTABLE` (TrendH-First Symbiosis)**:
   * Задача: Собрать монеты-«ракеты», где трендовый бот Жнец зарабатывает сверхприбыль на сильных безоткатных движениях, а сеточник выступает генератором сетки и дает разведданные об уровне стресса.
   * **Золотое правило отбора ($\text{Comb Net} \ge 0$):** Суммарная прибыль по монете ($\text{Grid Net} + \text{TrendH Net}$) **обязана быть положительной**.
     - *Пример успеха (`GUSDT`):* Сеточник $-\$13.35$, Жнецы $+\$110.31$ $\longrightarrow$ $\text{Comb Net} = \mathbf{+\$96.96}$ (Великолепная синергия!).
     - *Пример дисквалификации (`ZAMAUSDT`):* Сеточник $-\$50.58$, Жнецы $+\$13.50$ $\longrightarrow$ $\text{Comb Net} = \mathbf{-\$37.08}$ (Отказ! Просадка сетки превышает доход Жнецов).
   * **Мульти-стратегическая оценка:** Данные Жнецов агрегируются по пулу лучших стратегий (`DEFAULT_TRENDH_TARGET_STRATEGIES`): `u_shadow_harvester_50`, `u_shadow_harvester_40`, `u_delta_harvester`, `u_delta_sniper_15m`, `u_hvh_delta_symbiosis`.

---

## 4. Золотая формула и кластерная модель монет

При ограниченном депозите (5–10 монет в пуле) портфель балансируется по двухкластерной модели:

```
[БОЕВОЙ ПОРТФЕЛЬ (6-8 монет)]
   │
   ├── 🟢 КЛАСТЕР 1: «Денежные коровы» (50% портфеля)
   │     • CROSSUSDT (Net: +26.58$, N/R: 0.85, R/R: 0.81)
   │     • MIRAUSDT  (Net: +10.88$, N/R: 0.75, R/R: 0.38)
   │     • AIAUSDT   (Net: +14.45$, N/R: 0.85, R/R: 1.27)
   │     • AEROUSDT  (Net: +6.31$,  N/R: 0.76, R/R: 0.52)
   │     └─> Сеточник стабильно забирает кэш. Жнец спит (0 сделок, 0 стопов).
   │
   ├── 🚀 КЛАСТЕР 2: «Трендовые ракеты» (50% портфеля)
   │     • GUSDT     (TrendH PnL: +39.70$, WR: 64%, DRME: 0.154)
   │     • ZAMAUSDT  (TrendH PnL: +7.15$,  WR: 73%, DRME: 0.046)
   │     • ENAUSDT   (TrendH PnL: +5.81$,  WR: 70%, DRME: 0.050)
   │     └─> Сеточник растягивает сетку, Жнец заходит крупным объемом и снимает верха.
   │
   └── ❌ ЧЕРНЫЙ СПИСОК: «Ловушки пилы» (СТРОГО ИСКЛЮЧИТЬ)
         • PIEVERSEUSDT (Обманчивый лидер сеточника: Жнец на нем -$18.43 из-за пилы).
         • SOLVUSDT, STXUSDT (Низкий винрейт хеджера, распил на стопах).
```

---

## 5. Архитектура исполнения в реальном бою

При переходе на реальный депозит с 1 аккаунтом действует принцип **Multi-Signal Execution Pool**:
1. **Единый маржинальный кулак:** Все средства находятся на одном субсчете/аккаунте. Это дает максимальную маржинальную прочность для сеточника и исключает локальный маржин-колл при простаивании соседних счетов.
2. **First-Trigger Mutex (1 монета = 1 позиция):** 
   * Конфигурируемый лимит позиций на монету: `max_open_positions_per_coin: 1`.
   * Если импульсник вошел в позицию — монета блокируется для других стратегий, исключая перегруз плеча.
3. **Owner-based Exit (Правило создателя сделки):**
   * Стратегия, открывшая сделку, закрывает её по своим правилам (снайпер ждет далекую цель, скальпер выходит по быстрому трейлингу). -->














<!-- 1. "CALC_SPREAD_METHOD": "dominanta_premium",


вырезай арбитражную идею -- спреды.

2. оставь методы бинанса фьючерсы (адапторы апи).

3. KUCOIN_API_KEY=6a85c5c1733edc00015a6d2d
KUCOIN_API_SECRET=da7f0b5d-ac40-4315-b5b5-282d73764a0c
KUCOIN_API_PASSPHRASE=Hero6633

этого не будет.

1. оставь 2 индикатора:

        "trend": {
            "is_active": true,
            "sma_fast": 10,
            "sma_slow": 30,
            "confirmation_candles": 5,
            "require_rising": true,
            "trend_positive": true
        },

+ рси. рси сделай всего один. если рси от 50 до 70 (потолок может принимать параметр null то есть его не быть) (и плюс наш тренд -- строго восходлящий) то входим в лонг. если ниже 50 и до 30 + наш тренд (строго падающий) то в шорт. Возможен хедж режим (наличие одновременно двух позиций и лонг и шорт).

выход -- при первой смене трнеда либо по тейк-профиту (его пока поставишь в настройках в null)/
"DIRECTION_MODE": 3, это хорошо но там в логике моно режим. надо добавить опцию хедж тру или фолс.

Метаскальп и намеки на боевое состояние -- полность. вырезаем.

Это будет чисто бумажный бот.

сущность fresh_backtest тоже удаляем.

Аналитику и тг интерфейс делаем как в проекте -- C:\Users\user\Desktop\My_Pro\HP_EliteBook_735_old\MY\HRON_3\cron3Papper

дальше. по поводу сайза позиции и монет.

Бот должен быть мультисимвольным.

если конфигурации списка символов и размера позиций пер символ не заданы то идем в проект который будет указан в конфигах как источник символов и размера позиции:

-- C:\Users\user\Desktop\My_Pro\HP_EliteBook_735_old\MY\HRON_3\cron3Papper

заходим в 
C:\Users\user\Desktop\My_Pro\HP_EliteBook_735_old\MY\HRON_3\cron3Papper\CFG.app.json и читаем поле
symbols -- оттуда берем символы.

сайзы чуток из другого места --
C:\Users\user\Desktop\My_Pro\HP_EliteBook_735_old\MY\HRON_3\cron3Papper\CFG\runtime ... там будет список живых файлов которые будут отображать рантайм состояния монет (сайз и степень усредненности), смотрим общий  сайз и степень усредненности (по флагам) (в качестве примера привожу базовый шаблон но в рантайме эти поля идентичны --
{
    "LONG": {
        "enable": true,
        "invest_size": 400,
        "leverage": 10,
        "margin_type": "CROSSED",
        "_comment_margin_type": "Valid values: CROSSED | ISOLATED",
        "grid": {
            "0": {
                "indent": 0,
                "volume": 12.96,
                "super_indent": null
            },
            "1": {
                "indent": -5.0,
                "volume": 14.26,
                "super_indent": null
            },
            "2": {
                "indent": -8.0,
                "volume": 15.68,
                "super_indent": null
            },
            "3": {
                "indent": -13.0,
                "volume": 17.25,
                "super_indent": null
            },
            "4": {
                "indent": -21.0,
                "volume": 18.98,
                "super_indent": null
            },
            "5": {
                "indent": -34.0,
                "volume": 20.87,
                "super_indent": null
            }
        },
        "tp_purpose": "both",
        "tp_map": {
            "0": {
                "indent": 0.6,
                "fallback_indent": 1.0
            },
            "1": {
                "indent": 0.7,
                "fallback_indent": 1.6
            },
            "2": {
                "indent": 1.0,
                "fallback_indent": 2.3
            },
            "3": {
                "indent": 1.4,
                "fallback_indent": 3.0
            },
            "4": {
                "indent": 1.9,
                "fallback_indent": 3.6
            },
            "5": {
                "indent": 2.5,
                "fallback_indent": 4.0
            }
        }
    },
    "SHORT": {
        "enable": true,
        "invest_size": 400,
        "leverage": 10,
        "margin_type": "CROSSED",
        "_comment_margin_type": "Valid values: CROSSED | ISOLATED",
        "grid": {
            "0": {
                "indent": 0,
                "volume": 12.96,
                "super_indent": null
            },
            "1": {
                "indent": -5.0,
                "volume": 14.26,
                "super_indent": null
            },
            "2": {
                "indent": -8.0,
                "volume": 15.68,
                "super_indent": null
            },
            "3": {
                "indent": -13.0,
                "volume": 17.25,
                "super_indent": null
            },
            "4": {
                "indent": -21.0,
                "volume": 18.98,
                "super_indent": null
            },
            "5": {
                "indent": -34.0,
                "volume": 20.87,
                "super_indent": null
            }
        },
        "tp_purpose": "both",
        "tp_map": {
            "0": {
                "indent": 0.6,
                "fallback_indent": 1.0
            },
            "1": {
                "indent": 0.7,
                "fallback_indent": 1.6
            },
            "2": {
                "indent": 1.0,
                "fallback_indent": 2.3
            },
            "3": {
                "indent": 1.4,
                "fallback_indent": 3.0
            },
            "4": {
                "indent": 1.9,
                "fallback_indent": 3.6
            },
            "5": {
                "indent": 2.5,
                "fallback_indent": 4.0
            }
        }
    },
    "super_grid": {
        "enabled": false
    }
}

например сайз 400 м ыусреднились три раза (вытаскиваем поле объема) и флаги усреднений -- если флаги тру то плюбсуем объемы, например наплюсовали 40% объема * 400 долларов -- 160 долларов -- переводим в количество базового актива (как и надо для банана) и себе в переменной пишем (стата позиции).

когда входим -- фиксируем цену входа. когда выходим фиксируем цену выхода (еще раз смотри как это реализовано в бумажном сеточнике) -- C:\Users\user\Desktop\My_Pro\HP_EliteBook_735_old\MY\HRON_3\cron3Papper

...

и как я уже сказал аналитику и тг интерфейс делаем такую же как в бумажом сеточнике cron3Papper.

выкатывай план имплементации. -->



<!-- добавь еще вот какую стратегию.

еще предыдущего поколения стратегию:
        "trend": {
            "is_active": true,
            "timeframe": "5m",
            "sma_fast": 10,
            "sma_slow": 30,
            "confirmation_candles": 3,
            "require_rising": true,
            "trend_positive": true,
            "long_cond": "UP",
            "short_cond": "DOWN"
        }, +
        "trend": {
            "is_active": true,
            "timeframe": "5m",
            "sma_fast": 10,
            "sma_slow": 30,
            "confirmation_candles": 3,
            "require_rising": true,
            "trend_positive": true,
            "long_cond": "UP",
            "short_cond": "DOWN"
        },
        "trend_htf": {
            "is_active": true,
            "timeframe": "1h",
            "sma_fast": 10,
            "sma_slow": 30,
            "confirmation_candles": 2,
            "require_rising": true,
            "trend_positive": true,
            "long_cond": "UP",
            "short_cond": "DOWN"
        },
        "rsi": {
            "is_active": true,
            "timeframe": "5m",
            "window": 14,
            "conditions": {
                "ENTER_LONG": "50 < x <= 70",
                "ENTER_SHORT": "30 <= x < 50"
            }
        },

только оценка сигнала шиворот навыворот. вместо плановых лонгов -- шорты а вместо плановых шортов лонги. раз она так сильно и стремительно сливала знячит нужно сделать антидурака

Сделай анализ данных по стратегиям. Отдели пшеницу от шелухи. Предложи как усилить рабочие полурабочие варианты. Добавь стратегий. по всплеску объема вижу надо условия естче поставить


еще. рецензия кода другого агента:

Главная ловушка импульсных систем — наплодить десятки индикаторных вариаций и получить ложную подгонку под историю (overfitting / p-hacking), которая моментально сгорает на комиссиях и пилообразном флэте. Импульс усиливается не новыми осцилляторами, а жестким контекстным ситом и микроструктурой.1. Контекст и относительная сила (Universe Selection)Relative Strength к бенчмарку: Одиночный импульс монеты в вакууме часто оказывается ложным. Фильтруйте Universe по силе актива относительно BTC: вход оправдан только тогда, когда темп прироста цены монеты опережает поводыря на статистически значимую величину (Z-score доходности выше 1.5–2.0).Сжатие перед взрывом (Volatility Squeeze): Лучший импульс рождается из затухания волатильности. Открывайте позиции, только если текущий ATR находится в нижнем 15–20-м перцентиле своего диапазона за последние несколько дней, после чего происходит резкое расширение полос Боллинджера или взрывной рост диапазона свечи. Импульс на уже перегретой волатильности — это вход в кульминацию движения.2. Микроструктурные фильтры (Order Flow)Динамика открытого интереса (OI): Истинный трендовый импульс сопровождается синхронным ростом Open Interest — это маркер притока свежей ликвидности. Если резкий свечной вынос идет на падающем OI, вы берете шорт-сквиз или каскад стоп-лоссов, за которым с высокой вероятностью последует жесткий V-образный откат.Кумулятивная дельта объемов (CVD): Пробой локального уровня должен подтверждаться доминированием агрессивных рыночных покупок (Taker Buy Ratio), а не отсутствием лимитных заявок в стакане.3. Тайм-стопы и асимметрия рисковTime-based Stop: Импульс обязан отрабатывать сразу. Если за 3–5 свечей после сигнала цена не прошла расчетное расстояние ($1 \times \text{ATR}$), гипотеза импульса несостоятельна. Выходите по рынку, не дожидаясь срабатывания защитного стопа.Отказ от фиксированных тейков: Импульсные стратегии живут за счет длинного правого хвоста распределения прибыли (Fat Tails). Используйте ступенчатый трейлинг по экстремумам свечей или Chandelier Exit, фиксируя только часть позиции для покрытия комиссий.4. Валидация пула гипотезШтраф за множественное тестирование: При отборе из 100 вариантов используйте Deflated Sharpe Ratio (DSR), чтобы учесть число итераций перебора.Плато стабильности: Отбирайте только те параметры, которые образуют плоское «плато» доходности с соседними значениями, а не изолированные пики.Какую конкретно механику детекции импульса вы сейчас тестируете в CORE/rules.py — пробой локальных уровней (SR), волатильностный прорыв или всплеск объема?

жду план. 


еще. буквально за пару минут:

🌐 Вселенная: EMA Acceleration (TP 3%, SL 1.5%)
Боевой кроссовер EMA 9/21 с фильтром дельты + объем + 1h HTF, TP 3.0%, SL 1.5%

• Стартовый баланс: 0.00 USDT
• Текущий баланс: -179.42 USDT
• Чистый профит: -179.4166 USDT (+0.00%)
• Реализованный PnL: 0.1834 USDT
• Нереализованный PnL: +0.0000 USDT (0 поз.)
• Всего сделок: 374 (Побед: 218 | Winrate: 58.3%)
• Макс. просадка (DD): -179.4166 USDT
• Фактор восстановления: -1.00

ну это сильно. под таких дураков надо явно антистратегию ставить (вместо лонгов шорт вместо шортов лонг (и со стопами и тейками соотношение тоже перестроить наоборот)). например TP 3.0%, SL 1.5% поменять на TP 1.5%, SL 3.0%

хоть я ищу именно и импульсную стратгию, это кк минимум достойно внимания.

это то же:

🌐 Вселенная: Momentum Kick-off (TP 3.5%, SL 1.5%)
Пробой ватерлинии RSI 50 + всплеск объема (rolling) + 1h HTF, TP 3.5%, SL 1.5%

• Стартовый баланс: 0.00 USDT
• Текущий баланс: -64.70 USDT
• Чистый профит: -64.7032 USDT (+0.00%)
• Реализованный PnL: -0.1432 USDT
• Нереализованный PnL: +0.0000 USDT (0 поз.)
• Всего сделок: 120 (Побед: 57 | Winrate: 47.5%)
• Макс. просадка (DD): -64.7032 USDT
• Фактор восстановления: -1.00

--- -->

<!-- ## 2. Итоги архитектурных улучшений (Сентябрь 2026):
1. **Низкоуровневая база (C/LLVM через Numba JIT)**: Тяжелая математика (`EMA`, `RSI`, `ATR`, пивоты `LuxAlgo`, сжатие `Bollinger/Keltner`) переведена на C-уровень с `nogil=True` и `fastmath=True` (`CORE/native_math.py`). Устранен медленный `sliding_window_view`.
2. **Защита от захлеба Asyncio**: Внедрена двухуровневая модель тиков (мгновенная запись потока в `RealtimeFlowTracker` <1 мкс + троттлинг оценки вселенных до 50 мс на монету) + кооперативный `await asyncio.sleep(0)`. Нагрузка на CPU снижена на >80%, гонки исключены.
3. **Смотрящая собака (Watchdog)**: Восстановлен легковесный адаптер по образу `cron3Papper` (`CORE/watchdog.py`). Отстукивает ритм в Telegram каждые 60с редактированием сообщения, автоудаляет старые через 180с (чистый чат) и алертит при зависаниях главного цикла >60с.
4. **Анти-стратегии без оверинжиниринга**: Конфигурации для анти-стратегий (`u1_anti`, `u3_anti`, `u6_anti`) прописаны напрямую и открыто в `cfg.json`. Адаптер правил (`CORE/rules.py`) тупо читает эти конфигурации (включая `conditions` для RSI и `long_cond`/`short_cond` для тренда) без костылей и хардкода.
5. **Obsidian Wiki**: База знаний в `WORKSPACE/COMMON/wiki/trendH` актуализирована (`Overview.md`, `Indicators_Engine.md`, `Watchdog_and_Async_Architecture.md`).
6. **Интеллектуальный антиспамер логов (LogAntiSpammer)**: Внедрен в `c_log.py` (`UnifiedLogger`). Автоматически подавляет циклический спам однотипных ошибок и ворнингов с подсчетом подавленных повторов (`[Повторено N раз за X.Xs]`), никогда не глушит критические события (`[SIGNAL ENTRY]`, `[SIGNAL EXIT]`, `[POSITION OPEN]`, `[CLOSE ALL]`, `[WATCHDOG]`), устранены все неконтролируемые `traceback.print_exc()`.
7. **Живой расчет Текущего баланса (Equity) и стартового депозита**: Устранена рассинхронизация, когда `Текущий баланс` и `Чистый профит` в Telegram не учитывали открытые сделки. Теперь `live_cur_bal = start_bal + realized_pnl + unrealized_pnl`, а `live_net_profit = realized_pnl + unrealized_pnl`. В `cfg.json` и `ANALYTICS` внедрен параметр `default_start_balance` (1000 USDT), устранивший нулевой баланс виртуальных вселенных. -->


<!-- 
Новое:
Мой вопрос:
    Привет. Конфиг посмотрел. Сетка: 6 уровней, суммарный объем 100, уровни -5/-8/-13/-21/-34%, TP 0.6-2.5% (fallback 1-4%). Логика trendH: если LONG-сетка набрала много лонга и цена продолжает падать — trendH шортит; если SHORT-сетка набрала много шорта и цена продолжает расти — trendH лонгует. Иначе говоря, direction = opposite(grid_stressed_side). Это и есть забор безоткатного движения.

Ответ от Дип Сик:

    Привет. Конфиг посмотрел: сетка 6 уровней, суммарный объём ровно **100** (12.96+14.26+15.68+17.25+18.98+20.87), уровни усреднения **-5 / -8 / -13 / -21 / -34%**, TP от **0.6% до 2.5%** (fallback 1–4%). Это классическая мартингейл-сетка, которая хорошо живёт в пиле, но плохо — в безоткатном тренде.

    Ключевая идея trendH:  
    **Если LONG-сетка набрала много лонга и цена продолжает падать — trendH шортит. Если SHORT-сетка набрала много шорта и цена продолжает расти — trendH лонгует.**  
    То есть направление trendH = **против “застрявшей” стороны сетки**, но **по направлению импульса**. Так второй аккаунт забирает то движение, которое ломает сеточника.

    Ниже 3 оптимальных решения — от простого к сложному.

    ---

    ## Решение 1. Inventory-Stress Momentum Overlay (рекомендую как базу)

    **Суть:** trendH получает от сеточника состояние инвентаря по каждому символу/стороне и входит в импульс только тогда, когда сетка уже набрала объём и продолжает терпеть убыток.

    ### Связка с сеточником
    Нужен shared-state слой: Redis/Postgres/файл/API. Сеточник пишет:
    - symbol;
    - side: LONG/SHORT;
    - filled_levels;
    - accumulated_volume;
    - grid_volume_ratio = accumulated_volume / 100;
    - weighted_avg_price;
    - unrealized_pnl;
    - last_tp_time;
    - time_in_drawdown.

    ### Условия входа
    Для LONG-сетки, которая попала в даунтренд:
    - grid_volume_ratio >= 0.5–0.6 (заполнены уровни 0–3);
    - цена ниже weighted_avg_price и ниже уровня 2–3;
    - трендовый фильтр:
    - EMA50 < EMA200;
    - ADX(14) > 25 и растёт;
    - ATR(14) > ATR(50) * 1.2;
    - Efficiency Ratio > 0.35;
    - объём > 1.5× среднего;
    - цена закрылась ниже последнего swing low.
    - funding не в экстремально отрицательной зоне (чтобы не попасть в short-squeeze).

    Для SHORT-сетки — зеркально.

    ### Добавления
    - первый вход: 30–40% от целевого размера при ratio >= 0.5;
    - второй: +30% при ratio >= 0.7 и пробое следующего уровня;
    - третий: +30% при ratio >= 0.85–1.0 и продолжении тренда.

    ### Выход
    - 20–25% на +15–20%;
    - 20–25% на +30–40%;
    - 20–25% на +50–70%;
    - остаток 25–30% вести трейлингом: Chandelier Exit (3×ATR) или EMA50.
    - Полный выход, если:
    - сеточник начал закрывать позицию по TP;
    - ADX < 20;
    - цена вернулась выше/ниже EMA50;
    - прошло N баров без прогресса.

    **Плюсы:** просто, прозрачно, легко бэктестить.  
    **Минусы:** можно опоздать на 10–20% движения. Лечится ранним входом на уровне 2–3 и пирамидингом.

    ---

    ## Решение 2. Breakout of Grid Extreme + Pyramiding (агрессивное, для +30–100%)

    **Суть:** не входить “на среднем” движении, а ждать, когда цена пробивает **крайний уровень сетки** — уровень 4 или 5. Это точка максимального стресса сеточника. Если пробой подтверждается объёмом, trendH заходит в импульс и ведёт его до истощения.

    ### Логика для LONG-сетки
    - цена пробивает -21% (уровень 4) или -34% (уровень 5) и закрывается ниже;
    - breakout-свеча: объём > 2× среднего, ATR > 1.5× среднего;
    - OI растёт, funding не экстремально отрицательный;
    - trendH открывает SHORT.

    ### Пирамидинг
    - 30% на пробое уровня 4;
    - 30% на пробое уровня 5;
    - 40% на ретесте уровня 5 снизу, если цена не вернулась в диапазон.

    ### Выход
    - трейлинг 2.5–3×ATR от экстремума;
    - частичная фиксация на расширениях Фибоначчи: -1.272, -1.618, -2.0 от последнего swing;
    - остаток вести до:
    - смены режима (ADX падает, ATR сжимается, цена за EMA50);
    - начала закрытия сетки по TP;
    - возврата выше уровня 4.

    **Плюсы:** ловит именно безоткатные хвосты, может дать +30–100%.  
    **Минусы:** вход поздний, возможны резкие откаты. Обязателен жёсткий стоп за структурой или 1.5–2×ATR.

    ---

    ## Решение 3. Regime-Switching Ensemble / ML-фильтр (самое устойчивое)

    **Суть:** trendH не просто следует за ценой, а классифицирует режим рынка: range / trend-up / trend-down / exhaustion. Торгует только в trend-режиме, а инвентарь сетки использует как размер позиции и как риск-фильтр.

    ### Фичи
    - рыночные: ADX, ATR ratio, EMA slope, Efficiency Ratio, Bollinger width, volume delta, funding, OI, order book imbalance;
    - сеточные: grid_volume_ratio, расстояние до ликвидации, время в просадке, unrealized PnL, количество заполненных уровней.

    ### Вход
    - P(trend-down) > 0.7 и LONG grid_volume_ratio > 0.6 → SHORT;
    - P(trend-up) > 0.7 и SHORT grid_volume_ratio > 0.6 → LONG;
    - P(range) > 0.5 → торговля запрещена.

    ### Выход
    - P(trend) < 0.4;
    - P(exhaustion) > 0.6;
    - трейлинг-стоп;
    - сетка начала закрывать позицию.

    **Плюсы:** адаптируется к рынку, меньше ложных входов в боковике.  
    **Минусы:** сложно, нужны данные, бэктест, риск переобучения. Начинать только после Решения 1.

    ---

    ## Общая инфраструктура и риск

    1. **Второй аккаунт** — отдельные API-ключи, только торговля, без вывода, IP whitelist.
    2. **Изолированная маржа** для trendH. Плечо не 10×, а 2–5×. Иначе импульсный бот сам станет источником ликвидации.
    3. **Размер позиции trendH**:
    - риск на сделку 0.5–1% от equity trendH;
    - стоп = 1.5–2.5×ATR;
    - notional = risk / stop%;
    - cap: не более 30–50% от notional сетки, чтобы не перехеджировать.
    4. **Фильтр боковика**:
    - ADX > 25;
    - ER > 0.35;
    - ATR expansion;
    - объём > 1.5×;
    - пробой с закрытием, а не просто касание.
    5. **Выход из диспозиции**:
    - как только сеточник закрыл 50% инвентаря — закрыть 50% trendH;
    - закрыл 100% — закрыть trendH полностью;
    - либо трейлинг до смены режима.
    6. **Бэктест**:
    - исторические данные 1m/tick;
    - симулировать заполнение сетки;
    - учесть комиссии, funding, slippage;
    - отдельно проверить 2021 bull, 2022 bear, 2023 range, 2024–2025.

    ---

    ## Что выбрать

    - **Старт:** Решение 1 — Inventory-Stress Momentum Overlay. Оно прямо использует объёмы сеточника и даёт понятную логику.
    - **Усиление:** добавить Решение 2 для пробоев крайних уровней и пирамидинга.
    - **Долгосрок:** Решение 3, когда накопится статистика и появится инфраструктура для фичей.

    Если хочешь, могу расписать конкретные формулы для `stress_score`, `trend_score` и псевдокод входа/выхода под твой конфиг.

Редис и базы не нужны. Все будет в джейсоне в соседнм проекте. Путь -- уже прописан в конфигах --
        "symbols_path": "C:\\Users\\user\\Desktop\\My_Pro\\HP_EliteBook_735_old\\MY\\HRON_3\\cron3Papper\\CFG\\app.json",

        Пример файла app.json (поле symbols):

            {
        "app": {
            "time_zone": "UTC",
            "precision": 18,
            "spec_ttl_sec": 900,
            "time_slack_sec": 0.15,
            "req_timeout_sec": 10.0,
            "avoid_check_runtime_cfg": false,
            "api_rate_limit_sec": 0.2,
            "rest_failsafe_sec": 1.0,
            "income_pagination_delay_sec": 1.5,
            "post_close_sync_debounce_sec": 10.0,
            "bg_unrealized_poll_freq_sec": 10.0,
            "auto_start": true
        },
        "signal": {
            "timeframe": "5m",
            "smart_grace": {
                "start_period_sec": 90,
                "eval_window_sec": 300,
                "increments_card": {
                    "<2": 0,
                    ">=2": 120,
                    ">4": 150
                }
            }
        },
        "logging": {
            "debug": false,
            "info": true,
            "warning": true,
            "error": true,
            "max_log_lines": 10000,
            "log_to_console": false,
            "log_to_file": true
        },
        "symbols": [
        "ARXUSDT",
        "LAUSDT",
        "GIGGLEUSDT",
        "ROBOUSDT",
        "SOPHUSDT",
        "FLOCKUSDT",
        "ESPUSDT",
        "BOMEUSDT",
        "NAORISUSDT",
        "PUMPUSDT",
        "RIVERUSDT",
        "SIRENUSDT",
        "CHIPUSDT",
        "ARBUSDT",
        "ZAMAUSDT",
        "ENAUSDT",
        "PIEVERSEUSDT",
        "TRUMPUSDT",
        "CATIUSDT",
        "MOVRUSDT",
        "LITUSDT",
        "1000CATUSDT",
        "TUSDT",
        "CROSSUSDT",
        "ACUUSDT",
        "PEOPLEUSDT",
        "VVVUSDT",
        "VELODROMEUSDT",
        "1000BONKUSDT",
        "ZROUSDT",
        "GRASSUSDT",
        "ZECUSDT",
        "JTOUSDT",
        "GPSUSDT",
        "SAFEUSDT",
        "DOODUSDT",
        "ZORAUSDT",
        "FORMUSDT",
        "WLDUSDT",
        "KITEUSDT",
        "ZKCUSDT",
        "SOLVUSDT",
        "0GUSDT",
        "XPLUSDT",
        "GUSDT",
        "ETHFIUSDT",
        "UNIUSDT",
        "FARTCOINUSDT",
        "SPXUSDT",
        "DASHUSDT",
        "NEIROUSDT",
        "STXUSDT",
        "EIGENUSDT",
        "SCRUSDT",
        "FFUSDT",
        "SYRUPUSDT",
        "PLAYUSDT",
        "PYTHUSDT",
        "LDOUSDT",
        "DOGSUSDT",
        "RAYSOLUSDT",
        "MIRAUSDT",
        "AIAUSDT",
        "TRBUSDT",
        "1000PEPEUSDT",
        "AEROUSDT",
        "MEGAUSDT",
        "JUPUSDT",
        "CFGUSDT",
        "ADAUSDT",
        "PENGUUSDT",
        "XVGUSDT",
        "IOSTUSDT",
        "AAVEUSDT"
    ],
        "telegram": {
            "enabled": true,
            "allowed_users": [
                610822492
            ]
        },
        "super_grid": {
            "enabled": true,
            "_comment_timeframe": "Valid values: 1m, 3m, 5m, 15m, 30m, 1h, 2h, 4h, 6h, 8h, 12h, 1d, 3d, 1w, 1M",
            "timeframe": "1w",
            "window": 12,
            "multiplier": 2.0,
            "min_volatility_pct": 15.0,
            "max_volatility_pct": null,
            "update_interval_hours": 24
        },
        "volatility_scanner": {
            "timeframe": "1w",
            "window": 12,
            "min_volatility_pct": 25.0,
            "max_volatility_pct": 40.0,
            "strict_window": true,
            "min_dayly_vol_usdt": 3000000
        },
        "watchdog": {
            "timeout_sec": 60,
            "check_interval_sec": 1,
            "heartbeat_interval_sec": 60,
            "heartbeat_autodelete_sec": 180
        },
        "backup": {
            "enabled": true,
            "debounce_sec": 10,
            "max_interval_sec": 300
        },
        "notifications": {
            "enabled": true,
            "negative_threshold": -20.0,
            "positive_threshold": 20.0
        },
        "auto_closing": {
            "negative": {
                "threshold": null,
                "threshold_increment": null
            },
            "positive": {
                "threshold": 20,
                "threshold_increment": 20
            }
        },
        "stop_bot_rirk_system": {
            "enabled": false,
            "roi_critical_level_pct": -41
        }
    }



        "runtime_path": "C:\\Users\\user\\Desktop\\My_Pro\\HP_EliteBook_735_old\\MY\\HRON_3\\cron3Papper\\CFG\\runtime",

        Пример runtime/ смотри в артефакте текущего проекта -- artefacts/runtime.tar.gz -->
<!-- 
##

    # ///////
    def hvh_calc(self, df, ind_rules):
        """
        HVH-индикатор с режимами:
        - "fixed": фиксированная макс. девиация за окно
        - "rolling": скользящее макс. отклонение

        ind_rules:
            - "period": окно MA и девиации
            - "dev": множитель девиации
            - "mode": "fixed" или "rolling"
            - "is_trend": 1 или 0
        """
        try:
            ma_period = int(ind_rules.get("period", 0))
            deviation_rate = float(ind_rules.get("dev", 1.0))
            is_trend = int(ind_rules.get("is_trend", 1))
            mode = ind_rules.get("mode", "rolling").lower()

            if ma_period <= 0:
                raise ValueError("hvh_calc: параметр 'period' должен быть положительным.")

            if len(df) < ma_period:
                return pd.Series(dtype=int, index=df.index, name="HVH")

            close = df["Close"]
            high = df["High"]
            low = df["Low"]

            ma = close.rolling(window=ma_period, min_periods=ma_period).mean()
            high_dev = np.where(high > ma, (high - ma).abs(), 0)
            low_dev = np.where(low < ma, (ma - low).abs(), 0)
            deviation = pd.Series(np.maximum(high_dev, low_dev), index=df.index)

            if mode == "fixed":
                valid_dev = deviation[-ma_period:].dropna()
                if valid_dev.empty:
                    raise ValueError("hvh_calc: недостаточно валидных данных для fixed-девиации.")
                
                max_dev = valid_dev.max()
                adj_dev_value = max_dev * deviation_rate
                adj_dev = pd.Series(adj_dev_value, index=df.index)

            elif mode == "rolling":
                rolling_max_dev = deviation.rolling(window=ma_period, min_periods=ma_period).max()
                adj_dev_series = rolling_max_dev * deviation_rate
                adj_dev = pd.Series(adj_dev_series, index=df.index)

            else:
                raise ValueError("hvh_calc: неизвестный режим. Используйте 'fixed' или 'rolling'.")

            direction = np.where(close >= ma, 1, -1)
            trigger = ma + (adj_dev * direction)

            raw_signals = np.zeros(len(close), dtype=np.int8)
            raw_signals[(close >= trigger) & (direction == 1)] = 1 * is_trend
            raw_signals[(close <= trigger) & (direction == -1)] = -1 * is_trend
            filtered = filter_signals(raw_signals)

            return pd.Series(filtered, index=df.index, name="HVH")

        except Exception as ex:
            print(f"hvh_calc: {ex}")
            return pd.Series(dtype=int, index=df.index, name="HVH") (этот пробойный надо будет инвертировать и сделать отскокочным)   


            +



class TrendCalculator:
    """Изолированный калькулятор тренда на базе быстрой и медленной EMA."""

    def __init__(self, cfg: Dict[str, Any]):
        self.is_active: bool = bool(cfg["is_active"])
        self.timeframe: str = str(cfg["timeframe"])
        self.sma_fast: int = int(cfg["sma_fast"])
        self.sma_slow: int = int(cfg["sma_slow"])
        self.confirmation_candles: int = int(cfg["confirmation_candles"])
        self.require_rising: bool = bool(cfg["require_rising"])

    def calculate(self, closes: List[float]) -> str:
        """
        Классифицирует состояние рынка по ценам закрытия:
        - UP: быстрая EMA выше медленной на протяжении N свечей (и растет, если require_rising=True)
        - DOWN: быстрая EMA ниже медленной на протяжении N свечей (и падает, если require_rising=True)
        - FLAT: расхождение условий либо боковое движение
        - UNSTABLE: недостаточно свечей для расчета
        """
        if not self.is_active or not closes:
            return "UNSTABLE"

        ema_fast = IndicatorsMath.calc_ema(closes, self.sma_fast)
        ema_slow = IndicatorsMath.calc_ema(closes, self.sma_slow)

        if not ema_fast or not ema_slow or len(ema_fast) < self.confirmation_candles:
            return "UNSTABLE"

        ef_tail = ema_fast[-self.confirmation_candles:]
        es_tail = ema_slow[-self.confirmation_candles:]

        is_above = all(f > s for f, s in zip(ef_tail, es_tail))
        is_below = all(f < s for f, s in zip(ef_tail, es_tail))
        is_rising = all(ef_tail[i] > ef_tail[i - 1] for i in range(1, len(ef_tail)))
        is_falling = all(ef_tail[i] < ef_tail[i - 1] for i in range(1, len(ef_tail)))

        if is_above and (not self.require_rising or is_rising):
            return "UP"
        elif is_below and (not self.require_rising or is_falling):
            return "DOWN"
        else:
            return "FLAT"


            -- уже у нас есть.


Рецензия другого агента:

# trendH — модуль «HVH-Pullback + EMA-Regime»

Да, теперь картинка сходится. То, что ты описываешь, — это классический **trend + pullback entry**: направление берём у тренда, точку входа — у инвертированного HVH. Разберу по шагам, как это собрать в один модуль и встроить в trendH.

---

## 1. Ядро идеи

**Инвертированный HVH** = mean-reversion триггер:
- `close >= MA + dev` → **SHORT-триггер** (цена растянута вверх);
- `close <= MA - dev` → **LONG-триггер** (цена растянута вниз).

**TrendCalculator** = режим:
- `UP` / `DOWN` / `FLAT` / `UNSTABLE`.

**Сделка открывается только когда оба совпадают по направлению:**

| TrendCalculator | Inverted HVH | Действие |
|---|---|---|
| DOWN | SHORT (растяжка вверх) | **SHORT** — продаём отскок в даунтренде |
| UP | LONG (растяжка вниз) | **LONG** — покупаем пролив в аптренде |
| DOWN | LONG | пропуск (контр-тренд) |
| UP | SHORT | пропуск |
| FLAT / UNSTABLE | любое | пропуск |

Это ровно та логика, которую ты хотел: **не пробой, а вход на откате в сторону тренда**. В боковике сделок нет — FLAT отсекает.

---

## 2. Формула инвертированного HVH

Берём твой `hvh_calc` на старший ТФ (H4 / D1) и делаем ровно две правки:

```python
# было:
raw_signals[(close >= trigger) & (direction == 1)] = 1 * is_trend
raw_signals[(close <= trigger) & (direction == -1)] = -1 * is_trend

# станет (контртренд):
raw_signals[(close >= trigger) & (direction == 1)] = -1 * is_trend
raw_signals[(close <= trigger) & (direction == -1)] =  1 * is_trend
```

Всё остальное (`mode`, `dev`, `period`, `filter_signals`) — как есть.

**Рекомендации по параметрам для старшего ТФ:**
- `period`: 50–100 (MA на H4/D1);
- `dev`: 1.5–2.2 (ниже — много ложных, выше — редкие входы);
- `mode`: `rolling` (адаптируется к волатильности);
- `is_trend`: 1.

---

## 3. Связка с инвентарём сеточника

Это то, что отличает твой trendH от обычного pullback-бота.

Для каждого символа читаем state сеточника:

```
side        = LONG | SHORT
filled      = 0..5
vol_ratio   = accumulated_volume / 100
avg_price   = weighted avg сетки
uPnL        = unrealized PnL сетки
drawdown_t  = время в просадке
```

**Дополнительные условия входа (помимо HVH + TrendCalculator):**

Для SHORT-входа (ловим даунтренд, LONG-сетка в стрессе):
- `side == LONG`;
- `filled >= 3` и `vol_ratio >= 0.6`;
- `uPnL < 0` (сетка реально в минусе);
- направление TrendCalculator = `DOWN`;
- inverted HVH дал SHORT.

Для LONG-входа — зеркально (SHORT-сетка, filled >= 3, `UP`, inverted HVH дал LONG).

Если сеточник по символу в плюсе или не набрал объём — **trendH не входит**, даже если HVH+Trand совпали. Это твой главный риск-фильтр: не открываться «в пустоту».

---

## 4. Confirmation на младшем ТФ

HVH на H4/D1 даёт редкий, но «жирный» сигнал. Чтобы не поймать ранний отскок, который ещё не закончился, добавь микро-подтверждение на M15/H1:

**Для SHORT-входа (после HVH+Trend+Grid):**
- на M15 свеча закрылась обратно ниже EMA20, **или**
- bearish engulfing / pin bar у верхней границы HVH-канала, **или**
- ADX(M15) > 20 и растёт.

**Для LONG — зеркально.**

Это отсекает «ловлю ножей» и входы в момент, когда растяжка только формируется.

---

## 5. Дополнительные фильтры от боковика

Даже если FLAT отсекает большую часть, добавь:

- ADX(H4) > 22 — иначе тренд вялый;
- ATR(14) / ATR(50) > 1.1 — волатильность растёт;
- |EMA_fast − EMA_slow| / EMA_slow > 0.005 — реальное расхождение, а не почти слипшиеся EMA;
- `require_rising = True` в TrendCalculator — чтобы fast EMA реально шла в сторону тренда, а не просто была выше.

Пункт про `require_rising=True` — важный. Без него TrendCalculator может дать `UP`, когда fast выше slow, но уже загибается — а это начало разворота.

---

## 6. Размер позиции и пирамидинг

Базовая формула:

```
risk_per_trade = 0.5–1.0% от equity trendH
stop           = max(1.5 * ATR(H4), 1.0% от entry)
notional       = risk_per_trade * equity / stop_pct
cap_notional   = 0.4 * notional_grid (чтобы не перехеджировать)
```

**Пирамидинг (для отработки движений +30–100%):**
- 40% на первом входе (HVH + Trend + Grid + M15 confirm);
- 30% при закрытии M15/H1 в сторону позиции и сохранении режима;
- 30% при пробое последнего swing low (для шорта) / swing high (для лонга).

После третьего добора стоп подтягивается в безубыток по средней.

**Не масштабируй, если `vol_ratio` сеточника упал** (сетка начала закрывать TP) — это признак, что импульс выдохся.

---

## 7. Выход — под задачу «не дешевить»

Цель — забрать +30–100%, а не +5%. Значит, выход — **лестница + трейлинг**, а не фикс на первом профите.

**Лестница фиксации:**
- +15–20% → снять 15%;
- +30–40% → снять 20%;
- +50–60% → снять 20%;
- остаток 45% вести трейлингом.

**Трейлинг остатка — по одному из:**
- Chandelier Exit: `highest_high − 3×ATR(H4)` для лонга;
- либо EMA50 на H1 как динамический стоп;
- либо параболический SAR на H4.

**Принудительный выход (полный или частичный):**
- TrendCalculator перешёл в `FLAT` → закрыть 50%;
- inverted HVH дал сигнал **против** позиции → закрыть 30%;
- сеточник закрыл >= 50% инвентаря по TP → закрыть 50% trendH;
- сеточник полностью разгрузился → закрыть trendH полностью;
- ADX(H4) упал ниже 18 → закрыть всё;
- прошло N баров без нового экстремума → закрыть всё.

**Стоп-лосс:** всегда стоит, 1.5–2.5×ATR от входа. Не переносится против позиции.

---

## 8. Псевдокод модуля

```python
def trendH_decision(symbol, tf_high="H4", tf_low="M15"):
    # 1. Данные
    df_h = load(symbol, tf_high)
    df_l = load(symbol, tf_low)

    # 2. Режим тренда
    trend = TrendCalculator(cfg).calculate(df_h["Close"].tolist())
    if trend in ("FLAT", "UNSTABLE"):
        return None

    # 3. Инвертированный HVH на старшем ТФ
    hvh = hvh_calc(df_h, ind_rules_inverted)
    last_sig = hvh.iloc[-1]
    if last_sig == 0:
        return None

    # 4. Согласованность тренда и HVH
    if trend == "DOWN" and last_sig != -1: return None
    if trend == "UP"   and last_sig !=  1: return None

    # 5. Инвентарь сеточника
    g = grid_state(symbol)
    if trend == "DOWN":
        if g.side != "LONG":  return None
    if trend == "UP":
        if g.side != "SHORT": return None
    if g.filled < 3 or g.vol_ratio < 0.6 or g.uPnL >= 0:
        return None

    # 6. Доп. фильтры
    if adx(df_h) < 22: return None
    if atr_ratio(df_h) < 1.1: return None
    if abs(ema_fast - ema_slow)/ema_slow < 0.005: return None

    # 7. Подтверждение на младшем ТФ
    if trend == "DOWN" and not bearish_confirm(df_l): return None
    if trend == "UP"   and not bullish_confirm(df_l): return None

    return "SHORT" if trend == "DOWN" else "LONG"
```

Выходы — отдельная функция `trendH_exit_manager(position, state)`, читающая те же сигналы + grid_state.

---

## 9. Рекомендованные параметры (стартовая точка)

| Параметр | Значение |
|---|---|
| TF HVH | H4 |
| HVH period | 60 |
| HVH dev | 1.8 |
| HVH mode | rolling |
| EMA fast / slow | 21 / 55 |
| confirmation_candles | 5 |
| require_rising | True |
| ADX min | 22 |
| ATR ratio min | 1.1 |
| Grid filled min | 3 |
| Grid vol_ratio min | 0.6 |
| Stop | 2.0 × ATR(H4) |
| Trailing | Chandelier 3 × ATR(H4) |
| TP ladder | 15 / 30 / 50 / trail |

---

## 10. Что это даёт

- **Не пробой**, а вход на откате — там, где импульс уже подтверждён, но не перегрет.
- **Сеточник становится сенсором**: он «сообщает», по какой стороне рынок давит.
- **FLAT отсекает боковик**, HVH отсекает ранние входы, ATR/ADX отсекают вялый тренд.
- **Лестница + трейлинг** позволяет досидеть до +50–100%, а не срезать на +5%.
- **Диспозиция закрывается автоматически** по разгрузке сетки.

Слабое место — вход всё равно опаздывает на 10–20% от начала импульса. Это лечится пирамидингом (пункт 6) и подтверждением на M15: ты входишь не в первые растянутые свечи, а в момент, когда отскок уже ломается обратно в сторону тренда.

Если хочешь, могу расписать конкретный `trendH_exit_manager` с приоритетами выходов (что важнее: сигнал HVH против позиции vs. разгрузка сетки) или подобрать параметры под конкретный таймфрейм/монету.


P\s: подумай как ее превратиь в чисто импульсную. Возможно будет как и для неккоторых из наших стратегий брать за основу количество сеток усредненных у Хрона и смотреть hvh подтверждение (но пробоя, не отскока) на младшем или среднем таймфрейме.

--- -->

<!-- ## 11. Успешная верификация архитектуры Hedge-Overlay (ADR / Case Study)

**Дата фиксации успеха:** 18–19 сентября 2026 г.  
**Контекст:** Сеточный бот `cron3Papper` подвергся сильным безоткатным импульсным движениям на ряде ультра-волатильных монет (`PIEVERSE`, `CATI`, `CHIP`, `AERO`, `GUSDT`). Сетка набирала усредняющие уровни против безоткатного тренда, аккумулируя нереализованную просадку (uPnL).

### 1. Подтверждение фундаментальной гипотезы
Гипотеза связки «Сетка + Трендовый хедж-оверлей»:
> *Когда рынок переходит из фазы распределения в фазу мощного безоткатного тренда, сеточник неизбежно испытывает просадку по своей встречной позиции. Трендовый бот TrendH, выступая как оверлей-сенсор, синхронизируется с инвентарем сетки, подхватывает импульс в направлении тренда и компенсирует просадку чистым положительным PnL.* -->

<!-- **Результат боевого тестирования (Paper Trading live):** Задумка полностью подтверждена на практике. Трендовые вселенные `u15` и `u15_cons` продемонстрировали выдающуюся результативность:

| Стратегия | Всего сделок | Gross PnL | WinRate | Роль в системе |
|---|---|---|---|---|
| **`u15` (Breakout LuxAlgo + Trend)** | 399 | **+8.01$** | **51.9%** | Абсолютный лидер трендового хеджирования |
| **`u15_cons` (Breakout Sniper)** | 408 | **+7.67$** | **50.7%** | Консервативный трендовый хедж с пониженным риском |
| **`u15_scalp` (Micro Breakout Scalp)** | 963 | **+2.38$** | **45.6%** | Высокочастотный импульсный подхват |

### 2. Детальный разбор по «стрессовым» монетам cron3

1. **PIEVERSEUSDT (Безоткатный взлет):**
   - **cron3:** Застрял в позиции `SHORT` (уровни 0 и 1 активны, суммарный объем 27.22% = $108.88, uPnL в минусе).
   - **TrendH (`u15` / `u15_cons`):** Безупречно вошли в **`LONG`** (по тренду, хеджируя `SHORT` сетки).
   - **Результат `u15`:** **3 сделки из 3 в плюс (WR 100%)**, чистый PnL **+1.94$**.
   - **Динамический сайз:** Позиция автоматически масштабировалась с $25.92 до $54.44 при активации 1-го уровня сетки.

2. **CATIUSDT (Трендовое ралли):**
   - **cron3:** Застрял в позиции `SHORT` (уровни 0 и 1 активны, суммарный объем 27.22% = $108.88).
   - **TrendH (`u15` / `u15_cons`):** Вошли в **`LONG`**.
   - **Результат `u15`:** **5 побед из 7 сделок (WR 71.43%)**, PnL **+1.74$**.

3. **CHIPUSDT (Мощная свеча пробоя):**
   - **cron3:** Застрял в позиции `SHORT` (уровень 0 активен, $51.84).
   - **TrendH (`u15_cons`):** В 23:59:27 подхватил импульс в **`LONG`** на свече +3.28% (объем $25.92, дельта +5.68% от цены входа сетки), зафиксировал профит **+0.79$**.

4. **AEROUSDT (Трендовый памп):**
   - **cron3:** Застрял в позиции `SHORT` (уровни 0 и 1 активны, объем 27.22% = $108.88).
   - **TrendH (`u15` / `u15_cons`):** Открыли **`LONG`** с динамическим объемом **$54.44**.
   - **Результат `u15`:** PnL **+0.87$**.

5. **GUSDT (Глубокий дамп -43%):**
   - **cron3:** Застрял в позиции `LONG` (уровни 0, 1 и 2 активны, суммарный объем 42.90% = $171.60).
   - **TrendH:** Открыл **`SHORT`** с динамическим хедж-объемом **$85.80** ($171.60 × 0.5), нейтрализуя просадку лонга.

### 3. Ключевые архитектурные выводы для дальнейшего развития
1. **Направления позиций согласованы на 100%:** TrendH безошибочно определяет противоположную сторону (`opp_info`), открывая лонг против шорта сетки и шорт против лонга сетки.
2. **Динамический сайзинг эволюционировал от фиксы `accum_usd * 0.5` к адаптивной карте уровней сетки:** 
   - Уровни 0–1 (малый объем сетки): `1.0` (100% хедж).
   - Уровни 2–3 (средний объем): `0.75` (75% хедж).
   - Уровни 4+ (тяжелая сетка): `0.50` (50% хедж, защита маржи).
3. **Реверсивные стратегии в импульсном рынке токсичны:** Попытки торговать контртренд (fade / mean reversion) на сильных трендовых монетах приводят к серийным стоп-лоссам (`u15_reverse_tight`: -23.23$, `u3_reverse_opt`: -20.94$). Из реверсивных стратегий выживают только строго согласованные со старшим трендом (`u3_reverse_trend`: +0.43$).
4. **Сужение воронки:** Фокус системы концентрируется вокруг импульсных трендовых вселенных `u15` / `u15_cons`, а также HVH пробоев волатильности (`u_sq_hvh_impulse`), с минимизацией контртрендовых модулей.

---

## 12. Адаптивная матрица коэффициента хеджирования (ADR-012: Dynamic Level-Based Hedge Map)

**Дата реализации:** 19 сентября 2026 г.  
**Контекст и предпосылка:**  
При фиксированном коэффициенте `hedge_ratio = 0.5` на начальных этапах развития тренда (когда сеточник набрал только 0-й базовый или 1-й усредняющий уровень) размер позиции TrendH составлял всего $25–$54. На таких монетах, как `PIEVERSE` (WR 75%), `CATI`, `CHIP` и `AERO`, это неоправданно занижало результирующий PnL при высокой статистической вероятности победы трендового пробоя.

**Архитектурное решение:**  
Фиксированный параметр `hedge_ratio` заменен на карту зависимости множителя от степени усредненности застрявшей сетки:
```json
"hedge_ratio": {
    "0": 1.0,
    "1": 1.0,
    "2": 0.75,
    "3": 0.75,
    "default": 0.5
}
```

**Математическое обоснование и эффект сайзинга:**
1. **Ранняя фаза тренда (Уровни 0–1, объем сетки ~$25–$50):**
   * Множитель **1.0 (100%)**.
   * TrendH заходит на полный объем зависшего ордера сетки ($51.84 против $51.84). При импульсном выносе трендовый бот удваивает прибыль по сравнению со старой фиксой 0.5.
2. **Развитая фаза тренда (Уровни 2–3, объем сетки ~$100–$170):**
   * Множитель **0.75 (75%)**.
   * Пример `GUSDT` / `CROSSUSDT`: размер хеджа увеличивается с $85.80 до **$128.70**, что в 1.5 раза ускоряет окупаемость плавающей просадки сетки закрытыми тейками TrendH.
3. **Экстремальная фаза (Уровни 4–5+, объем сетки $250–$400+):**
   * Множитель **0.50 (50%)**.
   * Бережет свободную маржу депозита, предотвращая оверлеверидж на супер-тяжелых зависаниях сетки.

**Реализовано в модулях:**
* `cron_integration.py`: добавлен универсальный резолвер `CronIntegration.resolve_hedge_ratio()`.
* `CORE/universe.py`: `StrategyUniverse.get_dynamic_hedge_ratio()` с автоматическим логированием `(hedge=75%)`.
* `cfg.json`: развернуто на глобальный уровень `default_hedge_ratio` и во все 27 торговых вселенных.
* `tests/test_grid_stress.py`: покрыто специализированным юнит-тестом `test_dynamic_hedge_ratio_levels`.

---

## 13. Замер скорости токсичного потока (Grid Fill Velocity), Breakeven Ratchet и ТОП-архетипы (ADR-013)

**Дата фиксации:** 19 сентября 2026 г.  
**Концептуальная цель:**  
Переход от статического анализа факта застревания сетки (`vol_ratio >= 0.40`) к динамическому анализу **скорости набора уровней** (Toxic Order Flow Velocity) и защите прибыли через Breakeven Ratchet:

1. **Регистрация таймштампов в `cron3Papper`:**
   - В `avg_manager.py` и `runtime_manager.py` фиксируется поле `activated_at` (epoch sec) для каждого уровня сетки.
   - Уровень 0 берет `state.open_time / 1000.0`.
   - Уровни 1..5 фиксируют точный момент триггера.
   - **Реконструкция без сброса:** Написан скрипт бэкфилла по `AvgManager.log`, позволяющий обойтись без принудительного сброса позиций и истории!

2. **Замер скорости стресса в `TrendH` (`cron_integration.py`):**
   - `fill_duration_sec = activated_at[max_lvl] - activated_at[0]`
   - `is_shock = (fill_duration_sec <= 900) and (max_lvl >= 2)` — признак скоростного каскадного выноса.

3. **Защита прибыли: Breakeven Ratchet (`ExitBreakevenRatchetRule`):**
   - Если максимальный плавающий профит позиции достигал `+2.5%`, стоп-лосс безусловно подтягивается на уровень `entry_price + fees` (+0.2%), предотвращая потерю прибыли при резких сквизах назад.

4. **Динамический Time Stop (`ExitTimeStopRule`):**
   - Если за 15–20 минут сделка не развилась хотя бы до `+0.5%` (затухание импульса в айсбергах), бот выходит по рынку. Если сделка в сильном плюсе, она продолжает работать.

5. **3 целевых архетипа стратегий (First-Trigger Mutex) + u15_ratchet:**
   - `u_sq_hvh_ratchet`: вход первым из сжатия волатильности (Carter Squeeze + HVH).
   - `u15_cons_ratchet`: вход вторым при институциональном пробое уровней (Taker > 65%).
   - `u_grid_stress_shock`: вход при скоростном стрессе сетки (Shock Momentum Overlay).
   - `u15_ratchet`: флагманский пробой уровней LuxAlgo на базе абсолютного лидера U15 (WR 47% на 625 сделках) с Breakeven Ratchet (+2.5%).

6. **Синхронизация шаблона `_base.json` и перенос в боевой бот (`cron3`):**
   - Механизм `activated_at` и `timestamp` перенесен в боевой бот `C:\Users\user\Desktop\My_Pro\HP_EliteBook_735_old\MY\HRON_3\cron3`.
   - В обоих ботах исправлен базовый шаблон `CFG/_base.json` и `runtime_builder.py` (добавлены дефолтные `activated_at: null`, `timestamp: null`).
   - В `CORE/bot.py` внедрена немедленная фиксация времени уровня 0 при входе в сделку (`grid["0"]["activated_at"] = time.time()`), исключающая открытие новых сделок по старым шаблонам без таймштампов.
   - Все 74 рантайм-файла `cron3Papper` синхронизированы без остановки и сброса ботов.

---

## 14. Ликвидация высокочастотного спама (Churn Elimination) и фиксация U15 как Proven Leader (ADR-014)

**Дата фиксации:** 19 сентября 2026 г.  
**Концептуальная цель:**  
Устранение «токсичных пылесосов комиссий» (стратегий, генерирующих тысячи микросделок с нулевым или отрицательным математическим ожиданием из-за биржевых комиссий и проскальзываний) и фиксация устойчивых лидеров:

1. **Анализ и вырезание Churn-стратегий:**
   * **`u15_scalp` (Micro Breakout Scalp):** Зафиксировано **1871 сделка** с винрейтом 42%, огромной просадкой **-$108.53** и мизерным нетто-профитом +2.58$. Сверхкороткий тайм-стоп (10 мин) и жесткий TP 1.5% приводили к постоянному запилу на биржевых комиссиях.
   * **`u15_reverse_fade` (Pure Liquidity Fade):** Зафиксировано **807 сделок** с просадкой **-$43.32** и скромным профитом +0.55$. Торговля без трендового фильтра HTF в условиях импульсного рынка генерировала избыточный шум.
   * **Решение:** Обе стратегии полностью удалены из `cfg.json`. Число вселенных снижено с 31 до 29 (активных с 22 до 20).

2. **Фиксация U15 в качестве Proven Leader 🥇:**
   * Стратегия `u15` (Breakout LuxAlgo + Taker Flow) показала наивысшую устойчивость: **+5.39$ Net PnL**, 636 сделок, винрейт **47.1%**, просадка -$35.99.
   * В `TG/strategy_guide.py` стратегия официально назначена **Proven Leader #1** вместо выбывшей `u15_reverse_fade`.
   * Стратегия `u3_reverse_trend` осталась **Proven Leader #2** (Net PnL: +3.20$, WR: 37%, DD: -$7.84).

3. **Изоляция синтетических логов тестов (`N/A`):**
   * В `cron_integration.py` (`EntryGridStressRule.check`) логирование `[GRID STRESS MATCH]` обёрнуто в условие `if symbol and symbol != "N/A":`.
   * Это предотвращает засорение `logs/all.log` фиктивными событиями `[N/A][LONG] cur_price=0.0000` при фоновом прогоне юнит-тестов с мок-индикаторами.

4. **Точная построчная ротация логов (5k строк) и индексация архивов (all.1.log):**
   * Устранена ошибка логгера `c_log.py`, где лимит строк умножался на 5 (`maxBytes * 5`), а средний размер строки брался по умолчанию 300 байт вместо 170 байт из `all.log`, из-за чего файл разрастался до 25k–45k строк без ротации.
   * `maxBytes` теперь рассчитывается строго от целевого `max_log_lines` (5000 строк = ~850 КБ).
   * В `UnlockedRotatingFileHandler` переопределена ротация с удобным форматом `all.1.log`, `all.2.log` (с расширением `.log` для редакторов) и безопасным фоллбэком на Windows (copy + truncate при открытом файле в редакторе).
   * Добавлен параметр `backup_count: 5` в `cfg.json` и `consts.py`. Накопленные 22k строк автоматически отсечены в архив `all.1.log`, а рабочий `all.log` обновлен с чистого листа.

--- -->

<!-- ## 15. Проводы семейства U15 (Decommission of Blind Breakouts) и эволюция Дельта-Хеджеров (ADR-015)

**Дата фиксации:** 20 сентября 2026 г.  
**Концептуальная цель:**  
Окончательный вывод из боевой эксплуатации семейства «слепых» пробойных стратегий U15, фиксация ключевого квантового урока и запуск нового поколения дельта-хеджеров и симбиозов:

1. **Трибьют и постмортем семейства U15:**
   * **Боевой путь:** Стратегии семейства (`u15`, `u15_cons`, `u15_aggr`, `u15_cons_ratchet`, `u15_ratchet`) честно прошли через тысячи рыночных ситуаций (суммарно **>5 000 сделок**).
   * **Статистический вердикт:** На большой выборке все вариации показали отрицательное математическое ожидание:
     * `u15`: -97.20$ (1644 сделки, WR 44%, DD -357.13$)
     * `u15_cons`: -86.41$ (1762 сделки, WR 44%, DD -369.61$)
     * `u15_cons_ratchet`: -93.82$ (876 сделки, WR 43%, DD -286.94$)
     * `u15_ratchet`: -96.17$ (877 сделки, WR 43%, DD -290.19$)
     * `u15_aggr`: -22.87$ (300 сделки, WR 36%, DD -74.44$)
     * **Суммарный убыток семейства: -$396.47$**.
   * **Фундаментальный вывод:** Торговля пробоев уровней поддержки/сопротивления и Taker Buy Flow на таймфрейме 5m **вслепую** (без понимания, где застряла реальная рыночная ликвидность) неизбежно ведет к потерям из-за биржевых комиссий, проскальзываний и ложных пилообразных заколов.
   * **Дань уважения солдатам U15:** Данное семейство выполнило ключевую историческую миссию — на нем были отточены модули `taker_flow`, `sr_levels`, `chandelier_exit` и динамический `breakeven_ratchet`. Код правил сохранен в `CORE/indicators/` для будущих HTF-исследований, но все 5 вселенных U15 переведены в `"is_active": false`.

2. **Эволюция дельта-хеджирования и новые симбиозы:**
   * **`u_shadow_harvester_40` / `50`:** Оцифровка нереализованной прибыли `u_grid_shadow` (где плавающий плюс достигал +68$) через внедрение динамического трейлинга `ExitBreakevenRatchetRule` (2.5% $\to$ BE, 1.8% trail) со стопом 3.8%.
   * **`u_delta_sniper_15m`:** Перевод индикатора HVH на таймфрейм 15m (`period=20`, `dev=1.6`) для масштабирования успешного 100% WR дебюта снайпера на более частые институциональные импульсы.
   * **`u_hvh_delta_symbiosis`:** Симбиоз лидера №1 (`u_hvh_pullback`, +10.93$) и лидера №2 (`u_delta_harvester`, +16.30$) — вход на перерастяжке 15m HVH по тренду 1H с последующим динамическим трейлингом прибыли и выходом по TP сетки. -->

<!-- ---

## 16. Институциональная селекция по PortfolioMode, доказательство обратной корреляции и запуск линии Jem (ADR-016)

**Дата фиксации:** 21 сентября 2026 г.  
**Концептуальная цель:**  
Перевод разработки в фазу масштабной институциональной селекции по 4 направлениям `PortfolioMode`. Отказ от спешки с выводом трендового бота на боевой депозит до завершения песочницы. Реализация фильтрации по статистике сеточника, возвращение `u15` на 4H таймфрейме и запуск авторской линейки `Jem`.

1. **Математическое доказательство обратной корреляции сеточника и импульсника ($r = -0.214$):**
   * **Группа 1 (Кэш-коровы сетки, `Grid Net > 0`):** `PIEVERSE` (+36.59$), `PLAY` (+15.22$), `MEGA` (+12.86$), `JUP` (+5.67$), `SOLV` (+5.19$). Все 5 монет принесли трендовику **-$76.72$ чистого убытка (100% слив)**. Причина: сеточник процветает во флэте, где импульсник ловит постоянные ложные пробои и запил на комиссиях.
   * **Группа 2 (Лидеры трендового импульса — Alpha Momentum, `Grid Net <= 0`):** `GUSDT` (-8.95$), `FF` (-25.06$), `1000PEPE` (-22.72$), `ENA` (-21.49$), `PENGU` (-8.32$). Сгенерировали трендовику **+$19.32$ чистого профита**. Безоткатный тренд, в котором сетка застревает, является главным источником заработка импульсника.

2. **Архитектурный модуль симбиоза (`CORE/symbiosis_rules.py`):**
   * **`EntryGridNetFilterRule`:** 
     * Режим `ALPHA_ONLY`: допуск сделок ТОЛЬКО если `cron3_net_pnl <= 0.0` (монета в фазе сильного выноса Alpha Momentum).
     * Режим `EXCLUDE_TOP_CASH_COWS`: жесткий бан топ-10 кэш-коров сетки.
   * **`EntryHTFRSIRule`:** институциональный фильтр экстремумов старшего таймфрейма (Daily/4H RSI). Для LONG запрещает покупки при $RSI \ge 70$, для SHORT — продажи при $RSI \le 30$.
   * **`CronAnalyticsCache`:** потокобезопасный кэш аналитики сеточника с TTL 15 сек.

3. **8 новых фильтрованных версий жнецов:**
   * `u_sh50_alpha` & `u_sh50_notop` (Shadow Harvester 50% с фильтрами сетки).
   * `u_sh40_alpha` & `u_sh40_notop` (Shadow Harvester 40% с фильтрами сетки).
   * `u_hvh_symbiosis_alpha` & `u_hvh_symbiosis_notop` (HVH Delta Symbiosis с фильтрами сетки).
   * `u_symb_harv_alpha` & `u_symb_harv_notop` (Symbiosis Harvester + Stagnation Exit с фильтрами сетки).

4. **Возвращение `u15` на институциональный уровень (4H LuxAlgo + 1D RSI):**
   * `u15_4h_rsi1d_std`: пробой уровней LuxAlgo на 4H таймфрейме с фильтром $RSI_{1D} \in [30, 70]$ и сайзингом сетки.
   * `u15_4h_rsi1d_alpha`: институциональный пробой на 4H с фильтром Alpha Momentum (`Grid Net <= 0`).

5. **Авторская линейка стратегий `Jem`:**
   * **`u_jem_matrix_harvest` (Institutional 3-Tier):** синхронизация 3 уровней реальности (4H тренд + 1D RSI + стресс сетки 40% на Alpha монетах + 15m HVH) с выходом по Stagnation Lock (+0.3% БУ при +2.8%, выход при застое > +5% за 30 мин).
   * **`u_jem_symbiotic_quantum` (Trend-First Engine):** нацелен на режим `FOR_TRENDH_FIRSTABLE`. Активируется только при перекосе сетки $\ge 50\%$ на монетах с отрицательным Net PnL сетки, сопровождает вынос до полного исчерпания тренда с Breakeven Ratchet (+2.5%) и снятием при разгрузке сетки.

6. **Статус развертывания:**
   * Всего в `cfg.json`: 54 вселенные (40 активных).
   * Все новые стратегии запущены на параллельный сбор реальной рыночной статистики.

---

### 17. ADR-017: Устранение артефакта фантомных просадок (800$ Ghost Peak Bug) и запуск Prime-модификаций (Wide Prime & Stagnation Prime)

1. **Диагностика и первопричина бага фантомных просадок:**
   * При миграции стартового баланса с `1000$` на `200$` в кэше аналитики (`peak_balance_usdt`) остался старый пик `1030.48$`, рассчитанный от базы `1000$`.
   * Формула `peak - live_equity` дала искусственную просадку в `-$806.11$` на счетах с реальной депозитной просадкой всего `-$35..-$45$` (17–22%).
   * Кроме того, в `ANALYTICS/metrics.py` была найдена утечка: при отсутствии индивидуального файла `trades_ledger_{uid}.txt` происходил непреднамеренный фоллбэк на глобальный портфельный `trades_ledger.txt` (где аккумулировались балансы до `4000$`), что отравляло пики отдельных вселенных.

2. **Архитектурная защита от повторения проблемы:**
   * В [CORE/universe.py](file:///c:/Users/user/Desktop/My_Pro/HP_EliteBook_735_old/MY/TREND_H/TrendH_Papper/CORE/universe.py#L225-L245) и [ANALYTICS/metrics.py](file:///c:/Users/user/Desktop/My_Pro/HP_EliteBook_735_old/MY/TREND_H/TrendH_Papper/ANALYTICS/metrics.py#L70-L95) внедрена автоматическая нормализация: при обнаружении смены стартового баланса или аномального пика (`peak >= 800$` при базе `<= 300$`), пиковый баланс автоматически приводится к масштабу депозита, а максимальная просадка очищается от фантомного зазора.
   * Фоллбэк на глобальный `trades_ledger.txt` строго ограничен системными запросами общего портфеля (`uid in ('', 'default', 'all')`).
   * В [TG/handlers_analytics.py](file:///c:/Users/user/Desktop/My_Pro/HP_EliteBook_735_old/MY/TREND_H/TrendH_Papper/TG/handlers_analytics.py#L88) дефолтный стартовый баланс обновлен до актуальных `200.0 USDT`.

3. **Калибровка аналитики всех вселенных:**
   * Все файлы в `logs/analytics/` откалиброваны скриптом `scratch/calibrate_all_analytics.py`.
   * `u_shadow_harvester_wide`: Peak `230.48$`, Max DD скорректирован с `816.88$` до **`76.43$`**.
   * `u_grid_shadow_stagnation`: Peak `227.00$`, Max DD скорректирован с `804.50$` до **`62.27$`**.
   * `u_grid_stress_base`: Peak `235.12$`, Max DD скорректирован с `853.83$` до **`182.91$`**.

4. **Запуск институциональных Prime-модификаций (с сохранением оригиналов):**
   * **`u_sh_wide_prime` (Shadow Harvester Wide Prime)**: фильтр `ALPHA_ONLY` (`Grid Net <= 0`), ранняя защита в БУ (+0.5% при +3.0%), умеренно-широкий трейл (+5.5% / 2.5% trail) и SL 3.5%.
   * **`u_grid_shadow_stag_prime` (Pure Grid Shadow Stagnation Prime)**: фильтр `ALPHA_ONLY` (`Grid Net <= 0`), БУ-замок (+0.3% при +2.8%), чувствительный датчик стагнации (+2.8% и 20 мин без прогресса) и SL 3.5%.
   * Всего в системе: 54 вселенные (40 активных).
 -->
