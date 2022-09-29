from time import sleep
from json import JSONDecoder, JSONEncoder
from queue import Queue

import zmq

from drone import DJIDrone
from zmq_threads import TCPThread
from logger import Log
import configure as config
config_manager = config.ConfigManager()


class CommandReceiver(TCPThread):
	def __init__(self, zmq_context, message_callback, port, rate=10/1000):
		super().__init__(zmq_context, zmq.REP, "127.0.0.1", port, rate=rate)

		self._message_callback = message_callback
		self._request_queue = Queue()
		self._reply_queue = Queue()
		self._json_decoder = JSONDecoder()
		self._json_encoder = JSONEncoder()

	def _thread_action(self):
		self._request_queue.put(self._socket.recv_string())
		self._socket.send_string(self._reply_queue.get())
		super()._thread_action()

	def update(self):
		while not self._request_queue.empty():
			msg = self._json_decoder.decode(self._request_queue.get())
			success, return_kwargs = self._message_callback(msg["request"], msg["args"])
			response = {"success": success}
			if return_kwargs is not None:
				response["args"] = return_kwargs
			self._reply_queue.put(self._json_encoder.encode(response))


class AutoCopilot:
	def __init__(self):
		self.zmq_context = zmq.Context()
		self.drone = DJIDrone(self.zmq_context, rate=1 / config.UPDATE_HZ)
		self.cmd_receiver = CommandReceiver(self.zmq_context, self.process_request, port=5536, rate=1 / config.UPDATE_HZ)

	def update(self):
		self.drone.update()
		if self.cmd_receiver.is_alive():
			self.cmd_receiver.update()
		sleep(1 / config.UPDATE_HZ)

	def process_request(self, request, arguments):
		Log.add("Received request: " + request)

		try:
			success, return_kwargs = self.run_command(request, arguments)
		except TypeError:
			return_kwargs = {"error": "Unexpected error occurred while executing the command."}
			success = False

		return success, return_kwargs

	def run_command(self, request, arguments):
		# --- PING
		if request == "ping":
			return True, None


if __name__ == "__main__":
	acp = AutoCopilot()
	while True:
		acp.update()
