#ifndef __MIT_ROBOT_SDK_CHANNEL_PUBLISHER_HPP__
#define __MIT_ROBOT_SDK_CHANNEL_PUBLISHER_HPP__

#include "channel_name.hpp"
#include <common/lcm_types/control_messages/Command.hpp>
 
namespace yobotics  
{
namespace robot
{

class ChannelPublisher{//LCM 消息发布
public:
    ChannelPublisher(lcm::LCM *lcm);
    void write(motor_cmd_t *info);
    void write(sport_client_cmd_t *info);
    void write(development_command_t *info);
    void writeNav(control_messages::Command *info);

private:  
    lcm::LCM *_lcm;
    motor_cmd_t motor_cmd{};
    sport_client_cmd_t sport_client_cmd{};
    development_command_t development_cmd{};
    control_messages::Command nav_client_cmd{};
};


}
}
#endif//__MIT_ROBOT_SDK_CHANNEL_PUBLISHER_HPP    
