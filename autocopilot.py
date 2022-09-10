from time import sleep, time

import zmq

import configure as config
config_manager = config.ConfigManager()
from drone import DJIDrone

class AutoCopilot:
	def __init__(self):
		self.zmq_context = zmq.Context()
		self.drone = DJIDrone(self.zmq_context, rate=1 / config.UPDATE_HZ)

	def update(self):
		self.drone.update()
		sleep(1 / config.UPDATE_HZ)

if __name__ == "__main__":
	acp = AutoCopilot()
	while True:
		acp.update()