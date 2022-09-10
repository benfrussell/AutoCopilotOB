import zmq
import threading
import os.path
import time
from traceback import format_exception
from queue import Queue
from datetime import datetime
from logger import Log

from utility import activate_feed, UnexpectedStateError


class IPCThread(threading.Thread):
	def __init__(self, zmq_context, zmq_type, feed_name, auto_feed_activation=False, rate=10/1000):
		super().__init__()
		self.rate = rate
		self.exception = None
		self.exception_raised = False
		# Tracks whether the thread was ever started, as opposed to is_alive which only tracks if it's currently running
		self.started = False
		self.initialized = False

		self._zmq_context = zmq_context
		self._zmq_type = zmq_type
		self._event = threading.Event()
		self._feed_name = feed_name
		self._auto_feed_activation = auto_feed_activation
		self._socket = None

		self.setDaemon(True)

	def _thread_init(self):
		if self._auto_feed_activation:
			activate_feed(self._feed_name)

		self._socket = self._zmq_context.socket(self._zmq_type)
		if self._zmq_type in (zmq.PUB, zmq.REP):
			self._socket.bind("ipc:///tmp/feeds/{}.ipc".format(self._feed_name))
		else:
			self._socket.connect("ipc:///tmp/feeds/{}.ipc".format(self._feed_name))

	def _thread_action(self):
		pass

	def _thread_complete(self):
		pass

	def start(self):
		if self.started is True:
			raise UnexpectedStateError("Tried to start a thread that had already been started before.")
		else:
			self.started = True
		super().start()

	def run(self):
		self._thread_init()
		self.initialized = True
		while not self._event.is_set():
			self._thread_action()
			self._event.wait(self.rate)

		self._thread_complete()

	def stop(self):
		self._event.set()

	def update(self):
		while not self._subscriber_queue.empty():
			msg = self._subscriber_queue.get()
			self._message_callback(str(msg[0], "utf-8"), msg[1])


class IPCRequestThread(IPCThread):
	def __init__(self, zmq_context, message_callback, feed_name, auto_feed_activation=False, rate=10/1000):
		super().__init__(zmq_context, zmq.REQ, feed_name, auto_feed_activation, rate)

		self._request_state_lock = threading.Lock()
		self._request_in_progress = False
		self._message_callback = message_callback
		self._request_queue = Queue()
		self._reply_queue = Queue()
		self._request_time = None
		self.last_reply_time = 0
		self._update_thread = None

	def _thread_init(self):
		super()._thread_init()

	def _thread_action(self):
		while not self._request_queue.empty():
			with self._request_state_lock:
				if self._request_in_progress:
					continue
				self._request_in_progress = True

			self._socket.send_string(self._request_queue.get())
			self._reply_queue.put(self._socket.recv())
		super()._thread_action()

	def _thread_complete(self):
		super()._thread_complete()

	def send_request(self, request):
		with self._request_state_lock:
			self._request_time = time.time()
		self._request_queue.put(request)

	def update(self):
		while True:
			while not self._reply_queue.empty():
				with self._request_state_lock:
					self._request_in_progress = False

				self._message_callback(str(self._reply_queue.get(), "utf-8"))

				with self._request_state_lock:
					self.last_reply_time = time.time() - self._request_time
			time.sleep(self.rate)

	def start_update_async(self):
		if self._update_thread is None or not self._update_thread.is_alive():
			self._update_thread = threading.Thread(target=self.update)
			self._update_thread.setDaemon(True)
			self._update_thread.start()

	@property
	def updating_async(self):
		return False if self._update_thread is None else self._update_thread.is_alive()

	@property
	def waiting_on_reply(self):
		with self._request_state_lock:
			return self._request_in_progress
	
	def get_reply_time(self):
		with self._request_state_lock:
			if self._request_in_progress:
				return time.time() - self._request_time
			return 0