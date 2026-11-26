"""Bounded TCP relay to one fixed synthetic recovery API; no URL-based proxying."""
import select
import socket
import socketserver
import threading

BACKEND=('recovered-api',8000)


def make_server(address,backend=BACKEND):
    slots=threading.BoundedSemaphore(32)
    class Handler(socketserver.BaseRequestHandler):
        def handle(self):
            try:
                self.request.settimeout(5)
                with socket.create_connection(backend,timeout=3) as upstream:
                    upstream.settimeout(5)
                    peers={self.request:upstream,upstream:self.request}
                    while True:
                        readable,_,_=select.select(list(peers),[],[],30)
                        if not readable:return
                        for source in readable:
                            data=source.recv(65536)
                            if not data:return
                            peers[source].sendall(data)
            except (OSError,ValueError):return
    class Server(socketserver.ThreadingTCPServer):
        allow_reuse_address=True
        daemon_threads=True
        def process_request(self,request,client_address):
            if not slots.acquire(blocking=False):
                self.shutdown_request(request);return
            try:super().process_request(request,client_address)
            except BaseException:slots.release();raise
        def process_request_thread(self,request,client_address):
            try:super().process_request_thread(request,client_address)
            finally:slots.release()
        def handle_error(self,request,client_address):pass
    return Server(address,Handler)


if __name__=='__main__':
    # The running service has no configurable upstream or client-selected host.
    with make_server(('0.0.0.0',8000)) as server:server.serve_forever()
