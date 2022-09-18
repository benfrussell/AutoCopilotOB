import sys
import os
from shutil import copyfile
from configparser import ConfigParser


class ConfigEntry:
	def __init__(self, entry_id, section, option, type, value):
		self.id = entry_id
		self.section = section
		self.option = option

		if type not in ("int", "float", "string", "bool"):
			raise ValueError(f"Tried to create a config entry with an unsupported type ({type}).")
		self.type = type
		self.value = None
		self.set_value(value)

	def set_value(self, value):
		parsed_value = None

		if self.type == "int":
			try:
				parsed_value = int(value)
			except ValueError as e:
				pass
		elif self.type == "float":
			try:
				parsed_value = float(value)
			except ValueError:
				pass
		elif self.type == "string":
			try:
				parsed_value = str(value)
			except ValueError:
				pass
		elif self.type == "bool":
			try:
				parsed_value = value == "True"
			except ValueError:
				pass

		if parsed_value is not None:
			self.value = value
			setattr(sys.modules[__name__], self.option, parsed_value)
			return f"Set configuration entry {self.option} to {value}", True
		else:
			try:
				return f"Set configuration entry {self.option} failed. Could not parse '{value}' as type '{self.type}'.", False
			except ValueError:
				return f"Set configuration entry {self.option} failed. Could not parse the value as type '{self.type}'.", False

	def make_config_msg(self):
		msg = dict()
		msg["id"] = self.id
		msg["section"] = self.section
		msg["option"] = self.option
		msg["value"] = self.value
		return msg


class ConfigManager:
	def __init__(self):
		self.exception_raised = False
		self.exception = None

		if not os.path.isfile(sys.path[0] + "/Config.ini"):
			copyfile(sys.path[0] + "/ConfigDefaults.ini", sys.path[0] + "/Config.ini")

		self.default_config = ConfigParser()
		self.default_config.read(sys.path[0] + "/ConfigDefaults.ini")

		self.config_path = sys.path[0] + "/Config.ini"
		self.config = ConfigParser()
		self.config.read(self.config_path)

		self.entries = dict()

		self.add_entry("Main", "UPDATE_HZ", "int")
		self.add_entry("Drone", "INTERFACE_TIMEOUT", "int")

	def add_entry(self, section, option, type):
		self._validate_and_restore_section(section)
		self._validate_and_restore_option(section, option)

		new_id = len(self.entries)
		self.entries[new_id] = ConfigEntry(new_id, section, option, type, self.config[section][option])

	def _validate_and_restore_section(self, section):
		if not self.config.has_section(section):
			if not self.default_config.has_section(section):
				raise LookupError(f"The section '{section}' does not exist in the  config.")

			self.config.add_section(section)
			self.config.write(open(self.config_path, 'w'))

	def _validate_and_restore_option(self, section, option):
		if not self.config.has_option(section, option):
			if not self.default_config.has_option(section, option):
				raise LookupError(f"The option '{option}' does not exist under section '{section}' in the  config.")

			self.config.set(section, option, self.default_config[section][option])
			self.config.write(open(self.config_path, 'w'))

	def load_all_defaults(self):
		self.default_config.write(open(self.config_path, 'w'))
		self.config = ConfigParser()
		self.config.read(self.config_path)

		for entry in self.entries.values():
			if self.config.has_option(entry.section, entry.value):
				entry.set_value(self.config[entry.section][entry.option])

		return "Set all config options to their defaults.", True

	def load_default(self, entry_id):
		if entry_id not in self.entries.keys():
			return f"There is not config entry with the id '{entry_id}'", False
		
		entry = self.entries[entry_id]
		default_value = self.default_config[entry.section][entry.option]
		msg, success = self.set_entry(entry_id, default_value)

		if success:
			return f"Set '{entry.option}' to '{default_value}' (default).", True
		return msg, success

	def set_entry(self, entry_id, value):
		if entry_id not in self.entries.keys():
			return f"There is not config entry with the id '{entry_id}'", False
		entry = self.entries[entry_id]

		try:
			self._validate_and_restore_section(entry.section)
		except LookupError as e:
			return str(e), False

		msg, success = entry.set_value(value)
		if success:
			self.config.set(entry.section, entry.option, value)
			self.config.write(open(self.config_path, 'w'))
		return msg, success

	def make_configuration_msg(self):
		configuration = list()
		configuration.extend([entry.make_config_msg() for entry in self.entries.values()])
		return configuration
		