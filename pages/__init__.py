import importlib
def _import(mod): return importlib.import_module(f'pages.{mod}').show
show_dashboard = _import('01_dashboard')
show_strategies = _import('02_strategies')
show_backtest = _import('03_backtest')
show_signals = _import('04_signals')
show_custom = _import('05_custom')
show_manual = _import('06_manual')
