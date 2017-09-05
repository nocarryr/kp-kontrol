import threading
import asyncio
import weakref

from kivy.clock import mainthread

def wrapped_callback(f):
    @mainthread
    def cb(*args, **kwargs):
        f(*args, **kwargs)
    return cb

class AioBridge(threading.Thread):
    def __init__(self, app):
        super().__init__()
        self.app = app
        self.event_loop = None
        self.daemon = True
        self.running = False
        self.thread_run_event = threading.Event()
        self.thread_stop_event = threading.Event()
        self.wrappers = weakref.WeakKeyDictionary()
    def run(self):
        loop = self.event_loop
        if loop is None:
            loop = self.event_loop = asyncio.new_event_loop()
            loop.set_debug(True)
            asyncio.set_event_loop(loop)
        self.aio_stop_event = asyncio.Event()
        self.running = True
        loop.run_until_complete(self.aioloop())
        self.thread_stop_event.set()
    def stop(self):
        self.running = False
        self.event_loop.call_soon_threadsafe(self.aio_stop_event.set)
    async def aioloop(self):
        await self.aiostartup()
        self.thread_run_event.set()
        await self.aio_stop_event.wait()
        await self.aioshutdown()
    async def aiostartup(self):
        self.app.async_server_loop = self.event_loop

    async def aioshutdown(self):
        pass
    def bind_events(self, obj, **kwargs):
        # Override pydispatch.Dispatcher.bind() using wrapped_callback
        # Events should then be dispatched from the thread's event loop to
        # the main thread using the kivy.clock.mainthread decorator
        async def do_bind(obj_, **kwargs_):
            obj_.bind(**kwargs_)
        kwargs_ = {}
        for name, callback in kwargs.items():
            w = wrapped_callback(callback)
            kwargs_[name] = w
            if obj not in self.wrappers:
                self.wrappers[obj] = set()
            self.wrappers[obj].add(w)
        asyncio.run_coroutine_threadsafe(do_bind(obj, **kwargs_), loop=self.event_loop)
    def run_async_coro(self, coro):
        return asyncio.run_coroutine_threadsafe(coro, loop=self.event_loop)
