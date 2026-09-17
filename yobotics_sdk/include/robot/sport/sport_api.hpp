#ifndef __YOBOTICS_ROBOT_Y20W_SPORT_API_HPP__
#define __YOBOTICS_ROBOT_Y20W_SPORT_API_HPP__

#include <decl.hpp>

namespace yobotics
{
namespace robot
{
const std::string ROBOT_SPORT_SERVICE_NAME = "sport";
const std::string ROBOT_SPORT_API_VERSION = "1.0.0.0";

// API IDs consumed by the quad144w/Y20W controller.
const int32_t ROBOT_SPORT_API_ID_PASSIVE = 1000;
const int32_t ROBOT_SPORT_API_ID_DAMP = 1001;
const int32_t ROBOT_SPORT_API_ID_RECOVERY_STAND = 1006;
const int32_t ROBOT_SPORT_API_ID_DEVELOPMENT = 1005;
const int32_t ROBOT_SPORT_API_ID_STAND_DOWN = 1007;
const int32_t ROBOT_SPORT_API_ID_RL_WALK = 1002;

}
}

#endif
