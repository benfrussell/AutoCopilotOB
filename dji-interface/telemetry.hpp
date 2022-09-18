#ifndef TELEMETRY_HPP
#define TELEMETRY_HPP

#include <string>
#include <iostream>
#include <cctype>
#include <chrono>
#include <zmq_addon.hpp>
#include <json.hpp>

// DJI OSDK includes
#include <dji_vehicle.hpp>
#include <dji_linux_helpers.hpp>

class TelemetryController
{
public:
	TelemetryController(DJI::OSDK::Vehicle* vehicle, zmq::socket_t* zmq_socket, int hz);
	bool retrieveData();
private:
	Vehicle* vehicle;
	zmq::socket_t* zmq_socket;
	uint64_t slow_topic_timer;
	bool auto_mode;
	bool return_to_home;
	
	bool subscribeToTopics(int index, int freq, DJI::OSDK::Telemetry::TopicName* topics, int numTopic, bool timestamp);

	void sendTelemetry(bool with_accel, bool finish_send);

	void sendFlightStatus(bool finish_send);

	void sendControlDevice(bool finish_send);

	DJI::OSDK::Telemetry::TypeMap<DJI::OSDK::Telemetry::TOPIC_STATUS_FLIGHT>::type 		flight_status_data;
	DJI::OSDK::Telemetry::TypeMap<DJI::OSDK::Telemetry::TOPIC_GPS_FUSED>::type 			position_data;
	DJI::OSDK::Telemetry::TypeMap<DJI::OSDK::Telemetry::TOPIC_STATUS_DISPLAYMODE>::type displaymode_data;
	DJI::OSDK::Telemetry::TypeMap<DJI::OSDK::Telemetry::TOPIC_ACCELERATION_BODY>::type 	accel_data;
	DJI::OSDK::Telemetry::TypeMap<DJI::OSDK::Telemetry::TOPIC_GPS_VELOCITY>::type 		velocity_data;
};

#endif