import time
import os
from enum import Enum
from json import JSONDecoder
from abc import ABC, abstractmethod
from threading import Lock

import configure as config
from zmq_threads import IPCRequestThread
from utility import activate_feed, open_process_detached, kill_process, process_count
from logger import Log


class InterfaceState(str, Enum):
	OFFLINE = "OFFLINE"
	ATTEMPTING = "ATTEMPTING"
	ONLINE = "ONLINE"


class InterfaceFailState(str, Enum):
	NO_FAILURE = "NO_FAILURE"
	ATTEMPT_FAILURE = "ATTEMPT_FAILURE"
	THREAD_TIMEOUT = "THREAD_TIMEOUT"


class FlightState(str, Enum):
	STOPPED = "STOPPED"
	ON_GROUND = "ON_GROUND"
	IN_AIR = "IN_AIR"


class DJIMessageTopic(str, Enum):
	InterfaceStatus = "InterfaceStatus"
	FlightStatus = "FlightStatus"
	ControlDevice = "ControlDevice"
	Telemetry = "Telemetry"


class DJIInterfaceThread(IPCRequestThread):
	def __init__(self, zmq_context, message_callback, rate=10/1000):
		super().__init__(zmq_context, message_callback, "drone", auto_feed_activation=False, rate=rate)

		self._status = InterfaceState.OFFLINE
		self._status_is_set = False
		self._status_lock = Lock()
		self._current_request = None
		self._fail_state = None
		self._fail_output = None
		self._json_decoder = JSONDecoder()

	@property
	def status(self):
		with self._status_lock:
			return self._status

	@property
	def status_is_set(self):
		with self._status_lock:
			return self._status_is_set

	@property
	def current_request(self):
		with self._request_state_lock:
			return self._current_request

	@property
	def request_in_progress(self):
		with self._request_state_lock:
			return self._request_in_progress

	@property
	def fail_state(self):
		with self._status_lock:
			return self._fail_state

	@property
	def fail_output(self):
		with self._status_lock:
			return self._fail_output

	@staticmethod
	def is_process_running():
		return process_count("dji-interface") > 0

	def start(self):
		super().start()

	def update(self):
		while True:
			if not self._reply_queue.empty():
				with self._request_state_lock:
					self._request_in_progress = False

				reply = self._reply_queue.get()
				self._process_reply(reply)

				with self._request_state_lock:
					self.last_reply_time = time.time() - self._request_time
			else:
				self._check_for_errors()
			time.sleep(self.rate)

	def _check_for_errors(self):
		if not self.initialized:
			return

		if self.waiting_on_reply and self.current_request == "retrieve_data":
			if self.get_reply_time() > config.INTERFACE_TIMEOUT:
				with self._status_lock:
					self._fail_state = InterfaceFailState.THREAD_TIMEOUT
					self._fail_output = "Drone interface timed out while waiting for a reply."
				self.stop()

	def _process_reply(self, replies):
		num_replies = len(replies)
		for i in range(num_replies):
			message = self._json_decoder.decode(str(replies[i], "utf-8"))
			if "topic" not in message.keys():
				Log.add("Skipping a message from the DJI interface without a topic.")
				return

			topic = DJIMessageTopic(message["topic"])
			# Parse interface status out to keep track of
			if topic == DJIMessageTopic.InterfaceStatus:
				with self._status_lock:
					self._status = InterfaceState(message["state"])
					self._fail_state = InterfaceFailState(message["fail_state"])
					self._fail_output = message["fail_output"]
					self._status_is_set = True

			last_msg = i == (num_replies - 1)
			self._message_callback(topic, message, last_msg)

	def _thread_init(self):
		if activate_feed(self._feed_name, bound_process_name="dji-interface") is True:
			Log.add("Starting up a new drone interface process")
			open_process_detached(os.path.dirname(os.path.realpath(__file__)) + "/bin/dji-interface")
			with self._status_lock:
				self._status_is_set = True
		else:
			Log.add("Connecting to the existing drone interface process")
			self.send_request("check_interface")
		super()._thread_init()	

	def _thread_action(self):	
		while not self._request_queue.empty():
			with self._request_state_lock:
				if self._request_in_progress:
					continue

			request = self._request_queue.get()

			with self._request_state_lock:
				self._current_request = request
				self._request_in_progress = True

			self._socket.send_string(request)
			self._reply_queue.put(self._socket.recv_multipart())

			with self._request_state_lock:
				self._current_request = None

	def _thread_complete(self):
		with self._status_lock:
			self._status = InterfaceState.OFFLINE
		super()._thread_complete()

	def send_request(self, request):
		with self._status_lock:
			if request == "start_interface" and self.status is InterfaceState.OFFLINE:
				self._status = InterfaceState.ATTEMPTING
		super().send_request(request)

	def stop(self):
		with self._status_lock:
			self._status = InterfaceState.OFFLINE
		kill_process("dji-interface")
		super().stop()

	@staticmethod
	def read_error_log():
		output_file = os.path.dirname(os.path.realpath(__file__)) + "/nohup.out"
		error_string = None

		if os.path.isfile(output_file):
			f = open(output_file)
			for line in f:
				if "ERRORLOG" in line:
					if error_string is not None:
						error_string = error_string + "\n" + line
					else:
						error_string = line

		return error_string


