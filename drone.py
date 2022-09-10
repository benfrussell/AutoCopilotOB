import time
import os
from enum import Enum
from json import JSONDecoder
from abc import ABC, abstractmethod
from threading import Lock

from zmq_threads import IPCRequestThread
from utility import activate_feed, open_process_detached, UnexpectedStateError
from logger import Log

class InterfaceState(str, Enum):
	OFFLINE = "OFFLINE"
	ATTEMPTING = "ATTEMPTING"
	ONLINE = "ONLINE"

class InterfaceFailState(str, Enum):
	NO_FAILURE = "OFFLINE"
	ATTEMPT_FAILURE = "ATTEMPT_FAILURE"
	DROPPED_FAILURE = "DROPPED_FAILURE"
	THREAD_FAILURE = "THREAD_FAILURE"
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
	def __init__(self, zmq_context, message_callback, status_lock, rate=10/1000):
		super().__init__(zmq_context, message_callback, "drone", auto_feed_activation=False, rate=rate)

		self.status = InterfaceState.OFFLINE
		self.status_is_set = False
		self.current_request = None
		self.fail_state = None
		self.decoder = JSONDecoder()
		self._status_lock = status_lock

	def start(self):
		super().start()

	def update(self):
		while True:
			while not self._reply_queue.empty():
				with self._request_state_lock:
					self._request_in_progress = False

				reply = self._reply_queue.get()
				self._process_reply(reply)

				with self._request_state_lock:
					self.last_reply_time = time.time() - self._request_time
			time.sleep(self.rate)

	def _process_reply(self, replies):
		num_replies = len(replies)
		for i in range(num_replies):
			message = self.decoder.decode(str(replies[i], "utf-8"))
			if "topic" not in message.keys():
				Log.add("Skipping a message from the DJI interface without a topic.")
				return

			topic = DJIMessageTopic(message["topic"])
			# Parse interface status out to keep track of
			if topic == DJIMessageTopic.InterfaceStatus:
				with self._status_lock:
					self.status = InterfaceState(message["state"])
					self.status_is_set = True

			last_msg = i == (num_replies - 1)
			self._message_callback(topic, message, last_msg)


	def _thread_init(self):
		if activate_feed(self._feed_name, bound_process_name="dji-interface") is True:
			Log.add("Starting up a new drone interface process")
			open_process_detached(os.path.dirname(os.path.realpath(__file__)) + "/bin/dji-interface")
			self.status_is_set = True
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
			self.current_request = request

			with self._request_state_lock:
				self._request_in_progress = True

			self._socket.send_string(request)
			self._reply_queue.put(self._socket.recv_multipart())

			self.current_request = None

	def _thread_complete(self):
		with self._status_lock:
			self.status = InterfaceState.OFFLINE
		super()._thread_complete()

	def send_request(self, request):
		with self._status_lock:
			if request == "start_interface" and self.status is InterfaceState.OFFLINE:
				self.status = InterfaceState.ATTEMPTING
		super().send_request(request)

	def trigger_exception(self, message, interface_fail_state):
		self.fail_state = interface_fail_state
		raise UnexpectedStateError(message)

	def stop(self):
		with self._status_lock:
			self.status = InterfaceState.OFFLINE
		super().stop()

