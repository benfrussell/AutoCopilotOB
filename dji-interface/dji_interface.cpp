#include "dji_interface.hpp"

using namespace DJI::OSDK;
using namespace std;
using json = nlohmann::json;

template <typename Out>
void split(const string &s, char delim, Out result) {
    std::istringstream iss(s);
    string item;
    while (std::getline(iss, item, delim)) {
        *result++ = item;
    }
}

vector<string> split(const string &s, char delim) {
    vector<string> elems;
    split(s, delim, std::back_inserter(elems));
    return elems;
}

void sendInterfaceStatus(zmq::socket_t& zmq_socket, string state, string fail_state, string fail_out, bool active_mode)
{
	json interface_status;
	interface_status["topic"] = "InterfaceStatus";
	interface_status["state"] = state;
	interface_status["fail_state"] = fail_state;
	interface_status["fail_output"] = fail_out;
	interface_status["active_mode"] = active_mode;

	string json_string = interface_status.dump();
	int json_length = json_string.length();

	zmq::message_t zmq_msg(json_length);
	memcpy(zmq_msg.data(), json_string.c_str(), json_length);

	zmq_socket.send(zmq_msg, zmq::send_flags::none);
}

Vehicle* startVehicleInterface(zmq::socket_t& zmq_socket, LinuxSetup *linuxEnvironment) 
{
	Vehicle* vehicle;
	string init_errors = "Could not detect the error.";
	string rt_errors = "";

	try 
	{
		cout << "Initializing environment.\n";
		cout << "Initializing vehicle.\n";
		init_errors = linuxEnvironment->initVehicle();
		vehicle = linuxEnvironment->getVehicle();
	}
	catch(std::runtime_error& e)
	{
		rt_errors = e.what();
	}


	if (vehicle == NULL)
	{
		if (rt_errors.length() == 0) {
			sendInterfaceStatus(zmq_socket, "OFFLINE", "ATTEMPT_FAILURE", init_errors, false);
		} else {
			sendInterfaceStatus(zmq_socket, "OFFLINE", "ATTEMPT_FAILURE", rt_errors, false);
		}
		cout << "Could not connect.\n";
		
	}
	else
	{
		cout << "Connected.\n";
		sendInterfaceStatus(zmq_socket, "ONLINE", "NO_FAILURE", "", false);
	}

	cout << "Sending interface status.\n";

	return vehicle;
}

