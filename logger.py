import os
import datetime
import sys

class Logger():
	def __init__(self, filepath=None):
		self.writing_logfile = filepath is not None
		if self.writing_logfile:
			if os.path.isfile(filepath):
				self.logfile = open(filepath, 'a')
				self.add(f"{sys.argv[0]} is now appending to this log file " + '({:%Y-%m-%d})'.format(datetime.datetime.now()))
			else:
				self.logfile = open(filepath, 'w')
				self.add(f"Starting log file for {sys.argv[0]} at '{filepath}' on date " + '{:%Y-%m-%d}'.format(datetime.datetime.now()))

	def add(self, entry, warn=False):
		line = '{:%H:%M:%S}'.format(datetime.datetime.now()) + "\t"
		if warn:
			line = line + "WARNING: "
		line = line + entry

		if self.writing_logfile:
			self.logfile.write(line + "\n")
			self.logfile.flush()
			os.fsync(self.logfile.fileno())
		print(line)


Log = Logger(filepath=None)