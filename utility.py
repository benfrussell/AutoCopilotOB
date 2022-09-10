import os
import os.path
from subprocess import check_output, CalledProcessError, Popen, run
import functools
from sys import exc_info


class UnexpectedStateError(Exception):
	pass


# Ensure an ipc feed is activated. Returns True if it created a new feed.
# Set bound_process_name to check if a binding process exists
def activate_feed(feed_name, bound_process_name=None):
	feed_exists = os.path.exists("/tmp/feeds/{0}.ipc".format(feed_name))
	owner_count = process_count(bound_process_name) if bound_process_name is not None else 0

	if feed_exists is False and owner_count == 0:
		# If the directory doesn't exist then we're starting fresh
		if os.path.exists("/tmp/feeds/") is False:
			os.mkdir("/tmp/feeds/")
		open("/tmp/feeds/{0}.ipc".format(feed_name), "a").close()
		return True
	elif feed_exists is True:
		if owner_count == 1:
			# The feed exists and is likely bound to the individual owner
			return False
		elif owner_count == 0:
			# The feed exists but it's owner is gone. Remake the feed.
			os.remove("/tmp/feeds/{0}.ipc".format(feed_name))
			open("/tmp/feeds/{0}.ipc".format(feed_name), "a").close()
			return True

	# If we made it this far then we're in an unexpected state
	feed_exists_str = "DOES" if feed_exists else "DOES NOT"
	raise UnexpectedACEStateError("""
		Unexpected state when verifying ipc feed {0} with owner {1}. 
		Feed {2} exist but the owner count is {3}.""".format(feed_name, bound_process_name, feed_exists_str, owner_count))


def process_count(name):
	try:
		result = check_output(["pgrep","-f",name]).split(b"\n")[:-1]
		return len(result)
	except CalledProcessError:
		return 0


def kill_process(name):
	try:
		run(["pkill","-9","-f",name])
	except CalledProcessError:
		return


def open_process_detached(command, args=[], output_filename=None):
	filename = "nohup.out" if output_filename is None else output_filename
	output_path = os.path.dirname(os.path.realpath(__file__)) + "/" + filename
	if os.path.isfile(output_path):
		run(["rm", output_path])
	
	if output_filename is None:
		return Popen(['nohup', command] + args, preexec_fn=os.setpgrp)
	else:
		return Popen(['nohup', f'{command}',f'&> {output_filename} &'] + args, preexec_fn=os.setpgrp)


def arg_string_to_dict(arg_string):
	arg_dict = dict()
	cur_flag = None
	for arg in arg_string.split(" "):
		if len(arg) == 0:
			continue

		# If it starts with a dash and isn't followed by a number, consider it an argument flag
		if arg[0] == "-" and not arg[1].isnumeric():
			cur_flag = arg[1:]
			arg_dict[cur_flag] = ""
		elif cur_flag is not None:
			arg_dict[cur_flag] = arg

	return arg_dict