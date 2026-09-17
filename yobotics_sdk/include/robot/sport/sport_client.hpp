#ifndef __MIT_ROBOT_E15_SPORT_CLIENT_HPP__
#define __MIT_ROBOT_E15_SPORT_CLIENT_HPP__

#include <decl.hpp>

namespace yobotics
{
namespace robot
{
class SportClient
{
public:
    explicit SportClient();

    int32_t Passive();
    int32_t Damp();
    int32_t RecoveryStand();
    int32_t StandDown();
    int32_t Development();
    int32_t RLWalk();
    int32_t SetRCEnable(bool enable);
    int32_t EnableLCMControl();
    int32_t DisableLCMControl();

    int32_t Move(float vx, float vy, float vyaw);
    int32_t BodyHeight(float body_height);
    int32_t Euler(float roll_cmd, float pitch_cmd);
};

}
}

#endif
