#ifndef __MIT_ROBOT_E15_SPORT_ERROR_HPP__
#define __MIT_ROBOT_E15_SPORT_ERROR_HPP__

#include <decl.hpp>

namespace yobotics
{
namespace robot
{
MIT_DECL_ERR(MIT_ROBOT_SPORT_ERR_CLIENT_POINT_PATH, 4101, "point path error.")
MIT_DECL_ERR(MIT_ROBOT_SPORT_ERR_SERVER_OVERTIME, 4201, "server overtime.")
MIT_DECL_ERR(MIT_ROBOT_SPORT_ERR_SERVER_NOT_INIT, 4202, "server function not init.")

constexpr int32_t MIT_ROBOT_SPORT_STATE_OFF = 0;
constexpr int32_t MIT_ROBOT_SPORT_STATE_DAMP = 1;
constexpr int32_t MIT_ROBOT_SPORT_STATE_RECOVERY_STAND = 2;
constexpr int32_t MIT_ROBOT_SPORT_STATE_RL_WALK = 3;
constexpr int32_t MIT_ROBOT_SPORT_STATE_DEVELOPMENT = 99;

constexpr int32_t MIT_ROBOT_SPORT_FAULT_OK = 0;
constexpr int32_t MIT_ROBOT_SPORT_FAULT_GENERIC = 4001;

}
}

#endif
