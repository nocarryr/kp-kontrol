import threading
import asyncio
import weakref
from functools import partial, wraps, update_wrapper

from kivy.clock import Clock, mainthread

WRAPPER_ASSIGNMENTS = ('__module__', '__name__', '__qualname__', '__doc__',
    '__annotations__', '__self__', '__func__')
def foo_wrapped_callback(f, loop, obj=None):
    # Used by AioBridge.bind_events() to wrap a main thread callback
    # to be called by kivy.clock.Clock. Attributes are reassigned to make the
    # wrapped callback 'look' like the original (f.__func__ and f.__self__)
    # So the weakref storage in pydispatch still functions properly (in theory)
    # class wrapped_(object):
    #     def __init__(self, f_, loop_):
    #         self.f = f_
    #         self.loop = loop_
    #     def __call__(self, *args, **kwargs):
    #         print('im in yer loop: ', self.loop)
    #         Clock.schedule_once(partial(self.f, *args, **kwargs), 0)
    #         #self.loop.call_soon_threadsafe(partial(self.f, *args, **kwargs))
    #     def __get__(self, obj, objtype):
    #         return types.MethodType(self.__call__, obj, objtype)
    def wrapped_(f_, loop_):
        @wraps(f_, assigned=WRAPPER_ASSIGNMENTS)
        def inner(*args, **kwargs):
            print('im in yer loop: ', loop_, id(loop_))
            if isinstance(f_, types.MethodType):
                self = args[0]
                args = args[1:]
            Clock.schedule_once(partial(f_, *args, **kwargs), 0)
        print(inner)
        return inner
    #return update_wrapper(wrapped_(f), f, assigned=WRAPPER_ASSIGNMENTS)
    #return update_wrapper(wrapped_(f, loop), f, assigned=WRAPPER_ASSIGNMENTS)
    return wrapped_(f, loop)

def wrapped_callback(f):
    @mainthread
    def cb(*args, **kwargs):
        # #_loop = asyncio.get_event_loop()
        # t = threading.current_thread()
        # #mt = threading.main_thread()
        # print('im in yer loop: ', t)
        f(*args, **kwargs)
    return cb

# class WeakPair(object):
#     def __init__(self, obj, cb, del_callback):
#         self.obj_ref = weakref.ref(obj, self.on_wr_removed)
#         if isinstance(cb, types.MethodType):
#             cb = cb.__self__
#         self.cb_ref = weakref.ref(cb, self.on_wr_removed)
#         self.del_callback = del_callback
#         self.key = (id(obj), id(cb))
#     def on_wr_removed(self, *args):
#         self.del_callback(self)

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
        # the main thread using kivy.clock.Clock
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
