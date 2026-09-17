#ifndef __MIT_ROBOT_SDK_CHANNEL_NAME_HPP__
#define __MIT_ROBOT_SDK_CHANNEL_NAME_HPP__

#include <string>
#include <memory>
#include <utility>
#include <thread> 
#include <lcm/lcm-cpp.hpp>
#include <lcm_types/cpp/sport_client_cmd_t.hpp>  
#include <lcm_types/cpp/imu_data_t.hpp>   
#include <lcm_types/cpp/motor_cmd_t.hpp>     
#include <lcm_types/cpp/motor_state_t.hpp>   
#include <lcm_types/cpp/rc_cmd_t.hpp>   
#include <lcm_types/cpp/robot_state_t.hpp>  
#include <lcm_types/cpp/power_state_t.hpp>
#include <lcm_types/cpp/state_estimator_lcmt.hpp>   
#include <lcm_types/cpp/sport_client_state_t.hpp>
#include <lcm_types/cpp/quad_joint_state_t.hpp>
#include <lcm_types/cpp/quad_joint_command_t.hpp>
#include <lcm_types/cpp/development_state_t.hpp>
#include <lcm_types/cpp/development_command_t.hpp>
#include <Timer/Timer.hpp>   
#include <eigen3/Eigen/Dense>
#include <chrono>
#include <mutex>
#include <condition_variable> 

namespace yobotics  
{
namespace robot  
{   

const std::string ROBOT_SDK_TOPIC_LOWCMD ="MOTOR_CMD";
const std::string ROBOT_SDK_TOPIC_LOWSTATE ="MOTOR_STATE";
const std::string ROBOT_SDK_TOPIC_IMU ="IMU_DATA" ;
const std::string ROBOT_SDK_TOPIC_RCSTATE = "CMD" ;
const std::string ROBOT_SDK_TOPIC_RBSTATE = "ROBOT_STATE" ;
const std::string ROBOT_SDK_TOPIC_STATE = "state_estimator" ;
const std::string ROBOT_SDK_SPORT = "QUAD_ROBOT_CONTROL_Y20W" ; 
const std::string ROBOT_SDK_POWER_STATE = "POWER_STATE" ;
const std::string ROBOT_SDK_TOPIC_QUAD_STATE = "QUAD_ROBOT_STATE_Y20W";
const std::string ROBOT_SDK_TOPIC_LEG_CONTROL_DATA = "Y20W_QUAD_JOINT_STATE";
const std::string ROBOT_SDK_TOPIC_LEG_CONTROL_COMMAND = "Y20W_QUAD_JOINT_COMMAND";
const std::string ROBOT_SDK_TOPIC_DEVELOPMENT_STATE = "Y20W_development_state";
const std::string ROBOT_SDK_TOPIC_DEVELOPMENT_COMMAND = "Y20W_development_command";
const std::string ROBOT_SDK_NAV = "UPPER_dogNAV_1";
const std::string ROBOT_SDK_NAV_STATE = "UPPER_dogNAV_STATE_1";

/*
 * @brief
 * @class: ChannelNamer    
 */ 
class ChannelNamer
{
public:
    ChannelNamer();
    ~ChannelNamer();

protected:
    std::string GetSendChannelName(const std::string& name);
    std::string GetRecvChannelName(const std::string& name);
};

using ChannelNamerPtr = std::shared_ptr<ChannelNamer>;

}
}

#endif//__MIT_ROBOT_SDK_CHANNEL_NAME_HPP__ 