class Drone(ABC):
	def __init__(self):
		self.drone_status_lock = Lock()
		self.drone_update_handlers = []
		self.interface_fail_state = InterfaceFailState.NO_FAILURE
		self.interface_fail_output = ""

	@property
	@abstractmethod
	def interface_status(self):
		pass

	def send_interface_update(self):
		if self.interface_status is None:
			raise UnexpectedStateError(
				"Tried to send the drone's interface state but interface_status property returned None. Was interface_status implemented?")

		Log.add(self.interface_status)

	@abstractmethod
	def start_interface(self, attempts=1):
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
		self._rate = rate
		self._zmq_context = zmq_context

		self._interface = DJIInterfaceThread(self._zmq_context, self._process_drone_update, self.drone_status_lock, rate=rate)
		self._interface.start()
		self._interface.start_update_async()

		self._start_interface_attempts = 0
		self._start_interface_attempting = False

	@property
	def interface_status(self):
		with self.drone_status_lock:
			return self._interface.status

	def update(self):
		if self._start_interface_attempts > 0:
			self._attempt_starting_interface()

	def _process_drone_update(self, topic, message, last_msg):
		if topic == DJIMessageTopic.InterfaceStatus:
			Log.add("Received drone connection status from the interface " + self.interface_status)

			self.interface_fail_state = message["fail_state"]
			self.interface_fail_output = message["fail_output"]

			with self.drone_status_lock:
				# If we're moving from an attempting state, stop checking the attempt
				if self._start_interface_attempting and interface_status.interface_state != messages_pb2.InterfaceStatus.State.ATTEMPTING:
					Log.add("The interface is no longer attempting to connect to the drone")
					self._start_interface_attempting = False

					if message["state"] == InterfaceState.OFFLINE:
						self.interface_fail_state = InterfaceFailState.ATTEMPT_FAILURE
						self.interface_fail_output = self._get_attempt_failure_message()
						

	def _get_attempt_failure_message(self):
		output_file = os.path.dirname(os.path.realpath(__file__)) + "/nohup.out"

		if os.path.isfile(output_file):
			f = open(output_file)
			error_string = None

			for line in f:
				if "ERRORLOG" in line:
					if error_string is not None:
						error_string = error_string + "\n" + line
					else:
						error_string = line

			if error_string is not None:
				return "Interface attempt failed with the following errors:\n" + error_string
			else:
				return "Interface attempt failed but did not report any errors in the output."
		else:
			return "Interface attempt failed and provided no output."

	def start_interface(self, attempts=1):
		super().start_interface()
		with self.drone_status_lock:
			if self._interface.status == InterfaceState.ONLINE:
				msg,result = "Drone interface already active.", False
			elif self._interface.status == InterfaceState.ATTEMPTING:
				msg,result = "Drone interface is already attempting a connection.", False

		self._start_interface_attempts = attempts
		self._start_interface_attempting = True
		if attempts > 1:
			msg,result = "Attempting to start the drone interface up to ({}) time(s).".format(self._start_interface_attempts), True
		elif attempts == 1:
			msg,result = "Attempting to start the drone interface.", True

		Log.add(msg)
		return msg,result

	#@report_exceptions
	def stop_interface(self):
		super().stop_interface()
		Log.add("Stopping the drone interface process")
		if self.interface_status == InterfaceState.OFFLINE:
			return "Drone interface is not running.", False
				
		# Stop the interface thread, kill the process, restart the interface thread which will restart the process
		self._interface.stop()
		kill_process("dji-interface")
		self._interface = DroneInterfaceThread(self._zmq_context, self._process_drone_update, self.drone_status_lock, rate=self._rate)

		Log.add("Rebooting the drone interface process")
		self._interface.start()
		self._interface.start_update_async()

		# Reset the fail states
		self.interface_fail_state = InterfaceFailState.NO_FAILURE
		self.interface_fail_output = ""

		self.send_interface_update()
		return "Stopping the drone interface process.", True
		
	#@report_exceptions
	def _attempt_starting_interface(self):
		with self.drone_status_lock:
			if self._interface.status == InterfaceState.ONLINE:
				Log.add("Attempted to start the connection to the drone but it's already online. Stopping further attempts.")
				self._start_interface_attempts = 0
				return
			elif self._interface.status == InterfaceState.ATTEMPTING:
				return

		if self._interface.initialized:
			# First reset all states
			self.interface_fail_state = InterfaceFailState.NO_FAILURE
			self.interface_fail_output = ""
			# Then start the interface
			self._start_interface_attempts = self._start_interface_attempts - 1

			# Before trying anything, make sure the process is actually running
			if process_count("dji-interface") == 0:
				Log.add("Attempted to start the interface but there is no interface process running.", True)
				self._interface.stop()
			else:
				self._interface.send_request("start_interface")
				self._interface.send_request("check_interface")

			# Then inform everyone what's going down
			self.send_interface_update()

	def check_interface(self):
		super().check_interface()
		if not self._interface.is_alive():
			self.send_interface_update()
			return "Interface Status: " + self.interface_status, True

		self._interface.send_request("check_interface")
		return "Requesting the interface status.", True