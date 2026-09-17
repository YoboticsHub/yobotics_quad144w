#ifndef __MIT_ROBOT_SDK_CHANNEL_SUBSCRIBER_HPP__
#define __MIT_ROBOT_SDK_CHANNEL_SUBSCRIBER_HPP__

#include "channel_name.hpp"
#include <common/lcm_types/control_messages/Response.hpp>
  
namespace yobotics
{    
namespace robot
{
class ChannelSubscriber{
public:  
    ChannelSubscriber(lcm::LCM *lcm);
    ~ChannelSubscriber();
    void read(motor_state_t *info);
    void read(imu_data_t *info);
    void read(rc_cmd_t *info);
    void read(robot_state_t *info);
    void read(state_estimator_lcmt *info);
    void read(power_state_t *info);
    void read(sport_client_state_t *info);
    void read(quad_joint_state_t *info);
    void read(quad_joint_command_t *info);
    void read(development_state_t *info);
    void readNavData(control_messages::Response *info);
    void read_handle(const lcm::ReceiveBuffer *rbuf, const std::string &chan);
    void zero();
    void handleInterfaceLCM()
    {
      while ( !_interfaceLcmQuit ) {
        _lcm->handle();
      }
    }  
    
private:           
    lcm::LCM *_lcm;  
    volatile bool _interfaceLcmQuit = false;  
    std::thread _ChannelSubscriberThread;  
    motor_state_t _motorState_lcmt{};
    imu_data_t _imuData_lcmt{};
    rc_cmd_t _rcCmd_lcmt{};  
    robot_state_t _robotState_lcmt{};  
    state_estimator_lcmt _state_estimator_lcmt{}; 
    power_state_t _gpowerState_lcmt{};
    sport_client_state_t _sport_client_state_lcmt{};
    quad_joint_state_t _quad_joint_state_lcmt{};
    quad_joint_command_t _quad_joint_command_lcmt{};
    development_state_t _development_state_lcmt{};
    control_messages::Response _navData_lcmt{};

    std::mutex _lcm_ready_mutex;
    std::condition_variable _lcm_ready_cv;
    bool _lcm_ready = false; 
};

  
}
}    

#endif//__MIT_ROBOT_SDK_CHANNEL_SUBSCRIBER_HPP__
  
