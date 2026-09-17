from pathlib import Path
import sys
import threading
import webbrowser
from osi.visual import InterfaceLocal


def diretorio_aplicacao():
    if getattr(sys, 'frozen', False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def main():
    app = InterfaceLocal(diretorio_aplicacao() / 'topologia.json')
    def abrir_navegador():
        abriu = webbrowser.open(app.url)
        if not abriu and sys.platform == 'win32':
            import ctypes
            ctypes.windll.user32.MessageBoxW(0,
                'Abra este endereço no navegador: ' + app.url,
                'Simulador OSI - endereço local', 0x40)
    threading.Timer(0.3, abrir_navegador).start()
    if sys.stdout:
        print('Simulador OSI:', app.url, flush=True)
        print('Use Encerrar no programa para fechar o servidor local.', flush=True)
    try:
        app.executar()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except Exception as exc:
        if sys.platform == 'win32':
            import ctypes
            ctypes.windll.user32.MessageBoxW(0, str(exc), 'Simulador OSI - erro ao abrir', 0x10)
        else:
            raise