int main(int argc, char *argv[]) 
{
	// initialize the 0MQ context
	cout << "Starting interface program.\n";
	zmq::context_t context;
	// create and bind a server socket
	zmq::socket_t zmq_socket (context, zmq::socket_type::rep);
	cout << "Made socket.\n";
	zmq_socket.bind("ipc:///tmp/feeds/drone.ipc");
	cout << "Binded.\n";

	LinuxSetup linuxEnvironment(argc, argv);
	Vehicle* vehicle;
	//TelemetryController* tele_control;

	while (true) 
	{
		zmq::message_t req_message;
		zmq_socket.recv (req_message);
		vector<string> req_vec = split(string(static_cast<char*>(req_message.data()), req_message.size()), *const_cast<char*>(" "));
		string rep_string = "";

		cout << "REQUEST: " << req_vec[0] << "\n";

		if (req_vec[0] == "check_interface")
		{
			if (vehicle == NULL) {
				sendInterfaceStatus(zmq_socket, "OFFLINE", "NO_FAILURE", "", false);
			} else {
				sendInterfaceStatus(zmq_socket, "ONLINE", "NO_FAILURE", "", false);
			}
		}
		else 
		{
			rep_string = "Unknown command.";
		}

		if (rep_string.size() > 0) {
			zmq_socket.send(zmq::message_t(&rep_string, (int)rep_string.size()), zmq::send_flags::none);
			cout << "REPLY: " << rep_string << "\n";
		} 
	}

	// while (true) 
	// {
	// 	zmq::message_t req_message;
	// 	zmq_socket.recv (&req_message);
	// 	vector<string> req_vec = split(string(static_cast<char*>(req_message.data()), req_message.size()), *const_cast<char*>(" "));
	// 	string rep_string = "";

	// 	cout << "REQUEST: " << req_vec[0] << "\n";

	// 	if (req_vec[0] == "switch_idle") 
	// 	{
	// 		if (vehicle == NULL || tele_control == NULL) {
	// 			sendInterfaceStatus(zmq_socket, pbdrone::InterfaceStatus::OFFLINE, 
	// 				pbdrone::InterfaceStatus::NO_FAILURE, 
	// 				"", false);
	// 		} else {
	// 			tele_control->switchToIdle();
	// 			sendInterfaceStatus(zmq_socket, pbdrone::InterfaceStatus::ONLINE, 
	// 				pbdrone::InterfaceStatus::NO_FAILURE, 
	// 				"", tele_control->active_mode);
	// 		}
	// 	} 
	// 	else if (req_vec[0] == "switch_active") 
	// 	{
			
	// 		if (vehicle == NULL || tele_control == NULL) {
	// 			sendInterfaceStatus(zmq_socket, pbdrone::InterfaceStatus::OFFLINE, 
	// 				pbdrone::InterfaceStatus::NO_FAILURE, 
	// 				"", false);
	// 		} else {
	// 			if (req_vec.size() == 1) 
	// 			{
	// 				sendInterfaceStatus(zmq_socket, pbdrone::InterfaceStatus::ONLINE, 
	// 					pbdrone::InterfaceStatus::NO_FAILURE, 
	// 					"Must provide an update rate for active mode (Hz).", tele_control->active_mode);
	// 			} 
	// 			else 
	// 			{
	// 				try 
	// 				{
	// 					int hz = std::stoi(req_vec[1]);
	// 					tele_control->switchToActive(hz);
	// 					sendInterfaceStatus(zmq_socket, pbdrone::InterfaceStatus::ONLINE, 
	// 						pbdrone::InterfaceStatus::NO_FAILURE, 
	// 						"", tele_control->active_mode);
	// 				}
	// 				catch (std::invalid_argument& e)
	// 				{
	// 					sendInterfaceStatus(zmq_socket, pbdrone::InterfaceStatus::ONLINE, 
	// 						pbdrone::InterfaceStatus::NO_FAILURE, 
	// 						"Could not parse the update rate argument into an integer.", tele_control->active_mode);
	// 				}				
	// 			}
	// 		}
	// 	} 
	// 	else if (req_vec[0] == "retrieve_data") 
	// 	{
	// 		tele_control->retrieveData();
	// 	} 
	// 	else if (req_vec[0] == "start_interface")
	// 	{
	// 		vehicle = startVehicleInterface(zmq_socket, &linuxEnvironment);
	// 		if (vehicle != NULL)
	// 		{
	// 			tele_control = new TelemetryController(vehicle, &zmq_socket);
	// 		}
	// 	}
	// 	else if (req_vec[0] == "check_interface")
	// 	{
	// 		if (vehicle == NULL || tele_control == NULL) {
	// 			sendInterfaceStatus(zmq_socket, pbdrone::InterfaceStatus::OFFLINE, 
	// 				pbdrone::InterfaceStatus::NO_FAILURE, 
	// 				"", false);
	// 		} else {
	// 			sendInterfaceStatus(zmq_socket, pbdrone::InterfaceStatus::ONLINE, 
	// 				pbdrone::InterfaceStatus::NO_FAILURE, 
	// 				"", tele_control->active_mode);
	// 		}
	// 	}
	// 	else if (req_vec[0] == "return_home")
	// 	{
	// 		if (vehicle != NULL) {
	// 			ErrorCode::ErrorCodeType goHomeAck = vehicle->flightController->startGoHomeSync(3);
	// 			if (goHomeAck != ErrorCode::SysCommonErr::Success) {
	// 				DERROR("Fail to execute go home action!  Error code: %llx\n",goHomeAck);
	// 				rep_string = "Fail to execute go home action!";
	// 			} else {
	// 				rep_string = "Going home!";
	// 			}
	// 		} else {
	// 			rep_string = "Vehicle is not connected.";
	// 		}
			
	// 	}
	// 	else 
	// 	{
	// 		rep_string = "Unknown command.";
	// 	}

	// 	if (rep_string.size() > 0) {
	// 		zmq_socket.send(zmq::message_t(&rep_string, (int)rep_string.size()), zmq::send_flags::none);
	// 		cout << "REPLY: " << rep_string << "\n";
	// 	} 
	// }

	// if (tele_control != NULL) {
	// 	delete tele_control;
	// }
	return 0;
}