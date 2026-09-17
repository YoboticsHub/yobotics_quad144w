#include "channel_name.hpp"
#include "channel_publisher.hpp"
#include "channel_subscriber.hpp"

#include <chrono>
#include <stdexcept>
#include <thread>

namespace yobotics {
namespace robot {

ChannelPublisher::ChannelPublisher(lcm::LCM* lcm) : _lcm(lcm) {
    if (!_lcm) {
        throw std::invalid_argument("LCM pointer is null");
    }
}

void ChannelPublisher::write(motor_cmd_t* info) {
    if (!info) {
        return;
    }

    for (int i = 0; i < 4; ++i) {
        motor_cmd.q_des_abad[i] = info->q_des_abad[i];
        motor_cmd.q_des_hip[i] = info->q_des_hip[i];
        motor_cmd.q_des_knee[i] = info->q_des_knee[i];

        motor_cmd.qd_des_abad[i] = info->qd_des_abad[i];
        motor_cmd.qd_des_hip[i] = info->qd_des_hip[i];
        motor_cmd.qd_des_knee[i] = info->qd_des_knee[i];

        motor_cmd.kp_abad[i] = info->kp_abad[i];
        motor_cmd.kp_hip[i] = info->kp_hip[i];
        motor_cmd.kp_knee[i] = info->kp_knee[i];

        motor_cmd.kd_abad[i] = info->kd_abad[i];
        motor_cmd.kd_hip[i] = info->kd_hip[i];
        motor_cmd.kd_knee[i] = info->kd_knee[i];

        motor_cmd.tau_abad_ff[i] = info->tau_abad_ff[i];
        motor_cmd.tau_hip_ff[i] = info->tau_hip_ff[i];
        motor_cmd.tau_knee_ff[i] = info->tau_knee_ff[i];

        motor_cmd.contactFlag[i] = info->contactFlag[i];
    }

    _lcm->publish(ROBOT_SDK_TOPIC_LOWCMD, &motor_cmd);
}

void ChannelPublisher::write(sport_client_cmd_t* info) {
    if (!info) {
        return;
    }

    sport_client_cmd.rc_enable = info->rc_enable;
    sport_client_cmd.velocity[0] = info->velocity[0];
    sport_client_cmd.velocity[1] = info->velocity[1];
    sport_client_cmd.velocity[2] = info->velocity[2];

    sport_client_cmd.euler_angles[0] = info->euler_angles[0];
    sport_client_cmd.euler_angles[1] = info->euler_angles[1];
    sport_client_cmd.euler_angles[2] = info->euler_angles[2];

    sport_client_cmd.body_height = info->body_height;
    sport_client_cmd.step_height = info->step_height;
    sport_client_cmd.api = info->api;

    _lcm->publish(ROBOT_SDK_SPORT, &sport_client_cmd);
}

void ChannelPublisher::write(development_command_t* info) {
    if (!info) {
        return;
    }

    development_cmd.robot_id = info->robot_id;
    development_cmd.enable_development_mode = info->enable_development_mode;

    for (int i = 0; i < 12; ++i) {
        development_cmd.joint_des_q[i] = info->joint_des_q[i];
        development_cmd.joint_des_qd[i] = info->joint_des_qd[i];
        development_cmd.joint_des_tau[i] = info->joint_des_tau[i];
        development_cmd.joint_des_kp[i] = info->joint_des_kp[i];
        development_cmd.joint_des_kd[i] = info->joint_des_kd[i];
    }

    _lcm->publish(ROBOT_SDK_TOPIC_DEVELOPMENT_COMMAND, &development_cmd);
}

void ChannelPublisher::writeNav(control_messages::Command* info) {
    if (!info) {
        return;
    }

    nav_client_cmd.cmd = info->cmd;
    for (int i = 0; i < 8; ++i) {
        nav_client_cmd.params[i] = info->params[i];
    }

    _lcm->publish(ROBOT_SDK_NAV, &nav_client_cmd);
}

ChannelSubscriber::ChannelSubscriber(lcm::LCM* lcm) {
    if (!lcm) {
        throw std::invalid_argument("LCM pointer is null");
    }
    _lcm = lcm;

    std::this_thread::sleep_for(std::chrono::milliseconds(100));

    {
        std::lock_guard<std::mutex> lock(_lcm_ready_mutex);
        _lcm_ready = true;
    }
    _lcm_ready_cv.notify_one();

    zero();

    _lcm->subscribe(ROBOT_SDK_TOPIC_LOWSTATE, &ChannelSubscriber::read_handle, this);
    _lcm->subscribe(ROBOT_SDK_TOPIC_IMU, &ChannelSubscriber::read_handle, this);
    _lcm->subscribe(ROBOT_SDK_TOPIC_RCSTATE, &ChannelSubscriber::read_handle, this);
    _lcm->subscribe(ROBOT_SDK_TOPIC_RBSTATE, &ChannelSubscriber::read_handle, this);
    _lcm->subscribe(ROBOT_SDK_TOPIC_STATE, &ChannelSubscriber::read_handle, this);
    _lcm->subscribe(ROBOT_SDK_POWER_STATE, &ChannelSubscriber::read_handle, this);

    // 与 quad200-rl-control-framework 对齐的补充通道。
    _lcm->subscribe(ROBOT_SDK_TOPIC_QUAD_STATE, &ChannelSubscriber::read_handle, this);
    _lcm->subscribe(ROBOT_SDK_TOPIC_LEG_CONTROL_DATA, &ChannelSubscriber::read_handle, this);
    _lcm->subscribe(ROBOT_SDK_TOPIC_LEG_CONTROL_COMMAND, &ChannelSubscriber::read_handle, this);
    _lcm->subscribe(ROBOT_SDK_TOPIC_DEVELOPMENT_STATE, &ChannelSubscriber::read_handle, this);
    _lcm->subscribe(ROBOT_SDK_NAV_STATE, &ChannelSubscriber::read_handle, this);

    _ChannelSubscriberThread = std::thread(&ChannelSubscriber::handleInterfaceLCM, this);
}

ChannelSubscriber::~ChannelSubscriber() {
    _interfaceLcmQuit = true;
    if (_ChannelSubscriberThread.joinable()) {
        _ChannelSubscriberThread.join();
    }
}

void ChannelSubscriber::zero() {
    for (int i = 0; i < 4; ++i) {
        _motorState_lcmt.q_abad[i] = 0.f;
        _motorState_lcmt.q_hip[i] = 0.f;
        _motorState_lcmt.q_knee[i] = 0.f;
        _motorState_lcmt.qd_abad[i] = 0.f;
        _motorState_lcmt.qd_hip[i] = 0.f;
        _motorState_lcmt.qd_knee[i] = 0.f;
        _motorState_lcmt.tau_abad[i] = 0.f;
        _motorState_lcmt.tau_hip[i] = 0.f;
        _motorState_lcmt.tau_knee[i] = 0.f;
        _motorState_lcmt.footForce[i] = 0.f;
    }

    for (int i = 0; i < 3; ++i) {
        _imuData_lcmt.gyroscope[i] = 0.f;
        _imuData_lcmt.accelerometer[i] = 0.f;
        _imuData_lcmt.rpy[i] = 0.f;
        _imuData_lcmt.quaternion[i] = 0.f;

        _state_estimator_lcmt.p[i] = 0.f;
        _state_estimator_lcmt.vBody[i] = 0.f;
        _state_estimator_lcmt.rpy[i] = 0.f;

        _sport_client_state_lcmt.rpy[i] = 0.f;
        _development_state_lcmt.rpy[i] = 0.f;
        _development_state_lcmt.omega[i] = 0.f;
        _development_state_lcmt.acc[i] = 0.f;
        _development_state_lcmt.v_des[i] = 0.f;
        _development_state_lcmt.omega_des[i] = 0.f;
    }
    _imuData_lcmt.quaternion[3] = 0.f;

    _gpowerState_lcmt.voltage = 0.f;
    _gpowerState_lcmt.current = 0.f;

    _rcCmd_lcmt.linearVelX = 0.f;
    _rcCmd_lcmt.linearVelY = 0.f;
    _rcCmd_lcmt.linearVelZ = 0.f;
    _rcCmd_lcmt.angularVelX = 0.f;
    _rcCmd_lcmt.angularVelY = 0.f;
    _rcCmd_lcmt.angularVelZ = 0.f;
    _rcCmd_lcmt.roll = 0.f;
    _rcCmd_lcmt.pitch = 0.f;
    _rcCmd_lcmt.yaw = 0.f;
    _rcCmd_lcmt.bodyHeight = 0.f;
    _rcCmd_lcmt.stepHeight = 0.f;
    _rcCmd_lcmt.mode = 0;
    _rcCmd_lcmt.gait = 0;
    _rcCmd_lcmt.update = 0;

    _robotState_lcmt.state = 0;

    _sport_client_state_lcmt.power[0] = 0.f;
    _sport_client_state_lcmt.power[1] = 0.f;
    _sport_client_state_lcmt.v = 0.f;
    _sport_client_state_lcmt.h = 0.f;
    _sport_client_state_lcmt.state = 0;
    _sport_client_state_lcmt.fault = 0;

    for (int i = 0; i < 12; ++i) {
        _quad_joint_state_lcmt.joint_q[i] = 0.f;
        _quad_joint_state_lcmt.joint_qd[i] = 0.f;
        _quad_joint_state_lcmt.joint_tau[i] = 0.f;
        _quad_joint_state_lcmt.joint_fault[i] = 0.f;
        _quad_joint_state_lcmt.joint_temp[i] = 0.f;

        _quad_joint_command_lcmt.joint_des_q[i] = 0.f;
        _quad_joint_command_lcmt.joint_des_qd[i] = 0.f;
        _quad_joint_command_lcmt.joint_des_tau[i] = 0.f;
        _quad_joint_command_lcmt.joint_des_kp[i] = 0.f;
        _quad_joint_command_lcmt.joint_des_kd[i] = 0.f;

        _development_state_lcmt.joint_q[i] = 0.f;
        _development_state_lcmt.joint_qd[i] = 0.f;
        _development_state_lcmt.joint_tau[i] = 0.f;
    }

    for (int i = 0; i < 4; ++i) {
        _quad_joint_command_lcmt.flags[i] = 0;
    }

    _development_state_lcmt.robot_id.clear();
    _development_state_lcmt.mode = 0;
}

void ChannelSubscriber::read_handle(const lcm::ReceiveBuffer* rbuf, const std::string& chan) {
    if (chan == ROBOT_SDK_TOPIC_LOWSTATE) {
        _motorState_lcmt.decode(rbuf->data, 0, rbuf->data_size);
    } else if (chan == ROBOT_SDK_TOPIC_IMU) {
        _imuData_lcmt.decode(rbuf->data, 0, rbuf->data_size);
    } else if (chan == ROBOT_SDK_TOPIC_RCSTATE) {
        _rcCmd_lcmt.decode(rbuf->data, 0, rbuf->data_size);
    } else if (chan == ROBOT_SDK_TOPIC_RBSTATE) {
        _robotState_lcmt.decode(rbuf->data, 0, rbuf->data_size);
    } else if (chan == ROBOT_SDK_TOPIC_STATE) {
        _state_estimator_lcmt.decode(rbuf->data, 0, rbuf->data_size);
    } else if (chan == ROBOT_SDK_POWER_STATE) {
        _gpowerState_lcmt.decode(rbuf->data, 0, rbuf->data_size);
    } else if (chan == ROBOT_SDK_TOPIC_QUAD_STATE) {
        _sport_client_state_lcmt.decode(rbuf->data, 0, rbuf->data_size);
    } else if (chan == ROBOT_SDK_TOPIC_LEG_CONTROL_DATA) {
        _quad_joint_state_lcmt.decode(rbuf->data, 0, rbuf->data_size);
    } else if (chan == ROBOT_SDK_TOPIC_LEG_CONTROL_COMMAND) {
        _quad_joint_command_lcmt.decode(rbuf->data, 0, rbuf->data_size);
    } else if (chan == ROBOT_SDK_TOPIC_DEVELOPMENT_STATE) {
        _development_state_lcmt.decode(rbuf->data, 0, rbuf->data_size);
    } else if (chan == ROBOT_SDK_NAV_STATE) {
        _navData_lcmt.decode(rbuf->data, 0, rbuf->data_size);
    }
}

void ChannelSubscriber::read(motor_state_t* info) {
    if (!info) {
        return;
    }
    for (int i = 0; i < 4; ++i) {
        info->q_abad[i] = _motorState_lcmt.q_abad[i];
        info->q_hip[i] = _motorState_lcmt.q_hip[i];
        info->q_knee[i] = _motorState_lcmt.q_knee[i];
        info->qd_abad[i] = _motorState_lcmt.qd_abad[i];
        info->qd_hip[i] = _motorState_lcmt.qd_hip[i];
        info->qd_knee[i] = _motorState_lcmt.qd_knee[i];
        info->tau_abad[i] = _motorState_lcmt.tau_abad[i];
        info->tau_hip[i] = _motorState_lcmt.tau_hip[i];
        info->tau_knee[i] = _motorState_lcmt.tau_knee[i];
        info->footForce[i] = _motorState_lcmt.footForce[i];
    }
}

/**
 * 从LCMT类型的IMU数据结构中读取数据并填充到用户提供的IMU数据结构中
 * @param info 指向用户提供的imu_data_t类型结构体的指针，用于存储读取的数据
 */
void ChannelSubscriber::read(imu_data_t* info) {
    // 检查传入的指针是否有效
    if (!info) {
        return;
    }
    for (int i = 0; i < 3; ++i) {
        info->gyroscope[i] = _imuData_lcmt.gyroscope[i];
        info->accelerometer[i] = _imuData_lcmt.accelerometer[i];
        info->rpy[i] = _imuData_lcmt.rpy[i];
        info->quaternion[i] = _imuData_lcmt.quaternion[i];
    }
    info->quaternion[3] = _imuData_lcmt.quaternion[3];
}

void ChannelSubscriber::read(state_estimator_lcmt* info) {
    if (!info) {
    // 复制四元数的第四个分量（w分量）
        return;
    }
    for (int i = 0; i < 3; ++i) {
        info->p[i] = _state_estimator_lcmt.p[i];
        info->vBody[i] = _state_estimator_lcmt.vBody[i];
        info->rpy[i] = _state_estimator_lcmt.rpy[i];
    }
}

void ChannelSubscriber::read(rc_cmd_t* info) {
    if (!info) {
        return;
    }
    info->linearVelX = _rcCmd_lcmt.linearVelX;
    info->linearVelY = _rcCmd_lcmt.linearVelY;
    info->linearVelZ = _rcCmd_lcmt.linearVelZ;
    info->angularVelX = _rcCmd_lcmt.angularVelX;
    info->angularVelY = _rcCmd_lcmt.angularVelY;
    info->angularVelZ = _rcCmd_lcmt.angularVelZ;
    info->roll = _rcCmd_lcmt.roll;
    info->pitch = _rcCmd_lcmt.pitch;
    info->yaw = _rcCmd_lcmt.yaw;
    info->bodyHeight = _rcCmd_lcmt.bodyHeight;
    info->stepHeight = _rcCmd_lcmt.stepHeight;
    info->mode = _rcCmd_lcmt.mode;
    info->gait = _rcCmd_lcmt.gait;
    info->update = _rcCmd_lcmt.update;
}

void ChannelSubscriber::read(robot_state_t* info) {
    if (!info) {
        return;
    }
    info->state = _robotState_lcmt.state;
}

void ChannelSubscriber::read(power_state_t* info) {
    if (!info) {
        return;
    }
    info->voltage = _gpowerState_lcmt.voltage;
    info->current = _gpowerState_lcmt.current;
}

void ChannelSubscriber::read(sport_client_state_t* info) {
    if (!info) {
        return;
    }
    info->power[0] = _sport_client_state_lcmt.power[0];
    info->power[1] = _sport_client_state_lcmt.power[1];
    info->rpy[0] = _sport_client_state_lcmt.rpy[0];
    info->rpy[1] = _sport_client_state_lcmt.rpy[1];
    info->rpy[2] = _sport_client_state_lcmt.rpy[2];
    info->v = _sport_client_state_lcmt.v;
    info->h = _sport_client_state_lcmt.h;
    info->state = _sport_client_state_lcmt.state;
    info->fault = _sport_client_state_lcmt.fault;
}

void ChannelSubscriber::read(quad_joint_state_t* info) {
    if (!info) {
        return;
    }
    for (int i = 0; i < 12; ++i) {
        info->joint_q[i] = _quad_joint_state_lcmt.joint_q[i];
        info->joint_qd[i] = _quad_joint_state_lcmt.joint_qd[i];
        info->joint_tau[i] = _quad_joint_state_lcmt.joint_tau[i];
        info->joint_fault[i] = _quad_joint_state_lcmt.joint_fault[i];
        info->joint_temp[i] = _quad_joint_state_lcmt.joint_temp[i];
    }
}

void ChannelSubscriber::read(quad_joint_command_t* info) {
    if (!info) {
        return;
    }
    for (int i = 0; i < 12; ++i) {
        info->joint_des_q[i] = _quad_joint_command_lcmt.joint_des_q[i];
        info->joint_des_qd[i] = _quad_joint_command_lcmt.joint_des_qd[i];
        info->joint_des_tau[i] = _quad_joint_command_lcmt.joint_des_tau[i];
        info->joint_des_kp[i] = _quad_joint_command_lcmt.joint_des_kp[i];
        info->joint_des_kd[i] = _quad_joint_command_lcmt.joint_des_kd[i];
    }
    for (int i = 0; i < 4; ++i) {
        info->flags[i] = _quad_joint_command_lcmt.flags[i];
    }
}

void ChannelSubscriber::read(development_state_t* info) {
    if (!info) {
        return;
    }
    info->robot_id = _development_state_lcmt.robot_id;
    info->mode = _development_state_lcmt.mode;

    for (int i = 0; i < 12; ++i) {
        info->joint_q[i] = _development_state_lcmt.joint_q[i];
        info->joint_qd[i] = _development_state_lcmt.joint_qd[i];
        info->joint_tau[i] = _development_state_lcmt.joint_tau[i];
    }

    for (int i = 0; i < 4; ++i) {
        info->quat[i] = _development_state_lcmt.quat[i];
    }

    for (int i = 0; i < 3; ++i) {
        info->rpy[i] = _development_state_lcmt.rpy[i];
        info->omega[i] = _development_state_lcmt.omega[i];
        info->acc[i] = _development_state_lcmt.acc[i];
        info->v_des[i] = _development_state_lcmt.v_des[i];
        info->omega_des[i] = _development_state_lcmt.omega_des[i];
    }
}

void ChannelSubscriber::readNavData(control_messages::Response* info) {
    if (!info) {
        return;
    }
    *info = _navData_lcmt;
}

} // namespace robot
} // namespace yobotics
