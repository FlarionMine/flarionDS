"""
Лёгкий shim-модуль audioop для Python 3.13 на Railway.

discord.py импортирует стандартный модуль audioop для работы с голосовыми
функциями. В Python 3.13 его больше нет, но для нашего бота голос не нужен,
поэтому достаточно заглушки, чтобы импорт не падал.

Все функции ниже — no-op и добавлены только для совместимости. Если когда-либо
будешь использовать голос, лучше перейти на библиотеку, официально
поддерживающую Python 3.13, или запустить бота на Python 3.11.
"""

def _not_implemented(*args, **kwargs):  # pragma: no cover
    raise NotImplementedError("audioop shim: функция не реализована, голос не поддерживается")


# Определяем минимальный набор имён, который может ожидать discord.py.
lin2lin = _not_implemented
mul = _not_implemented
add = _not_implemented
max = _not_implemented
