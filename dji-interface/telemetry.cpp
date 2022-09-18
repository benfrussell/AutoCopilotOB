#include <dji_telemetry.hpp>
#include "telemetry.hpp"
#include <typeinfo>

using namespace DJI::OSDK;
using namespace DJI::OSDK::Telemetry;
using namespace std;
using json = nlohmann::json;

uint64_t timeSinceEpochMillisec() {
  using namespace std::chrono;
  return duration_cast<milliseconds>(system_clock::now().time_since_epoch()).count();
}

TelemetryController::TelemetryController(Vehicle* vehicle, zmq::socket_t* zmq_socket, int hz)
{
	this->vehicle = vehicle;
	this->zmq_socket = zmq_socket;
	this->slow_topic_timer = timeSinceEpochMillisec();

	ACK::ErrorCode subscribeStatus;
	subscribeStatus = this->vehicle->subscribe->verify(1);
	if (ACK::getError(subscribeStatus) != ACK::SUCCESS)
	{
		ACK::getErrorCodeMessage(subscribeStatus, __func__);
		return;
	}

	TopicName flightStatusTopic[]  = { TOPIC_STATUS_FLIGHT };
	this->subscribeToTopics(0, 1, flightStatusTopic, 1, false);

	TopicName fast_topics[] = { TOPIC_STATUS_DISPLAYMODE, TOPIC_GPS_FUSED, TOPIC_ACCELERATION_BODY };
	this->subscribeToTopics(1, hz, fast_topics, 3, false);

	TopicName vel_topic[] = { TOPIC_GPS_VELOCITY };
	this->subscribeToTopics(2, 5, vel_topic, 1, false);

  	this->auto_mode = false;
  	this->return_to_home = false;
}

bool TelemetryController::subscribeToTopics(int index, int freq, TopicName* topics, int numTopic, bool timestamp)
{
	bool pkgStatus = this->vehicle->subscribe->initPackageFromTopicList(index, numTopic, topics, timestamp, freq);
	if (!(pkgStatus))
	{
		return pkgStatus;
	}
	ACK::ErrorCode subscribeStatus = this->vehicle->subscribe->startPackage(index, 1);
	if (ACK::getError(subscribeStatus) != ACK::SUCCESS)
	{
		ACK::getErrorCodeMessage(subscribeStatus, __func__);
		// Cleanup before return
		this->vehicle->subscribe->removePackage(index, 1);
		return false;
	}
	return true;
}

void TelemetryController::sendTelemetry(bool with_accel, bool finish_send)
{
	json msg;
	msg["topic"] = "Telemetry";
	msg["longitude"] = position_data.longitude;
	msg["latitude"] = position_data.latitude;
	msg["altitude"] = position_data.altitude;
	msg["satellites"] = position_data.visibleSatelliteNumber;
	msg["vel_x"] = velocity_data.x * 0.01;
	msg["vel_y"] = velocity_data.y * 0.01;
	msg["vel_z"] = velocity_data.z * 0.01;

	if (with_accel)  {
		msg["accel_x"] = accel_data.x;
		msg["accel_y"] = accel_data.y;
		msg["accel_z"] = accel_data.z;
	}

	string json_string = msg.dump();
	int json_length = json_string.length();

	zmq::message_t zmq_msg(json_length);
	memcpy(zmq_msg.data(), json_string.c_str(), json_length);

	if (finish_send) {
		this->zmq_socket->send(zmq_msg, zmq::send_flags::none);
	} else {
		this->zmq_socket->send(zmq_msg, zmq::send_flags::sndmore);
	}
}

void TelemetryController::sendFlightStatus(bool finish_send)
{
	json msg;
	msg["topic"] = "FlightStatus";
	msg["state"] = (int)flight_status_data;

	string json_string = msg.dump();
	int json_length = json_string.length();

	zmq::message_t zmq_msg(json_length);
	memcpy(zmq_msg.data(), json_string.c_str(), json_length);

	if (finish_send) {
		this->zmq_socket->send(zmq_msg, zmq::send_flags::none);
	} else {
		this->zmq_socket->send(zmq_msg, zmq::send_flags::sndmore);
	}
}

void TelemetryController::sendControlDevice(bool finish_send)
{
	int displaymode = (int)displaymode_data;

	// 11 - Auto takeoff
	// 12 - Auto landing
	// 14 - Auto fly to point (?)
	// 15 - Return to home
	// 17 - SDK Control
	// 33 - Forced auto landing
	
	// If it's 0 or above 40, it's an unknown state, so ignore
	if (displaymode != 0 && displaymode <= 43)
	{
		this->auto_mode = displaymode == 11 || displaymode == 12 || displaymode == 14 || displaymode == 15 || displaymode == 17 || displaymode == 33;
		this->return_to_home = displaymode == 12 || displaymode == 15 || displaymode == 33;
	}

	json msg;
	msg["topic"] = "ControlDevice";
	msg["auto_mode"] = this->auto_mode;
	msg["return_to_home"] = this->return_to_home;
	
	string json_string = msg.dump();
	int json_length = json_string.length();

	zmq::message_t zmq_msg(json_length);
	memcpy(zmq_msg.data(), json_string.c_str(), json_length);

	if (finish_send) {
		this->zmq_socket->send(zmq_msg, zmq::send_flags::none);
	} else {
		this->zmq_socket->send(zmq_msg, zmq::send_flags::sndmore);
	}
}

/*
Packages:
--- PACKAGE 0 - FLIGHT STATUS ---
Flight Status 			@ 1Hz
--- PACKAGE 1 - full rate ---
Display Mode Active 	@ ACTIVE Hz
Position 				@ ACTIVE Hz
Acceleration 			@ ACTIVE Hz
--- PACKAGE 2 - 5Hz ---
Velocity 				@ 5 Hz
*/

bool TelemetryController::retrieveData()
{
	if (timeSinceEpochMillisec() >= this->slow_topic_timer)
	{
		this->flight_status_data = 	this->vehicle->subscribe->getValue<TOPIC_STATUS_FLIGHT>();
		this->sendFlightStatus(false);
		this->slow_topic_timer = timeSinceEpochMillisec() + 1000;
	}

	this->position_data = 		this->vehicle->subscribe->getValue<TOPIC_GPS_FUSED>();
	this->displaymode_data = 	this->vehicle->subscribe->getValue<TOPIC_STATUS_DISPLAYMODE>();
	this->accel_data = 			this->vehicle->subscribe->getValue<TOPIC_ACCELERATION_BODY>();
	this->velocity_data = 		this->vehicle->subscribe->getValue<TOPIC_GPS_VELOCITY>();

	this->sendControlDevice(false);
	this->sendTelemetry(true, true);
	return true;
}