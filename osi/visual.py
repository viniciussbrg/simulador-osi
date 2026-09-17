from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Lock, Thread
import json
import secrets
import sys
from urllib.parse import urlsplit
from .rede import Topologia
from .simulador import Simulador


class InterfaceLocal:
    def __init__(self, caminho_topologia, assets=None):
        self.caminho = Path(caminho_topologia)
        self.assets = Path(assets) if assets else (
            Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parent.parent)) / 'interface')
        self.token = secrets.token_urlsafe(24)
        self.lock = Lock()
        self.topologia = None
        self.erro_topologia = ''
        self.carregar()
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), self._handler())
        self.server.daemon_threads = True

    @property
    def url(self):
        return f'http://127.0.0.1:{self.server.server_port}/'

    def carregar(self, dados=None):
        try:
            topologia = Topologia(self.caminho, dados=dados)
        except (OSError, ValueError) as exc:
            self.erro_topologia = str(exc)
            if dados is not None:
                raise
        else:
            self.topologia = topologia
            self.erro_topologia = ''

    def estado(self):
        topo = self.topologia.modelo_visual() if self.topologia else None
        return {'topologia': topo, 'erro': self.erro_topologia,
                'casos': Simulador.CASOS, 'token': self.token,
                'cenarios': self.topologia.dados.get('cenarios', {}) if topo else {}}

    def _handler(self):
        app = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def responder(self, status, data, content_type='application/json; charset=utf-8'):
                if isinstance(data, dict):
                    data = json.dumps(data, ensure_ascii=False).encode('utf-8')
                self.send_response(status)
                self.send_header('Content-Type', content_type)
                self.send_header('Content-Length', str(len(data)))
                self.send_header('Cache-Control', 'no-store')
                self.send_header('X-Content-Type-Options', 'nosniff')
                self.send_header('Content-Security-Policy',
                    "default-src 'self'; style-src 'self'; script-src 'self'; img-src 'self' blob:; object-src 'none'; frame-ancestors 'none'")
                self.end_headers()
                self.wfile.write(data)

            def do_GET(self):
                if self.headers.get('Host') != f'127.0.0.1:{app.server.server_port}':
                    self.responder(403, {'erro': 'Acesso permitido somente pelo endereço local.'})
                    return
                path = urlsplit(self.path).path
                if path == '/api/estado':
                    with app.lock:
                        self.responder(200, app.estado())
                else:
                    arquivos = {'/': ('index.html', 'text/html; charset=utf-8'),
                                '/app.js': ('app.js', 'text/javascript; charset=utf-8'),
                                '/styles.css': ('styles.css', 'text/css; charset=utf-8')}
                    if path not in arquivos:
                        self.responder(404, {'erro': 'Recurso não encontrado.'})
                        return
                    nome, mime = arquivos[path]
                    try:
                        self.responder(200, (app.assets / nome).read_bytes(), mime)
                    except OSError:
                        self.responder(500, {'erro': 'Arquivos da interface ausentes. Refaça o build.'})

            def do_POST(self):
                if self.headers.get('Origin') != app.url.rstrip('/') or self.headers.get('X-OSI-Token') != app.token:
                    self.responder(403, {'erro': 'Origem ou token inválido.'})
                    return
                try:
                    length = int(self.headers.get('Content-Length', '0'))
                    if not 0 < length <= 300000:
                        raise ValueError('Requisição ausente ou muito grande.')
                    data = json.loads(self.rfile.read(length))
                    with app.lock:
                        if self.path == '/api/topologia':
                            if data.get('dados') is None:
                                raise ValueError('Selecione um arquivo JSON válido.')
                            app.carregar(data['dados'])
                            response = app.estado()
                        elif self.path == '/api/recarregar':
                            app.carregar()
                            if app.erro_topologia:
                                raise ValueError(app.erro_topologia)
                            response = app.estado()
                        elif self.path == '/api/configuracao':
                            if app.topologia is None:
                                raise ValueError('Carregue uma topologia válida.')
                            response = Simulador(app.topologia).configuracao(data['caso'])
                        elif self.path == '/api/simular':
                            if app.topologia is None:
                                raise ValueError('Carregue uma topologia válida.')
                            response = Simulador(app.topologia).simular(data['caso'], data.get('configuracao')).to_dict()
                        elif self.path == '/api/encerrar':
                            response = {'ok': True}
                            Thread(target=app.server.shutdown, daemon=True).start()
                        else:
                            self.responder(404, {'erro': 'Comando inexistente.'})
                            return
                    self.responder(200, response)
                except (ValueError, OSError, KeyError, TypeError) as exc:
                    self.responder(400, {'erro': str(exc)})
                except Exception:
                    self.responder(500, {'erro': 'Erro interno. Recarregue a topologia e repita a simulação.'})

        return Handler

    def executar(self):
        try:
            self.server.serve_forever(poll_interval=0.2)
        finally:
            self.server.server_close()