class Drone(ABC):
	def __init__(self):
		self.drone_status_lock = Lock()
		self.drone_update_handlers = []
		self.interface_fail_output = ""

	@property
	@abstractmethod
	def interface_status(self):
		pass

	@abstractmethod
	def start_interface(self):
		return "Method 'start_interface' has not been implemented correctly for this drone.", False

	@abstractmethod
	def stop_interface(self):
		return "Method 'stop_interface' has not been implemented correctly for this drone.", False

	@abstractmethod
	def check_interface(self):
		return "Method 'check_interface' has not been implemented correctly for this drone.", False


class DJIDrone(Drone):
	def __init__(self, zmq_context, rate=10/1000):
		super().__init__()
		self._update_rate = rate
		self._zmq_context = zmq_context
		self._interface = None
		self._reinitialize_interface()

	@property
	def interface_status(self):
		return self._interface.status

	def update(self):
		if self._interface.fail_state is InterfaceFailState.THREAD_TIMEOUT:
			Log.add(self._interface.fail_output)
			self._reinitialize_interface()
		else:
			if self._interface.status == InterfaceState.ATTEMPTING:
				if self._interface.current_request is None:
					self.check_interface()

	def _reinitialize_interface(self):
		if self._interface is not None and self._interface.is_alive():
			self._interface.stop()
		self._interface = DJIInterfaceThread(self._zmq_context, self._process_drone_update, rate=self._update_rate)
		self._interface.start()
		self._interface.start_update_async()

	def _process_drone_update(self, topic, message, last_msg):
		if topic == DJIMessageTopic.InterfaceStatus:
			Log.add("Received drone connection status from the interface " + self.interface_status)

	def start_interface(self):
		with self.drone_status_lock:
			if self._interface.status == InterfaceState.ONLINE:
				msg, result = "Drone interface already active.", False
			elif self._interface.status == InterfaceState.ATTEMPTING:
				msg, result = "Drone interface is already attempting a connection.", False
			else:
				if self._interface.initialized:
					# Before trying anything, make sure the process is actually running
					if not self._interface.is_process_running():
						msg, result = "Attempted to start the interface but there is no interface process running.", False
						self._interface.stop()
					else:
						# Then start the interface
						self._interface.send_request("start_interface")
						self._interface.send_request("check_interface")
						msg, result = "Attempting to start the drone interface.", True
				else:
					msg, result = "Tried to start the interface before it was initialized.", False

		Log.add(msg)
		return msg, result

	def stop_interface(self):
		super().stop_interface()
		if self.interface_status == InterfaceState.OFFLINE:
			msg, result = "Tried to stop the drone interface but it is not running.", False
		else:
			Log.add("Rebooting the drone interface process.")
			self._reinitialize_interface()
			msg, result = "Stopping the drone interface and reinitializing the process.", True

		Log.add(msg, not result)
		return msg, result

	def check_interface(self):
		super().check_interface()
		if not self._interface.is_alive():
			return "Interface Status: " + self.interface_status, True

		self._interface.send_request("check_interface")
		return "Requesting an interface status update.", True
